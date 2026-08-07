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
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

from config import PROJECT_ROOT
from prompts.svg_generate import build_svg_generation_prompt, build_svg_review_prompt



# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_ATTEMPTS = 4  # generate/review retries — extra attempt helps fix overlaps
REVIEW_THRESHOLD = 7  # score >= 7 = accept
# Bedrock inference-profile model ID (Claude via Amazon Bedrock)
DEFAULT_MODEL = "global.anthropic.claude-sonnet-5"

# Match any <Svg ...> placeholder tag (self-closing or not), multi-line safe.
# We match the whole tag, then extract concept/context attributes separately
# so attribute ORDER, line breaks, and a missing context= all work.
_SVG_TAG_RE = re.compile(r'<Svg\b([^>]*?)/?>', re.IGNORECASE | re.DOTALL)
_CONCEPT_ATTR_RE = re.compile(r'concept\s*=\s*"([^"]*)"', re.IGNORECASE | re.DOTALL)
_CONTEXT_ATTR_RE = re.compile(r'context\s*=\s*"([^"]*)"', re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# LLM Helpers (via Claude Agent SDK — handles Foundry automatically)
# ---------------------------------------------------------------------------

async def _llm_call_async(prompt: str, model: str) -> str:
    """Make a single LLM call via the Agent SDK and return the text response.

    Uses the Agent SDK (same as the main lesson agent) so Foundry auth
    works automatically. No tools needed — just a plain text completion.
    """
    opts = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        model=model,
        max_turns=2,
        cwd=str(PROJECT_ROOT),
    )
    text_parts: list[str] = []
    async for message in query(prompt=prompt, options=opts):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
    return "".join(text_parts)




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
# Geometric Overlap Detection (code — free, deterministic, no LLM)
# ---------------------------------------------------------------------------

# Local tag (strip SVG namespace like {http://www.w3.org/2000/svg}rect -> rect)
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _to_float(v, default=0.0):
    try:
        # Strip units like "px"
        return float(str(v).replace("px", "").strip())
    except (ValueError, TypeError, AttributeError):
        return default


def _boxes_overlap(a, b, margin: float = 0.0) -> float:
    """Return overlap area of two boxes (x1,y1,x2,y2), shrunk by margin. >0 = overlap."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1) + margin
    iy1 = max(ay1, by1) + margin
    ix2 = min(ax2, bx2) - margin
    iy2 = min(ay2, by2) - margin
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return (ix2 - ix1) * (iy2 - iy1)


def _contains(outer, inner) -> bool:
    """True if box `outer` fully contains box `inner` (label inside its own box)."""
    return (
        outer[0] <= inner[0] and outer[1] <= inner[1]
        and outer[2] >= inner[2] and outer[3] >= inner[3]
    )


def _element_boxes(svg_content: str):
    """Return lists of (kind, box, label) for shapes and texts in the SVG.

    box = (x1, y1, x2, y2). Text width is estimated from char count × font size.
    """
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError:
        return [], [], None

    # viewBox for bounds checking
    vb = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    bounds = None
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            bx, by, bw, bh = (_to_float(p) for p in parts)
            bounds = (bx, by, bx + bw, by + bh)

    shapes = []  # (kind, box)
    texts = []   # (box, label)

    for el in root.iter():
        tag = _local(el.tag)
        a = el.attrib

        if tag == "rect":
            x, y = _to_float(a.get("x")), _to_float(a.get("y"))
            w, h = _to_float(a.get("width")), _to_float(a.get("height"))
            if w > 0 and h > 0:
                shapes.append(("rect", (x, y, x + w, y + h)))
        elif tag == "circle":
            cx, cy, r = _to_float(a.get("cx")), _to_float(a.get("cy")), _to_float(a.get("r"))
            if r > 0:
                shapes.append(("circle", (cx - r, cy - r, cx + r, cy + r)))
        elif tag == "ellipse":
            cx, cy = _to_float(a.get("cx")), _to_float(a.get("cy"))
            rx, ry = _to_float(a.get("rx")), _to_float(a.get("ry"))
            if rx > 0 and ry > 0:
                shapes.append(("ellipse", (cx - rx, cy - ry, cx + rx, cy + ry)))
        elif tag == "text":
            label = "".join(el.itertext()).strip()
            if not label:
                continue
            x, y = _to_float(a.get("x")), _to_float(a.get("y"))
            fs = _to_float(a.get("font-size"), 16.0)
            if fs <= 0:
                fs = 16.0
            # Estimate text width: chars × avg glyph width (~0.6 em). Add safety.
            w = len(label) * fs * 0.62
            h = fs * 1.2
            anchor = (a.get("text-anchor") or "start").lower()
            if anchor == "middle":
                x1 = x - w / 2
            elif anchor == "end":
                x1 = x - w
            else:
                x1 = x
            # SVG text y is the baseline; box spans ~0.8em above, 0.3em below.
            y1 = y - fs * 0.8
            texts.append(((x1, y1, x1 + w, y1 + h), label))

    return shapes, texts, bounds


def _autofit_viewbox(svg_content: str, padding: float = 50.0) -> str:
    """Recompute the viewBox to wrap ALL content with padding. Guarantees nothing is clipped."""
    shapes, texts, _ = _element_boxes(svg_content)
    if not shapes and not texts:
        return svg_content  # can't compute — leave as-is

    all_boxes = [b for _, b in shapes] + [b for b, _ in texts]
    min_x = min(b[0] for b in all_boxes) - padding
    min_y = min(b[1] for b in all_boxes) - padding
    max_x = max(b[2] for b in all_boxes) + padding
    max_y = max(b[3] for b in all_boxes) + padding
    w = max_x - min_x
    h = max_y - min_y

    # Replace viewBox attribute in the SVG
    new_vb = f'viewBox="{min_x:.0f} {min_y:.0f} {w:.0f} {h:.0f}"'
    svg_content = re.sub(r'viewBox="[^"]*"', new_vb, svg_content, count=1, flags=re.IGNORECASE)
    return svg_content


def _detect_overlaps(svg_content: str, margin: float = 4.0) -> tuple[bool, str]:
    """Detect overlapping elements geometrically. Returns (has_overlap, reason).

    Checks:
      - text vs text (worst for readability)
      - text vs shape it is NOT contained in (label spilling onto unrelated shape)
      - shape vs shape (partial overlap; full containment is allowed = nesting)
      - elements outside the viewBox bounds
    """
    shapes, texts, bounds = _element_boxes(svg_content)
    issues: list[str] = []

    def fmt(box):
        return f"({box[0]:.0f},{box[1]:.0f})-({box[2]:.0f},{box[3]:.0f})"

    # 1) text vs text
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if _boxes_overlap(texts[i][0], texts[j][0], margin) > 0:
                issues.append(
                    f"Text '{texts[i][1][:20]}' {fmt(texts[i][0])} overlaps "
                    f"text '{texts[j][1][:20]}' {fmt(texts[j][0])}"
                )

    # 2) text vs shape (only if the text is NOT inside that shape)
    for tbox, tlabel in texts:
        for kind, sbox in shapes:
            if _contains(sbox, tbox):
                continue  # label sits inside its box — fine
            if _boxes_overlap(tbox, sbox, margin) > 0:
                # Only flag significant spill (>25% of text area)
                area = max(1.0, (tbox[2] - tbox[0]) * (tbox[3] - tbox[1]))
                if _boxes_overlap(tbox, sbox) / area > 0.25:
                    issues.append(
                        f"Text '{tlabel[:20]}' {fmt(tbox)} overlaps {kind} {fmt(sbox)}"
                    )

    # 3) shape vs shape (partial overlap, not full nesting)
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            a, b = shapes[i][1], shapes[j][1]
            if _contains(a, b) or _contains(b, a):
                continue  # nesting is allowed
            if _boxes_overlap(a, b, margin) > 0:
                issues.append(
                    f"{shapes[i][0]} {fmt(a)} overlaps {shapes[j][0]} {fmt(b)}"
                )

    # 4) out of bounds
    if bounds:
        for kind, sbox in shapes:
            if sbox[0] < bounds[0] - 2 or sbox[1] < bounds[1] - 2 or sbox[2] > bounds[2] + 2 or sbox[3] > bounds[3] + 2:
                issues.append(f"{kind} {fmt(sbox)} extends outside canvas {fmt(bounds)}")
        for tbox, tlabel in texts:
            if tbox[0] < bounds[0] - 2 or tbox[2] > bounds[2] + 2 or tbox[1] < bounds[1] - 2 or tbox[3] > bounds[3] + 2:
                issues.append(f"Text '{tlabel[:20]}' {fmt(tbox)} is clipped at canvas edge")

    if issues:
        # Cap the list so feedback stays focused
        shown = issues[:6]
        more = f" (+{len(issues) - 6} more)" if len(issues) > 6 else ""
        return True, "; ".join(shown) + more
    return False, "OK"


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

async def _review_svg(svg_content: str, concept: str, context: str, model: str) -> tuple[int, str]:
    """Ask LLM to review the SVG. Returns (score, issues_string)."""
    prompt = build_svg_review_prompt(svg_content, concept, context)
    response = await _llm_call_async(prompt, model)

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

    # Fallback: average the 4 dimension scores if OVERALL wasn't parseable
    if score is None:
        dims = []
        for dim in ("relevance", "clarity", "labels", "accuracy", "layout"):
            m = re.search(rf'{dim}[^0-9]{{0,20}}([0-9]+(?:\.[0-9]+)?)', response, re.IGNORECASE)
            if m:
                try:
                    dims.append(float(m.group(1)))
                except (ValueError, TypeError):
                    pass
        if dims:
            score = round(sum(dims) / len(dims))

    # Last resort: if we truly can't parse a score, treat as borderline-pass (7)
    # rather than 0 — a validated SVG shouldn't be discarded due to a parse miss.
    if score is None:
        score = 7

    # Extract issues (robust to markdown prefixes)
    issues = ""
    issues_match = re.search(r'issues?[:\-]\s*(.+)', response, re.IGNORECASE)
    if issues_match:
        issues = issues_match.group(1).strip().strip("*").strip()

    return score, issues


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

async def resolve_svgs(mlai_path: Path, model: str = DEFAULT_MODEL, verbose: bool = True) -> int:
    """Resolve all <Svg concept="..." context="..." /> placeholders in an .mlai file.

    For each placeholder:
      1. Generate SVG from concept+context
      2. Validate structure (code)
      3. Review quality (LLM judge)
      4. Regenerate on feedback (up to MAX_ATTEMPTS)
      5. Embed final SVG or remove placeholder if all fail

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
            print(f"   🎨 No SVG placeholders found in {mlai_path.name}")
        return 0

    if verbose:
        print(f"   🎨 Found {len(placeholders)} SVG placeholder(s) to resolve...")

    resolved_count = 0

    for match in reversed(placeholders):  # Reverse to preserve positions
        attrs = match.group(1)
        concept_m = _CONCEPT_ATTR_RE.search(attrs)
        context_m = _CONTEXT_ATTR_RE.search(attrs)
        concept = concept_m.group(1) if concept_m else ""
        context = context_m.group(1) if context_m else ""

        if verbose:
            print(f"\n      📐 Generating SVG for: '{concept[:50]}...'")

        # Best-of-N loop: NEVER DROP — always embed the best SVG seen.
        # Track all valid+overlap-free candidates with their scores.
        feedback = None
        best_svg = None
        best_score = -1
        any_valid_svg = None  # fallback: first valid SVG (even if score low)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if verbose:
                print(f"         Attempt {attempt}/{MAX_ATTEMPTS}...", end=" ")

            # GENERATE
            gen_prompt = build_svg_generation_prompt(
                concept=concept,
                context=context,
                feedback=feedback,
            )
            raw_response = await _llm_call_async(gen_prompt, model)
            svg_content = _extract_svg(raw_response)

            # VALIDATE (code)
            valid, reason = _validate_svg(svg_content)
            if not valid:
                if verbose:
                    print(f"❌ validate: {reason}")
                feedback = f"Validation failed: {reason}. Fix the SVG structure."
                continue

            # Track first valid SVG as ultimate fallback
            if any_valid_svg is None:
                any_valid_svg = svg_content

            # OVERLAP CHECK (code — deterministic geometry)
            has_overlap, overlap_reason = _detect_overlaps(svg_content)
            if has_overlap:
                if verbose:
                    print(f"❌ overlap: {overlap_reason[:70]}")
                feedback = (
                    "The diagram has OVERLAPPING elements (detected geometrically). "
                    f"Fix these exact collisions by repositioning with ≥30px gaps: {overlap_reason}. "
                    "Enlarge boxes to fit their text, spread elements out on the canvas, "
                    "and keep everything within a 40px inner margin."
                )
                # Still track it as a candidate if it's the only one
                if best_svg is None:
                    best_svg = svg_content
                    best_score = 3  # low priority — overlapping fallback
                continue

            # REVIEW (LLM judge — only overlap-free SVGs reach here)
            score, issues = await _review_svg(svg_content, concept, context, model)
            if verbose:
                print(f"score={score}/10", end=" ")

            # Track best overlap-free SVG
            if score > best_score:
                best_svg = svg_content
                best_score = score

            if score >= REVIEW_THRESHOLD:
                if verbose:
                    print("✅ accepted!")
                break
            else:
                if verbose:
                    print(f"↻ issues: {issues[:60]}")
                feedback = f"Review score {score}/10. Issues: {issues}. Fix these and regenerate."

        # ALWAYS EMBED — use best available (never drop, never leave lesson imageless)
        final_svg = best_svg or any_valid_svg
        if final_svg:
            # Auto-fit viewBox to prevent clipping
            final_svg = _autofit_viewbox(final_svg)
            embedded = f"  <Svg>\n{final_svg}\n  </Svg>"
            content = content[:match.start()] + embedded + content[match.end():]
            resolved_count += 1
            if verbose and best_score < REVIEW_THRESHOLD:
                print(f"         ⚠️ Used best available (score={best_score}) — not ideal but guaranteed present")
        else:
            # Truly impossible (all attempts produced unparseable garbage) — extremely rare
            if verbose:
                print(f"         ⚠️ All attempts invalid — removing placeholder")
            content = content[:match.start()] + content[match.end():]

    # Write back
    mlai_path.write_text(content, encoding="utf-8")

    if verbose:
        print(f"\n   🎨 Resolved {resolved_count}/{len(placeholders)} SVGs")

    return resolved_count
