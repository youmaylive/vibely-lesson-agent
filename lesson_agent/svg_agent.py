"""
SVG Agent — Post-processing step that resolves <Svg concept="..." context="..." />
placeholders into actual educational SVG diagrams.

Flow per placeholder:
  1. GENERATE: LLM writes SVG from concept + context
  2. VALIDATE: Code checks well-formed XML, has labels, reasonable size
  3. REVIEW: LLM judges relevance/clarity/accuracy (score 1-10)
  4. REGENERATE: If review < 7, feed critique back and retry (up to 3x)
  5. EMBED or FALLBACK: If all fail → skip (lesson continues without)

Usage:
    from svg_agent import resolve_svgs
    resolve_svgs(Path("lesson_01.mlai"), model="claude-sonnet-4-5")
"""

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from anthropic import AsyncAnthropicBedrock

from prompts.svg_generate import build_svg_generation_prompt, build_svg_review_prompt
from svg_geometry import (
    HARD,
    SD_ANCHOR,
    SD_CANVAS,
    SD_DENSITY,
    SD_DEPTH,
    SD_FONT,
    SD_MEASURABLE,
    SD_MOTION,
    SD_PALETTE,
    SD_SPACING,
    SD_STRUCTURE,
    SD_TEXT_FIT,
    SD_TYPE,
    autofit_viewbox,
    craft_findings,
    detect_overlaps,
    element_boxes,
    motion_findings,
)
import usage



# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_ATTEMPTS = 4  # generate/review retries — extra attempt helps fix overlaps
REVIEW_THRESHOLD = 7  # score >= 7 = accept

# How many review calls may be spent on candidates that already failed the geometry
# gate. Clean candidates are ALWAYS reviewed. A geometry-flagged candidate is still
# worth judging (its score decides which flawed draft to keep if every attempt fails,
# and the judge sees problems the linter cannot), but not at unbounded cost.
#
# Raised 2 -> 3 after measuring a real run: every diagram logged "review skipped
# (attempt 3)" and "(attempt 4)", so the judge was absent for HALF of every
# diagram's attempts and the last two attempts were decided by the linter alone.
# That is rule 24's shape — the cheap check quietly becoming the only check — and
# the diagram that shipped from it was rejected on sight.
#
# The root cause was upstream and is fixed: two of that run's three "collisions"
# were the geometry gate flagging a transmembrane protein for crossing its own
# membrane, twice (see _crossing_bands and drop_coincident_overlays in
# svg_geometry.py). Fewer candidates are flagged now, so this budget is reached
# far less often — but leaving it at 2 would have kept the last attempt unjudged
# whenever it IS reached, and an unjudged attempt is the one that ships.
FLAGGED_REVIEW_BUDGET = 3
# Bedrock inference-profile model ID (Claude via Amazon Bedrock)
DEFAULT_MODEL = "global.anthropic.claude-sonnet-5"

# Match any <Svg ...> placeholder tag (self-closing or not), multi-line safe.
# We match the whole tag, then extract concept/context attributes separately
# so attribute ORDER, line breaks, and a missing context= all work.
_SVG_TAG_RE = re.compile(r'<Svg\b([^>]*?)/?>', re.IGNORECASE | re.DOTALL)
_CONCEPT_ATTR_RE = re.compile(r'concept\s*=\s*"([^"]*)"', re.IGNORECASE | re.DOTALL)
_CONTEXT_ATTR_RE = re.compile(r'context\s*=\s*"([^"]*)"', re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# LLM Helpers (direct Bedrock — plain text completion, no agent)
# ---------------------------------------------------------------------------

# SVG markup is verbose; a low cap silently truncates diagrams mid-element.
# Raised from 8192 because the design spec asks for denser drawings than the old
# prompt did. Not binding on the archived corpus (max ~3667 tokens), but 8192 sits
# *below* _validate_svg's own 50000-byte (~15k token) ceiling, so it was a silent
# truncation waiting to happen: a diagram cut off mid-element fails validation with
# no indication that the model was simply stopped.
MAX_OUTPUT_TOKENS = 16384

# One shared async client. Region: Bedrock model availability differs per region,
# and the "global." inference-profile prefix is the only one valid in both
# us-east-1 and ap-south-1.
_bedrock = AsyncAnthropicBedrock(
    aws_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
)


async def _llm_call_async(prompt: str, model: str) -> str:
    """Make a single LLM call and return the text response.

    Calls Bedrock directly rather than going through the Claude Agent SDK.
    This function only ever needed a plain text completion — routing it through
    the Agent SDK spawned a Claude CLI subprocess per call (~3x slower), and made
    it impossible to call from *inside* an agent tool: a nested SDK session
    deadlocks during MCP initialization ("Control request timeout: initialize").
    A direct call has no subprocess and no nesting, so `generate_one_svg` is safe
    to invoke from the in-agent `generate_svg` tool.
    """
    resp = await _bedrock.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        # Sonnet 5 enables extended thinking by DEFAULT on Bedrock. Left on, it
        # spends the entire max_tokens budget on thinking and returns a response
        # with a single empty `thinking` block and no text at all (stop_reason
        # "max_tokens", 8192/8192 thinking_tokens). Writing an SVG needs no
        # reasoning budget — disabling it takes the call from ~95s/empty to
        # ~14s/valid markup. Note: `temperature` is rejected by this model.
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    # Book the tokens. These calls are invisible to the Agent SDK's cost reporting
    # (they bypass it entirely), and since the SVG design framework landed they run
    # ~4 generate + ~4 review per diagram — material spend that reached no record.
    usage.add_bedrock_usage(getattr(resp, "usage", None))
    return "".join(block.text for block in resp.content if block.type == "text")




# ---------------------------------------------------------------------------
# SVG Validation (code — no LLM)
# ---------------------------------------------------------------------------

def _validate_svg(svg_content: str) -> tuple[bool, str]:
    """Validate SVG is well-formed and has educational value.
    
    Returns (valid, reason).
    """
    # Strip any markdown code fences the LLM might wrap around it
    svg_content = svg_content.strip()
    if svg_content.startswith("```"):
        lines = svg_content.split("\n")
        # Remove first and last ``` lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        svg_content = "\n".join(lines).strip()

    # Must start with <svg
    if not svg_content.lower().startswith("<svg"):
        return False, "Does not start with <svg> tag"

    # Must end with </svg>
    if not svg_content.lower().rstrip().endswith("</svg>"):
        return False, "Does not end with </svg>"

    # Must parse as well-formed XML
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError as e:
        return False, f"Malformed XML: {e}"

    # Must have viewBox
    if "viewBox" not in root.attrib and "viewbox" not in root.attrib:
        return False, "Missing viewBox attribute on <svg>"

    # Must contain <text> labels (educational requirement)
    texts = root.findall(".//{http://www.w3.org/2000/svg}text")
    if not texts:
        # Try without namespace
        texts = [el for el in root.iter() if el.tag.endswith("text") or el.tag == "text"]
    if len(texts) < 2:
        return False, f"Too few text labels ({len(texts)} found, need at least 2)"

    # Reasonable size
    if len(svg_content) < 100:
        return False, "SVG too short (likely incomplete)"
    if len(svg_content) > 50000:
        return False, "SVG too large (> 50KB — overly complex)"

    return True, "OK"


# ---------------------------------------------------------------------------
# Geometry (code — free, deterministic, no LLM)
# ---------------------------------------------------------------------------
#
# All of it now lives in `svg_geometry.py`, which is pure stdlib and has no SDK
# import, so it is testable in the worker image with no AWS credentials — this
# module constructs `AsyncAnthropicBedrock` at import time. See that module's
# docstring for the seven measurement defects the code deleted from here had, and
# `svg_geometry.test.py` (51 cases) for the proof they are gone.


# What to do about each hard finding, keyed by the design-spec rule it cites.
# The generator is corrected against a named clause rather than an ad-hoc
# sentence — that linkage is what makes the spec a framework instead of a lint.
# A single generic instruction cannot work here: 30 of the 47 flagged corpus
# blocks carry only MISSING_TEXT_ANCHOR, which "reposition with 30px gaps" does
# not describe at all, and following it would move correct geometry.
_FIX_BY_RULE = {
    SD_SPACING: (
        "Reposition these so no two elements share pixels — a 30px gap between "
        "boxes, and every label fully inside the shape it belongs to."
    ),
    SD_ANCHOR: (
        'Add an explicit text-anchor ("start", "middle" or "end") to every '
        "<text>, matching the x you positioned it at. Never rely on the default."
    ),
    SD_FONT: (
        'Add font-family="Arial, sans-serif" to the root <svg> element. Nothing '
        "else needs it — it inherits."
    ),
    SD_CANVAS: (
        "Bring this geometry back inside the declared viewBox, keeping a 40px "
        "margin. Do not widen the canvas to accommodate it."
    ),
    SD_TEXT_FIT: (
        "Shorten the label or widen its box. Arial at font-size F fits about "
        "W / (0.55 x F) characters in W px — compute it before writing the text."
    ),
    SD_MEASURABLE: (
        "Rewrite this without rotate/matrix/scale transforms or <use>: group "
        "with <g transform=\"translate(dx,dy)\"> only."
    ),
    SD_TYPE: "Pick the SD-TYPE that fits this idea and draw the form it calls for.",
    SD_PALETTE: "Use the assigned palette's roles to distinguish what shapes mean.",
    SD_DENSITY: "Rebalance: specific labels on shapes, not paragraphs in a frame.",
    # SD-DEPTH is now one advisory and one HARD code, and the hard one needs the
    # *opposite* instruction from the advisory one — "add gradients" against
    # "take this gradient off". Naming only the advisory fix would tell a model
    # whose line is invisible *because* of a gradient to add more of them
    # (rule 24, and rule 26's shape: the spec asked for gradients everywhere and
    # a stroked one silently deletes the element).
    SD_DEPTH: (
        "Gradients are for FILLS. If a stroke references one, replace it with a "
        "flat palette hex — a gradient stroked on a line that is flat along the "
        "ramp's axis renders completely invisible. Otherwise: give the primary "
        "shapes a two-stop <linearGradient> and the key surface a white "
        "<radialGradient> sheen; depth is an offset translucent copy, never a "
        "<filter>."
    ),
    # Two hard codes share this rule and BOTH fixes are named, because they are
    # different edits: adding a missing declaration, or correcting a name that is
    # not in the table. A single "declare an archetype" sentence would leave a
    # model that already wrote `<!-- archetype: bathtub -->` with nothing to do
    # (rule 24 — the retry message must be fixable by the thing it names).
    SD_STRUCTURE: (
        "Add `<!-- archetype: NAME -->` as the first line inside <svg>, or change "
        "the name you declared to one from the SD-TYPE table. Then check the "
        "drawing really is that form — and place every shape and label inside one "
        "SD-STRUCTURE cell rather than at coordinates you chose."
    ),
    # Two shapes under one rule, so the text has to name both, and both are now hard:
    # REVEAL_WITHOUT_FREEZE is a reveal that undoes itself, STATIC_STRUCTURE is a build
    # that only moved the decorations. Rule 24 — the instruction must be fixable by the
    # thing it names, which is why "stage the structure" is spelled out as *what goes
    # inside one group* rather than "add more animation".
    SD_MOTION: (
        'Add fill="freeze" to every reveal <animate>, or the element snaps back to '
        "opacity 0 and disappears permanently. And stage the STRUCTURE, not the "
        "trimmings: each teaching step's shape, label and connector go together "
        'inside one <g opacity="0"> with an increasing `begin`, so the figure '
        "assembles in the order the lesson explains it. A diagram whose frame and "
        "cards are all on screen at t=0 reads as static however many chips fade in."
    ),
}


def _geometry_feedback(findings) -> str:
    """Group hard findings by spec rule and pair each group with its fix."""
    order: list[str] = []
    grouped: dict[str, list[str]] = {}
    for finding in findings:
        if finding.rule_id not in grouped:
            order.append(finding.rule_id)
            grouped[finding.rule_id] = []
        grouped[finding.rule_id].append(finding.message)

    parts = []
    for rule_id in order:
        messages = grouped[rule_id]
        # Cap per rule, not overall, so one noisy rule cannot crowd out another.
        shown = "; ".join(messages[:4])
        more = f" (+{len(messages) - 4} more)" if len(messages) > 4 else ""
        fix = _FIX_BY_RULE.get(rule_id, "Fix the geometry this describes.")
        parts.append(f"[{rule_id}] {shown}{more} → {fix}")
    return "\n".join(parts)


def _geometry_check(svg_content: str) -> tuple[list, str, str]:
    """Run both gates. Returns (hard_findings, retry_feedback, advisory_notes).

    Hard findings drive the retry; advisory findings go to the reviewer as context
    and are scored under CRAFT/DENSITY. Keeping them out of the retry feedback is
    deliberate — they are matters of judgement, and a false retry trigger costs a
    full generate+review cycle.
    """
    report = detect_overlaps(svg_content)
    if not report.gate_ran:
        # Rule 21: a gate that cannot run must never pass silently. Fail *open* on
        # broken infrastructure (a malformed SVG is already caught by
        # _validate_svg), but say so on the way past.
        print(f"      ⚠️  SVG_GEOMETRY_UNAVAILABLE: {report.error}")
        return [], "", ""

    craft = craft_findings(svg_content) + motion_findings(svg_content)
    hard = report.hard + [f for f in craft if f.severity == HARD]
    advisory = report.advisory + [f for f in craft if f.severity != HARD]

    notes = "\n".join(f"- [{f.rule_id}] {f.message}" for f in advisory)
    return hard, (_geometry_feedback(hard) if hard else ""), notes


def _detect_overlaps(svg_content: str) -> tuple[bool, str]:
    """Back-compatible boolean form of `_geometry_check`."""
    hard, feedback, _ = _geometry_check(svg_content)
    return bool(hard), feedback or "OK"



def _autofit_viewbox(svg_content: str) -> str:
    """Expand the canvas only if content overflows it; never rewrite from scratch."""
    fitted, _ = autofit_viewbox(svg_content)
    return fitted



def _extract_svg(raw: str) -> str:
    """Extract the <svg>...</svg> content from LLM response, stripping wrappers."""
    raw = raw.strip()
    # Remove markdown code fences
    if "```" in raw:
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    # Find <svg...>...</svg>
    match = re.search(r'(<svg[\s\S]*?</svg>)', raw, re.IGNORECASE)
    if match:
        return match.group(1)
    return raw


# ---------------------------------------------------------------------------
# SVG Review (LLM judge)
# ---------------------------------------------------------------------------

def parse_review_response(
    response: str, *, has_excerpt: bool
) -> tuple[int | None, str, int]:
    """Parse a reviewer response into (score, issues, grounding). Pure — no network.

    Split out of `_review_svg` so it can be tested at all. While the parse was welded
    to the Bedrock call, the only way to exercise it was to spend an LLM call, so it
    had no cases — and it was carrying the inverted implication documented below.
    """
    # Robustly extract the OVERALL score. Handles many formats the model may emit:
    #   "OVERALL: 8", "**OVERALL:** 8", "Overall - 8/10", "Overall score: 8", etc.
    score = None
    overall_match = re.search(
        r'overall[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)',
        response,
        re.IGNORECASE,
    )
    if overall_match:
        try:
            score = round(float(overall_match.group(1)))
        except (ValueError, TypeError):
            score = None

    # Fallback: average the dimension scores if OVERALL wasn't parseable
    if score is None:
        dims = []
        # Must list EVERY dimension the review prompt asks for, or the average
        # silently drops the missing ones and skews toward the rest.
        for dim in (
            "relevance", "clarity", "labels", "accuracy", "grounding", "layout",
            "craft", "density", "polish",
        ):
            m = re.search(rf'{dim}[^0-9]{{0,20}}([0-9]+(?:\.[0-9]+)?)', response, re.IGNORECASE)
            if m:
                try:
                    dims.append(float(m.group(1)))
                except (ValueError, TypeError):
                    pass
        # Fewer than 3 dimensions means the response was not a review at all —
        # averaging 1 stray number is not a judgement.
        if len(dims) >= 3:
            score = round(sum(dims) / len(dims))

    # Rule 21: a gate that cannot run must never pass silently. This used to
    # default to 7 — a borderline PASS — so an unparseable review shipped the
    # diagram unjudged. Say so and let the caller retry instead.
    if score is None:
        print("      ⚠️  REVIEW_UNAVAILABLE: no parseable score in review response")

    # Extract issues (robust to markdown prefixes)
    issues = ""
    issues_match = re.search(r'issues?[:\-]\s*(.+)', response, re.IGNORECASE)
    if issues_match:
        issues = issues_match.group(1).strip().strip("*").strip()

    # GROUNDING — a hard gate, parsed separately from the average. Only meaningful when
    # a lesson excerpt was supplied; otherwise there is nothing to be unfaithful to.
    grounding = 10
    if has_excerpt:
        g_match = re.search(
            r'grounding[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)', response, re.IGNORECASE
        )
        if g_match:
            try:
                grounding = round(float(g_match.group(1)))
            except (ValueError, TypeError):
                grounding = 10
        else:
            # The verdict clamp is a FALLBACK for a garbled numeric line, and ONLY
            # that. It reads the review's *overall* VERDICT, and the prompt's rule is
            # one-directional — "if Grounding < 7, VERDICT is FAIL"
            # (`svg_generate.py:151`). Treating a FAIL as evidence of a grounding
            # problem affirms the consequent: a faithful diagram with flat fills and
            # wordy labels scores 6 overall, emits FAIL for that reason, and used to
            # be relabelled a grounding failure.
            #
            # Measured on the real run in /tmp/full_probe.log, which is what found
            # this: grounding came back as *exactly* 6 on 10 of 12 attempts across
            # three independent figures. 6 is `REVIEW_THRESHOLD - 1`, i.e. the clamp,
            # not a judgement — a model's own opinion does not land on one integer ten
            # times. The cost was not cosmetic. Because the hard gate at the top of
            # the loop `continue`s *before* the ranking key is computed, every clamped
            # candidate was discarded rather than ranked:
            #   * figure 0's attempt 4 was geometry CLEAN and was thrown away; the
            #     only survivor was attempt 3, which shipped with STATIC_STRUCTURE,
            #     TEXT_OVERFLOWS_RECT and TEXT_SPILL — the flat, overlapping diagram.
            #   * figure 1 had all four attempts clamped, so `best_svg` was never set
            #     and it shipped through the `any_valid_svg` fallback, ranking bypassed.
            #   * figure 2 scored 8, so it alone kept its real grounding and took the
            #     designed path — and it is the one figure that renders well.
            # Rule 24 exactly, one level up: a gate placed before the ranking silently
            # replaces it. And the retry text it triggers ("the diagram shows facts
            # that are NOT in the lesson … regenerate using ONLY the lesson's own
            # examples") is unfixable by the thing it names, which is the same rule's
            # second half — three of figure 0's four attempts were told to fix
            # grounding while its actual defect was that nothing was staged.
            #
            # Confirmed by one real Bedrock call against the diagram that shipped, rather
            # than left as an inference from the log: the reviewer emits
            # `GROUNDING: 9` alongside `VERDICT: FAIL` (failing it for craft — "a single
            # pulsing dot with 0 opacity most of the time", "60/68 shapes are circles",
            # a title spanning 60% of canvas width). Old code returned 6 for that
            # response; this returns 9.
            v_match = re.search(r'verdict[^a-z]{0,10}(pass|fail)', response, re.IGNORECASE)
            if v_match and v_match.group(1).lower() == "fail":
                grounding = min(grounding, REVIEW_THRESHOLD - 1)
                # Say which of the two produced the number. Without this the log prints
                # `grounding 6/10` for both "the model judged it unfaithful" and "the
                # model never gave a number and we assumed the worst" — and it was
                # exactly that ambiguity which let the inverted clamp hide in plain
                # sight across three figures and twelve attempts (rule 21).
                print(
                    "      ⚠️  GROUNDING_ASSUMED: the review gave no numeric GROUNDING "
                    f"line, and its overall VERDICT was FAIL — assuming "
                    f"{REVIEW_THRESHOLD - 1}/10 rather than passing it unmeasured"
                )

    return score, issues, grounding


async def _review_svg(
    svg_content: str,
    concept: str,
    context: str,
    model: str,
    lesson_excerpt: str = "",
    craft_notes: str = "",
) -> tuple[int | None, str, int]:
    """Ask LLM to review the SVG. Returns (score, issues_string, grounding).

    `score` is None when the review is unusable — see the REVIEW_UNAVAILABLE branch.
    `grounding` is 10 when no lesson excerpt was supplied (nothing to check against),
    so callers can gate on it unconditionally.
    """
    prompt = build_svg_review_prompt(
        svg_content, concept, context, lesson_excerpt, craft_notes=craft_notes
    )
    response = await _llm_call_async(prompt, model)
    return parse_review_response(response, has_excerpt=bool(lesson_excerpt.strip()))


# ---------------------------------------------------------------------------
# Single SVG generator (reusable — called by tool or resolve_svgs)
# ---------------------------------------------------------------------------

async def generate_one_svg(
    concept: str,
    context: str,
    lesson_excerpt: str = "",
    model: str = DEFAULT_MODEL,
    *,
    max_attempts: int = MAX_ATTEMPTS,
) -> str:
    """Generate ONE validated, reviewed, autofit SVG. Returns <svg> markup or ''.

    `lesson_excerpt` is the verbatim lesson text the diagram must be faithful to. When
    supplied, the reviewer's GROUNDING score acts as a hard gate: a diagram showing
    values absent from the lesson is never promoted to `best_svg`, however polished.

    Candidates are ranked by `(0 if geometry-clean else 1, -score)` — clean beats
    flagged, and within each group the higher review score wins. Geometry findings
    therefore *inform* the ranking without skipping the judge: previously a flagged
    candidate short-circuited the review and was pinned at a hardcoded 3, so the
    first flawed draft beat every later one regardless of quality.
    """
    feedback = None
    best_svg = None
    best_key: tuple[int, float] | None = None
    any_valid_svg = None
    flagged_reviews = 0

    for attempt in range(1, max_attempts + 1):
        gen_prompt = build_svg_generation_prompt(
            concept=concept,
            context=context,
            lesson_excerpt=lesson_excerpt,
            feedback=feedback,
        )
        raw_response = await _llm_call_async(gen_prompt, model)
        svg_content = _extract_svg(raw_response)

        valid, reason = _validate_svg(svg_content)
        if not valid:
            feedback = f"Validation failed: {reason}. Fix the SVG structure."
            continue

        if any_valid_svg is None:
            any_valid_svg = svg_content

        hard_findings, geometry_feedback, craft_notes = _geometry_check(svg_content)
        if hard_findings:
            geometry_note = (
                "A geometric checker measured every text and shape box exactly "
                "and found these design-spec violations. Each is followed by the "
                f"fix it needs:\n{geometry_feedback}"
            )
        else:
            geometry_note = ""

        # A flagged candidate is still reviewed — its score is what decides which
        # flawed draft to keep — but only while the budget lasts. Past that, the
        # geometry feedback alone drives the retry and no review call is spent.
        if hard_findings and flagged_reviews >= FLAGGED_REVIEW_BUDGET:
            print(
                f"      ⏭️  review skipped (attempt {attempt}): "
                f"{len(hard_findings)} geometry finding(s), budget spent"
            )
            if best_key is None:
                best_svg, best_key = svg_content, (1, 0.0)
            feedback = geometry_note
            continue
        if hard_findings:
            flagged_reviews += 1

        score, issues, grounding = await _review_svg(
            svg_content, concept, context, model, lesson_excerpt,
            craft_notes=craft_notes,
        )

        # One line per attempt, so a run's transcript shows whether the judge actually
        # ran and where the loop stopped. Without it, "resolved 2/2" is silent about
        # whether reviews happened at all — the exact ambiguity Phase 2 was fixing.
        print(
            f"      🔎 attempt {attempt}: geometry "
            f"{'clean' if not hard_findings else f'{len(hard_findings)} finding(s)'}, "
            f"review {'n/a' if score is None else f'{score}/10'}, grounding {grounding}/10"
        )

        # HARD GATE: an ungrounded diagram invents facts that contradict the lesson.
        # Never let it become the chosen candidate — retry with the specifics instead.
        # (It stays reachable via any_valid_svg, so we still ship something rather
        # than an empty diagram if every attempt fails.)
        if grounding < REVIEW_THRESHOLD:
            feedback = (
                f"GROUNDING FAILURE ({grounding}/10) — the diagram shows facts that are NOT "
                f"in the lesson: {issues}. Every label and value must come from the LESSON "
                "EXCERPT verbatim. Use generic role names where the lesson gives no concrete "
                "value. Regenerate using ONLY the lesson's own examples."
            )
            continue

        if score is None:
            # REVIEW_UNAVAILABLE (already logged). Never count this as a pass. Keep the
            # candidate reachable so a parse miss can't ship an empty diagram, but rank
            # it below anything actually judged.
            if best_key is None:
                best_svg, best_key = svg_content, (1 if hard_findings else 0, 0.0)
            feedback = (
                "The previous review could not be parsed. Regenerate the diagram, "
                "applying the design spec in full."
            ) if not geometry_note else geometry_note
            continue

        key = (1 if hard_findings else 0, -float(score))
        if best_key is None or key < best_key:
            best_svg, best_key = svg_content, key

        # Only a clean *and* well-scored candidate ends the loop. A high score on
        # flagged geometry is not a pass — the linter's findings are ground truth.
        if score >= REVIEW_THRESHOLD and not hard_findings:
            break

        review_note = f"Review score {score}/10. Issues: {issues}. Fix and regenerate."
        feedback = f"{geometry_note}\n\n{review_note}" if geometry_note else review_note

    final_svg = best_svg or any_valid_svg
    if not final_svg:
        return ""
    shipped = _autofit_viewbox(final_svg)

    # A diagram that still carries hard findings after every attempt SHIPS — an
    # empty figure is worse than a flawed one, and the SVG floor depends on this
    # returning markup. But it must not ship *quietly*, which is what happened: a
    # diagram whose labels demonstrably collided was ranked second, shipped, and
    # the only trace was a per-attempt line buried in a concurrent log. Rule 31's
    # corollary — a verdict computed and then not surfaced is not a gate — and
    # rule 21's: fail-open is a legitimate choice, fail-open silently is not.
    #
    # Measured on the bytes that ship, AFTER autofit, not on `best_svg`: autofit
    # rewrites the viewBox, so it is the only thing that can decide
    # CONTENT_OUTSIDE_CANVAS either way (rule 29 — validate the artifact the
    # student reads). Re-derived here rather than carried from the loop for the
    # same reason, and it costs no LLM call.
    #
    # Deliberately a print and not an exception: this audits a candidate we have
    # already chosen to keep, and aborting a five-hour run over one label
    # collision is the wrong trade (rule 31 — fail-open vs fail-closed is
    # per-path). The `any_valid_svg` fallback is covered too, since that path
    # never set `best_key` and would otherwise report nothing at all.
    hard_findings, _, _ = _geometry_check(shipped)
    if hard_findings:
        codes = ", ".join(sorted({f.code for f in hard_findings}))
        print(
            f"      ⚠️  SVG-SHIPPED-FLAGGED: '{concept[:60]}' ships with "
            f"{len(hard_findings)} unresolved geometry finding(s) after "
            f"{max_attempts} attempts — {codes}"
        )

    return shipped


# ---------------------------------------------------------------------------
# Lesson-context extraction
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_CODE_EL_RE = re.compile(r"<Code\b[^>]*>([\s\S]*?)</Code>", re.IGNORECASE)
_FENCE_RE = re.compile(r"```[\s\S]*?```")
MAX_EXCERPT_CHARS = 2000


def _extract_lesson_excerpt(content: str, placeholder_start: int) -> str:
    """Pull the lesson text a placeholder sits after, as grounding for the diagram.

    Placeholders are emitted between `</Section>` and the next `<Section>`, so the
    relevant material is the preceding <Section> block. MLAI tags are stripped, but code
    is preserved verbatim — the code IS the lesson's concrete example, and losing it is
    what let the generator invent its own values.

    Code appears two ways and both must survive: `<Code>` elements, and markdown ```
    fences inside `<Body>`. Fenced regions are masked out before tag-stripping, otherwise
    the stripper eats the HTML *inside* them (`<div class="banner">` → `banner`).

    Returns "" if no preceding section can be found (nothing to ground against).
    """
    prev_open = content.rfind("<Section", 0, placeholder_start)
    if prev_open == -1:
        return ""

    prev_close = content.rfind("</Section>", 0, placeholder_start)
    if prev_close > prev_open:
        # Placeholder sits AFTER a closed section — take that whole section.
        segment = content[prev_open:prev_close]
    else:
        # Placeholder sits INSIDE an open section — take what's been written so far.
        segment = content[prev_open:placeholder_start]

    # Normalise <Code> elements into fences so both forms are handled identically.
    segment = _CODE_EL_RE.sub(lambda m: f"\n```\n{m.group(1).strip()}\n```\n", segment)

    # Mask fenced code, strip MLAI tags from the prose only, then restore the code.
    fences: list[str] = []

    def _mask(m: re.Match) -> str:
        fences.append(m.group(0))
        return f"\x00FENCE{len(fences) - 1}\x00"

    segment = _FENCE_RE.sub(_mask, segment)
    text = _TAG_RE.sub("", segment)
    for i, block in enumerate(fences):
        text = text.replace(f"\x00FENCE{i}\x00", block)

    # Collapse the blank-line runs left behind by stripped tags.
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln)
    excerpt = "\n".join(out).strip()

    if len(excerpt) > MAX_EXCERPT_CHARS:
        # Keep the TAIL — the text nearest the placeholder is the most relevant.
        excerpt = "..." + excerpt[-MAX_EXCERPT_CHARS:]
    return excerpt


# ---------------------------------------------------------------------------
# Main resolver (fallback path — Stage 2 generates in-agent instead)
# ---------------------------------------------------------------------------

async def resolve_svgs(mlai_path: Path, model: str = DEFAULT_MODEL, verbose: bool = True) -> int:
    """Resolve all <Svg concept="..." context="..." /> placeholders in an .mlai file.

    Placeholders are resolved CONCURRENTLY (each is an independent generate/review
    loop), then spliced back in reverse document order so earlier offsets stay valid.

    Each placeholder goes through `generate_one_svg`, which validates structure, checks
    overlaps geometrically, reviews quality, and enforces the grounding gate against the
    surrounding lesson text.

    Returns the number of SVGs successfully resolved.
    """
    if not mlai_path.exists():
        if verbose:
            print(f"   ⚠️ File not found: {mlai_path}")
        return 0

    content = mlai_path.read_text(encoding="utf-8")
    # Find all <Svg ...> tags, then keep only those that have a concept= attr
    # (i.e. unresolved placeholders — not already-embedded <Svg>...</svg> blocks).
    placeholders = [
        m for m in _SVG_TAG_RE.finditer(content)
        if _CONCEPT_ATTR_RE.search(m.group(1))
    ]

    if not placeholders:
        if verbose:
            # Report embedded SVGs, not just "no placeholders" — the old wording read
            # like "this lesson has no SVGs" when it actually means the opposite:
            # the in-agent generate_svg tool already embedded them, so this
            # post-step has nothing left to resolve.
            embedded = content.count("<svg")
            if embedded:
                print(f"   🎨 {embedded} SVG(s) already embedded in {mlai_path.name} — nothing to resolve")
            else:
                print(f"   ⚠️  {mlai_path.name} contains NO SVGs (none embedded, no placeholders to resolve)")
        return 0

    if verbose:
        print(f"   🎨 Found {len(placeholders)} SVG placeholder(s) to resolve...")

    # Build the work list in document order, capturing the lesson text each diagram
    # must be faithful to. Offsets are read from the ORIGINAL content, before any
    # splicing, so they all stay valid.
    jobs = []
    for match in placeholders:
        attrs = match.group(1)
        concept_m = _CONCEPT_ATTR_RE.search(attrs)
        context_m = _CONTEXT_ATTR_RE.search(attrs)
        jobs.append({
            "match": match,
            "concept": concept_m.group(1) if concept_m else "",
            "context": context_m.group(1) if context_m else "",
            "excerpt": _extract_lesson_excerpt(content, match.start()),
        })

    if verbose:
        for j in jobs:
            print(f"      📐 {j['concept'][:60]}...  (excerpt: {len(j['excerpt'])} chars)")
        print(f"      ⏳ Generating {len(jobs)} SVG(s) concurrently...")

    # Each placeholder is an independent generate/review loop — run them together.
    results = await asyncio.gather(
        *[
            generate_one_svg(
                concept=j["concept"],
                context=j["context"],
                lesson_excerpt=j["excerpt"],
                model=model,
            )
            for j in jobs
        ],
        return_exceptions=True,
    )

    resolved_count = 0

    # Splice in REVERSE document order so earlier offsets remain valid.
    for j, result in reversed(list(zip(jobs, results))):
        match = j["match"]

        if isinstance(result, BaseException):
            if verbose:
                print(f"      ⚠️ {j['concept'][:40]}: {type(result).__name__}: {result}")
            final_svg = ""
        else:
            final_svg = result

        if final_svg:
            # generate_one_svg already autofits the viewBox.
            embedded = f"  <Svg>\n{final_svg}\n  </Svg>"
            content = content[:match.start()] + embedded + content[match.end():]
            resolved_count += 1
        else:
            # All attempts produced unparseable garbage — drop rather than ship a
            # broken placeholder into the lesson.
            if verbose:
                print(f"      ⚠️ All attempts failed — removing placeholder")
            content = content[:match.start()] + content[match.end():]

    # Write back
    mlai_path.write_text(content, encoding="utf-8")

    if verbose:
        print(f"\n   🎨 Resolved {resolved_count}/{len(placeholders)} SVGs")

    return resolved_count
