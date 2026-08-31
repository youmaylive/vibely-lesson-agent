"""Choose which game a lesson gets, and build the prompt section that describes it.

Stdlib only, on the `svg_geometry.py` precedent: no SDK import, so this module runs
and tests with no credentials and cannot fail on a dependency missing from the worker
image.

The problem this solves
-----------------------
Everything the agent needs in order to *choose* a game — what the game is, what
content it fits, what its fields mean, what a correct payload looks like — is ~2.2k
tokens per game. Inlining all of it works for one game and is impossible for a
hundred: 100 games is ~220k tokens on every lesson, before the ontology, the MLAI
format guide and the SVG design spec.

So selection is two-stage, and the split is the whole design:

  Stage A (here, deterministic)  narrow the registry to a few candidates, so the
                                 prompt cost is bounded and flat in registry size
  Stage B (the model)            choose one of them, decide where it goes, write the
                                 payload. It chooses *which*, never *whether*:
                                 `LS-GAME-FLOOR` requires exactly one per lesson

Measured on the 2-game registry: catalog 182 + rules 782 tokens always, plus ~2.2k
per candidate spec. Projected at 100 games with MAX_GAME_CANDIDATES=5: ~15k tokens,
and **flat** — the catalog grows by ~32 tokens per game and nothing else does.

Why Stage A can only reorder, never veto
----------------------------------------
The shape inference below is written from reasoning about what lesson specs look
like, not from measurement, and AGENTS.md rule 25 is unambiguous about what that is
worth ("`len(text) × font_size × 0.62` errs +179% on `iiii`"; a `LONG_LINE` rule
written on a character count fired on 110/150 legitimate blocks). So it is built so
that being wrong is cheap:

  * `catalog.md` lists EVERY game and is always in the prompt, so the agent can pick a
    type whose spec was not injected. The cap bounds cost, not capability.
  * When the registry has no more games than the cap, **every** game is a candidate
    and the inference only affects the order they are presented in. That is today's
    state: with 2 games and a cap of 5, a wrong inference changes nothing at all.
  * Above the cap the inference decides whose *spec* is included. The failure mode is
    "the agent picks a game it has less detail about", which the fix loop repairs —
    not a lesson that fails or a game that is unreachable.

`explain()` exists so the decision is inspectable rather than implicit: rule 27's
corollary is that a value computed and never read is not a gate, and a selection
nobody can see is a selection nobody can debug.

Adding a game costs nothing here
--------------------------------
A new game is 4 files in `mlai-games` and `npm run build`. This module reads
`dist/agent-guide/index.json` and never names a game type, so game #100 is selectable
the moment it is registered.

A new *content shape* is the one thing that does cost code: it needs an entry in
`SHAPE_EVIDENCE` below as well as in `schemas/types.ts`. That is why `index.json`
ships the shape vocabulary — `load_guide()` compares it against `SHAPE_EVIDENCE` and
warns loudly about a shape it cannot score, because the alternative is a game that is
registered, valid, documented and silently never chosen.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# One frontmatter parser for the whole pipeline. `budget.py` owns it because it needed it
# first (`duration:`), and it is stdlib-only like this module, so importing it costs
# nothing and a second copy of that anchored regex is what would drift (rule 23).
from budget import frontmatter

# ---------------------------------------------------------------------------
# The guide, as built by mlai-games/scripts/emit-agent-guide.mjs
# ---------------------------------------------------------------------------


@dataclass
class GameEntry:
    """One game, as `index.json` describes it. Mirrors `GameAgentSpec`."""

    type: str
    label: str
    tagline: str
    content_shapes: list[str]
    minutes: int
    gradable: bool
    max_per_lesson: int
    spec_rel: str


@dataclass
class GameGuide:
    """The generated guide: the catalog, the shared rules, and the per-game specs."""

    catalog_md: str
    rules_md: str
    games: list[GameEntry]
    known_shapes: list[str]
    root: Path

    def spec_md(self, game_type: str) -> str:
        """The full spec for one game, read on demand."""
        for game in self.games:
            if game.type == game_type:
                return (self.root / game.spec_rel).read_text(encoding="utf-8")
        raise KeyError(f"no such game type in the guide: {game_type!r}")


class GuideUnavailable(Exception):
    """The generated guide is missing or unreadable.

    Deliberately NOT raised out of `build_game_prompt_section` — see the fail-open
    reasoning there. Callers that want to fail closed can catch this from
    `load_guide` directly.
    """


def load_guide(guide_dir: Path) -> GameGuide:
    """Load the generated guide. Raises `GuideUnavailable` if it is not usable."""
    index_path = guide_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        catalog_md = (guide_dir / "catalog.md").read_text(encoding="utf-8")
        rules_md = (guide_dir / "rules.md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise GuideUnavailable(
            f"could not read the game guide at {guide_dir}: {exc}. "
            f"Run `npm run build` in vibely-v2/mlai-games."
        ) from exc

    games = [
        GameEntry(
            type=g["type"],
            label=g["label"],
            tagline=g["tagline"],
            content_shapes=list(g["contentShapes"]),
            minutes=int(g["minutes"]),
            gradable=bool(g["gradable"]),
            max_per_lesson=int(g.get("maxPerLesson", 1)),
            spec_rel=g["spec"],
        )
        for g in index.get("games", [])
    ]
    if not games:
        raise GuideUnavailable(f"the game guide at {guide_dir} declares no games")

    known_shapes = list(index.get("contentShapes", []))
    # A shape this module cannot score is a game that can never be ranked on its own
    # merits. Loud, because the symptom otherwise is "the model just never picks that
    # game" — indistinguishable from the model exercising judgement.
    unscorable = [s for s in known_shapes if s not in SHAPE_EVIDENCE]
    if unscorable:
        print(
            f"⚠️  GAMES: the registry declares content shape(s) {unscorable} that "
            f"games.py cannot score. Games needing them will rank last and their "
            f"specs may never be injected. Add an entry to SHAPE_EVIDENCE."
        )
    # And the reverse: a shape scored here but no longer in the vocabulary is dead
    # code that quietly does nothing.
    orphaned = [s for s in SHAPE_EVIDENCE if known_shapes and s not in known_shapes]
    if orphaned:
        print(
            f"⚠️  GAMES: games.py scores content shape(s) {orphaned} that the registry "
            f"no longer declares — dead evidence rules."
        )

    return GameGuide(
        catalog_md=catalog_md,
        rules_md=rules_md,
        games=games,
        known_shapes=known_shapes,
        root=guide_dir,
    )


# ---------------------------------------------------------------------------
# Lesson signals
# ---------------------------------------------------------------------------


@dataclass
class LessonSignals:
    """What a lesson spec says about itself, in the shapes a game can consume."""

    title: str = ""
    objectives: list[str] = field(default_factory=list)
    key_concepts: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    outline: list[str] = field(default_factory=list)
    text: str = ""


# Spec headings, as the lesson planner actually emits them. Matched loosely (a
# substring of the lowercased heading) because the planner's wording varies —
# "Key Concepts", "Key Concepts & Terms", "Common Misconceptions".
_SECTION_KEYS = {
    "objectives": ("learning objectives", "objectives"),
    "key_concepts": ("key concepts", "key terms", "vocabulary"),
    "misconceptions": ("common misconceptions", "misconceptions"),
    "outline": ("content outline", "outline", "practical examples"),
}


def _bullets(block: str) -> list[str]:
    """The bullet lines of a markdown block, stripped of their markers."""
    out = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "+ ")):
            out.append(stripped[2:].strip())
        elif re.match(r"^\d+[.)]\s+", stripped):
            out.append(re.sub(r"^\d+[.)]\s+", "", stripped))
    return [b for b in out if b]


# A fenced code block, any fence length ≥3, backticks or tildes. Blanked (newlines
# preserved) before any heading or bullet is read, because a lesson that teaches code
# puts `#` comments and `- ` list lines inside one, and markdown does not treat those as
# structure. This is not hypothetical: the H1 the old code picked up on the neuro
# planner's 89 specs was `# Your attempt here` — a Python comment inside a fence.
_FENCE_RE = re.compile(r"^(?P<f>```+|~~~+)[^\n]*\n.*?^(?P=f)[ \t]*$", re.M | re.S)


def _blank_fences(text: str) -> str:
    return _FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


_FM_TITLE_RE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.M | re.I)
# `concepts:` followed by an indented YAML block list — the shape the planner emits.
# Stops at the first line that is neither a list item nor blank, so the next key
# (`objectives:`, `content_outline:`) cannot be swallowed as a concept.
_FM_CONCEPTS_RE = re.compile(
    r"^concepts:[ \t]*\r?\n((?:[ \t]+-[ \t]*[^\n]*\r?\n?|[ \t]*\r?\n)+)", re.M | re.I
)


def _frontmatter_signals(front: str) -> tuple[str, list[str]]:
    """`(title, concepts)` from a spec's YAML frontmatter.

    The planner writes both, and this reads neither until now — which was the whole
    reason `hangman` could never win. Measured over the 89 real specs in
    `memebu-lesson-planner/output/test_full_pipeline_neuro/`: **89 of 89** declare
    `concepts:` in frontmatter and **0** carry a `## Key Concepts` heading, so
    `key_concepts` was empty on every one of them and `term-recall` — hangman's only
    shape — scored a structural 0.00. The 31 older specs in `test_curriculum/` are the
    exact mirror (31 headings, 0 frontmatter), which is how the gap survived: the
    ranking was tuned on the dialect the planner had already stopped emitting.

    Rule 27's shape, one more time: the value existed and nothing read it.
    """
    if not front:
        return "", []

    title = ""
    match = _FM_TITLE_RE.search(front)
    if match:
        title = match.group(1).strip().strip('"').strip("'").strip()

    concepts: list[str] = []
    block = _FM_CONCEPTS_RE.search(front)
    if block:
        for line in block.group(1).splitlines():
            item = line.strip()
            if item.startswith("-"):
                value = item[1:].strip().strip('"').strip("'").strip()
                if value:
                    concepts.append(value)
    return title, concepts


def extract_signals(spec_text: str) -> LessonSignals:
    """Parse a lesson spec's markdown into the signals games are matched against.

    Structural, not keyword-based, wherever the structure exists: a spec's
    `## Key Concepts` list IS the set of terms the lesson teaches, and its
    `## Common Misconceptions` list IS a set of claims that are false — which is
    exactly the raw material a judgement game needs. Those two are worth more than
    any amount of scanning the prose.

    **Two spec dialects, and both have to work.** The planner writes `title:` and a
    `concepts:` list into YAML frontmatter (89 of 89 specs in the neuro run); the older
    `test_curriculum/` specs write `## Key Concepts` headings instead (31 of 31, with no
    frontmatter at all). Frontmatter is read first and the headings extend it, so a spec
    carrying both contributes both without either dialect being privileged.
    """
    signals = LessonSignals(text=spec_text)

    front = frontmatter(spec_text)
    fm_title, fm_concepts = _frontmatter_signals(front)
    signals.title = fm_title
    signals.key_concepts.extend(fm_concepts)

    # Everything below reads *structure*, so fenced code goes first — see `_blank_fences`
    # for the H1 this was picking up before.
    body_text = _blank_fences(spec_text[len(front) :] if front else spec_text)

    # Title fallback: the first H1 outside a fence, else the first non-empty line.
    if not signals.title:
        for line in body_text.splitlines():
            if line.startswith("# "):
                signals.title = line[2:].strip()
                break
            if line.strip() and line.strip() != "---" and not signals.title:
                signals.title = line.strip()

    # Split on H2/H3 headings and bucket the blocks by what they are called.
    parts = re.split(r"^#{2,3}\s+(.+)$", body_text, flags=re.MULTILINE)
    # parts = [preamble, heading1, body1, heading2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip().lower()
        body = parts[i + 1]
        for attr, needles in _SECTION_KEYS.items():
            if any(n in heading for n in needles):
                getattr(signals, attr).extend(_bullets(body))
                break

    # Frontmatter and a heading can name the same concept. Dedupe case-insensitively,
    # keeping first-seen order, so a term is not scored twice for being written twice.
    seen: set[str] = set()
    deduped = []
    for term in signals.key_concepts:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    signals.key_concepts = deduped

    return signals


# ---------------------------------------------------------------------------
# Shape evidence
# ---------------------------------------------------------------------------

# A term a `term-recall` game can actually use. This is not a guess: it is
# hangman's own `word` pattern (`^[A-Za-z ]{1,40}$`) expressed as a predicate, so a
# lesson with no term matching it is a lesson where the game cannot be authored at
# all — the digit in COVID19 and the hyphen in T-CELL are unguessable on an A-Z
# keyboard. Checking the shape's requirement rather than the game's keeps this
# registry-agnostic.
_RECALLABLE_TERM = re.compile(r"^[A-Za-z][A-Za-z ]{2,39}$")

_ORDERING_WORDS = (
    "step", "steps", "sequence", "order", "ordering", "phase", "phases",
    "stage", "stages", "lifecycle", "pipeline", "workflow", "first", "then",
    "before", "after", "chronolog", "timeline",
)
_PROCEDURE_WORDS = (
    "how to", "procedure", "install", "configure", "set up", "setup",
    "implement", "construct", "build", "deploy", "perform",
)
_NUMERIC_WORDS = (
    "calculate", "compute", "formula", "equation", "derive", "quantif",
    "estimate", "measure", "solve for", "convert",
)
_SPATIAL_WORDS = (
    "diagram", "anatomy", "layout", "position", "map", "topology",
    "architecture", "structure of", "region", "axis", "coordinate",
)
_JUDGEMENT_WORDS = (
    "when to", "whether", "should you", "valid", "invalid", "correct",
    "incorrect", "appropriate", "decide", "choose between", "misconception",
    "pitfall", "common mistake", "trade-off", "tradeoff",
)
_PAIRING_WORDS = (
    "match", "matching", "corresponds", "corresponding", "maps to", "mapping",
    "associate", "pair", "equivalent",
)
_CATEGORISATION_WORDS = (
    "types of", "kinds of", "classif", "categor", "taxonom", "group into",
    "distinguish between", "versus", " vs ", " vs. ",
)


# Two scores this close carry no information about which game fits better, whatever the
# arithmetic says. One definition, two consumers — the prompt says so to the model
# (`build_game_prompt_section`) and the log says so to us (`explain`); a second literal
# in one of them is how the two would drift apart (rule 23).
_TIE_EPSILON = 0.05

# Scores are rounded to 4 dp, so anything under this is float noise, not a margin.
# An EXACT tie is a different fact from a small one and needs a different sentence:
# under an exact tie the order the reader sees *is* the alphabetical tie-break and
# carries no information, whereas at 0.98 vs 0.93 the leader really does lead — saying
# "the order above is alphabetical" there would be a false statement in the prompt.
_EXACT_TIE_EPSILON = 1e-9


def _hits(haystacks: list[str], needles: tuple[str, ...]) -> list[str]:
    """Which needles appear in any haystack, lowercased substring match."""
    blob = " \n ".join(haystacks).lower()
    return [n for n in needles if n in blob]


# Both structural rules below are scored on the QUALITY of the raw material, not on
# its presence. The reason is measured: the previous rules — `min(1.0, 0.6 + 0.1 ×
# usable)` for terms and a flat `1.0` for "has a misconceptions section" — both
# saturate on every spec the lesson planner emits, because it emits six key-concept
# bullets and a `## Common Misconceptions` section every single time. Over the 31 real
# specs in `test_curriculum/` that produced an **exact 1.00 tie on 29 of them**, so the
# ranking carried no information at all and the order the model saw was the
# alphabetical tie-break wearing the words "in order". A score that cannot separate two
# games is worse than no score, because the prompt presents it as evidence.
#
# So: grade each candidate item, then combine. The values are near-continuous, which is
# what makes the ranking discriminate; and every factor is a property of THIS lesson's
# content, which is what makes the choice content-driven rather than a coin toss.

# Occurrence thresholds for "the lesson actually uses this term". A key concept that
# appears once — in its own bullet — and never again is a heading, not a term the
# student will have met often enough to recall letter by letter.
def _term_quality(term: str, spec_blob: str) -> tuple[float, str]:
    """Grade one key concept as hangman material. Returns (0-1, short reason)."""
    words = term.split()
    letters = term.replace(" ", "")

    # Shape: the game hides one string on an A-Z + space keyboard. A single word is
    # the ideal; a four-word phrase is a sentence with the spaces given away.
    if len(words) == 1:
        shape, shape_why = 1.0, "single word"
    elif len(words) == 2:
        shape, shape_why = 0.6, "two words"
    else:
        shape, shape_why = 0.2, f"{len(words)} words"

    # Length: too short is guessed in two moves, too long is tedious to spell out.
    n = len(letters)
    if 6 <= n <= 14:
        length, length_why = 1.0, f"{n} letters"
    elif 5 <= n <= 18:
        length, length_why = 0.6, f"{n} letters"
    else:
        length, length_why = 0.2, f"{n} letters"

    # Reinforcement: how often the spec itself uses the term outside its own bullet.
    hits = spec_blob.count(term.lower())
    if hits >= 3:
        reinforce, reinforce_why = 1.0, f"used {hits}×"
    elif hits == 2:
        reinforce, reinforce_why = 0.6, "used twice"
    else:
        reinforce, reinforce_why = 0.15, "used once, in its own bullet"

    score = 0.45 * shape + 0.35 * length + 0.20 * reinforce
    return score, f"{shape_why}, {length_why}, {reinforce_why}"


def _shape_terms(signals: LessonSignals) -> tuple[float, str]:
    """term-recall: does the lesson teach a term the game could hide *well*?

    Graded on the best two terms rather than on the count. The game needs exactly one
    word, so the best term decides whether it can be authored at all; the runner-up
    decides whether the author had a choice or was cornered.
    """
    usable = [t for t in signals.key_concepts if _RECALLABLE_TERM.match(t)]
    if not usable:
        if signals.key_concepts:
            return 0.1, (
                f"has {len(signals.key_concepts)} key concepts but none match "
                f"[A-Za-z ]{{3,40}} — digits/symbols cannot be guessed on an A-Z keyboard"
            )
        return 0.0, "the spec lists no key concepts"

    spec_blob = signals.text.lower()
    graded = sorted(
        ((*_term_quality(t, spec_blob), t) for t in usable), key=lambda g: -g[0]
    )
    best_score, best_why, best_term = graded[0]
    runner_up = graded[1][0] if len(graded) > 1 else 0.0

    # 0.30 floor: a usable term exists, so the game is authorable whatever its quality.
    quality = 0.75 * best_score + 0.25 * runner_up
    return round(0.30 + 0.70 * quality, 4), (
        f"best term {best_term!r} ({best_why}); {len(usable)} of "
        f"{len(signals.key_concepts)} key concepts usable"
    )


# A misconception is only usable as a petition if it states something that can be ruled
# on. "Students think a higher voltage means a faster signal" is a claim with a verdict;
# "students find this section confusing" is a report about students and has no verdict
# at all — the game cannot be authored from it.
#
# STEMS, not inflections, and this was measured rather than reasoned. The first version
# of this list held `"assume"`, `"confuse"`, `"neglect"` and friends in their base form,
# and scored **0.00** on real planner output like "Assuming all neuronal models have
# unique attractors" — because `"assume"` is not a substring of `"assuming"`. The lesson
# planner emits misconceptions almost exclusively as gerund-headed error phrases, so the
# base forms matched nearly nothing. An error phrase is as usable as a belief phrase:
# the mistake it names IS a claim, and its verdict is "deny".
_ERROR_STEMS = (
    "assum", "think", "believ", "confus", "conflat", "mistak", "misconcept",
    "misappl", "misread", "misunderstand", "misinterpret", "neglect", "forget",
    "forgett", "ignor", "overlook", "treating", "treat ", "expect", "imagin",
    "suppos", "equat", "conclud", "generaliz", "generalis", "using inappropriate",
)
# Anything that makes the bullet a proposition with a truth value — a copula, a modal,
# an absolute quantifier, or an explicit contrast.
_PROPOSITION_WORDS = (
    " is ", " are ", " was ", " were ", "always", "never", "must", "cannot",
    "can't", "only", "same", "equal", "cause", "means", "requires", "does not",
    "doesn't", "will ", "should", "more than", "less than", "identical",
    "no effect", "directly", "all ", "every", " any ", "none", " no ", "each ",
    "unique", "independent", "linear", "constant", "rather than", "instead of",
    " not ", "holds for", "guarantee",
)
# Genuinely verdictless: a report about how the student feels, not about the subject.
# `confusing` is deliberately NOT here — "Confusing X with Y" is the claim "X is Y",
# which is the single most petition-shaped thing the planner writes.
_VAGUE_WORDS = (
    "difficult", "hard to grasp", "hard to see", "hard to visuali", "struggle",
    "unclear", "tricky", "trouble", "counterintuitive", "too abstract",
)


def _petition_quality(bullet: str) -> float:
    """Grade one misconception bullet as a yes/no petition. 0-1."""
    text = f" {bullet.lower()} "
    has_proposition = any(w in text for w in _PROPOSITION_WORDS)
    has_error = any(w in text for w in _ERROR_STEMS)
    is_vague = any(w in text for w in _VAGUE_WORDS)

    score = 0.0
    if has_error:
        # Names a specific mistake, so the petition writes itself: state the mistake as
        # a request and the correct verdict is "deny".
        score += 0.45
    if has_proposition:
        score += 0.35
    if len(bullet.split()) >= 8:
        # Long enough to state a case the student can rule on, rather than a label.
        score += 0.20
    if is_vague and not has_proposition:
        # A report about how students feel, with nothing to rule on.
        score -= 0.40
    return max(0.0, min(1.0, score))


def _shape_judgement(signals: LessonSignals) -> tuple[float, str]:
    """judgement: is there a rule the student must apply to cases?

    Graded on how many misconceptions are actually verdict-shaped, and on whether
    there are enough of them: the shape's own contract asks for 3-4 cases, so two
    grounded claims leaves the author inventing the rest.
    """
    # Judgement language in the title and objectives counts even when misconceptions
    # exist. The old rule consulted it only in the `else` branch, which is a real gap
    # and not a stylistic one: a lesson whose stated objective is "Decide which
    # declaration keyword a situation calls for" is a judgement lesson by construction,
    # and it was losing to term-recall on the strength of a tidy one-word key concept.
    # Deciding *when* a rule applies is the whole shape; that intent lives in the
    # objectives, not in the misconceptions list.
    found = _hits([signals.title, *signals.objectives, *signals.outline], _JUDGEMENT_WORDS)
    lang = min(1.0, 0.25 * len(found))

    if signals.misconceptions:
        qualities = [_petition_quality(m) for m in signals.misconceptions]
        strong = [q for q in qualities if q >= 0.6]
        mean_quality = sum(qualities) / len(qualities)
        enough = min(1.0, len(strong) / 3.0)
        quality = min(1.0, 0.6 * mean_quality + 0.4 * enough + 0.5 * lang)
        why = (
            f"{len(strong)} of {len(signals.misconceptions)} misconceptions are "
            f"verdict-shaped claims (mean case quality {mean_quality:.2f})"
        )
        if found:
            why += f"; objectives/title decide-language {found[:3]}"
        return round(0.30 + 0.70 * quality, 4), why
    if found:
        return round(0.30 + 0.40 * lang, 4), (
            f"no misconceptions listed, but objectives/outline mention {found[:3]}"
        )
    return 0.0, "no misconceptions listed and no judgement language"


def _keyword_shape(name: str, words: tuple[str, ...], weight: float = 0.6):
    """Build an evidence rule that scores on keyword presence.

    Deliberately weaker than the two structural rules above, and labelled as
    keyword-based in its own reason string, so a reader of `explain()` can see which
    part of a ranking rests on measurement and which on a word list.
    """

    def rule(signals: LessonSignals) -> tuple[float, str]:
        found = _hits(
            [signals.title, *signals.objectives, *signals.outline, *signals.key_concepts],
            words,
        )
        if not found:
            return 0.0, f"no {name} language in title/objectives/outline"
        return min(weight + 0.05 * len(found), 0.95), (
            f"keyword evidence: {found[:3]}"
        )

    return rule


# Keyed by the ContentShape values in mlai-games/src/schemas/types.ts. The two
# structural rules come first because they are the ones with real evidence behind
# them; the rest are keyword rules and are scored lower on purpose.
SHAPE_EVIDENCE = {
    "term-recall": _shape_terms,
    "judgement": _shape_judgement,
    "ordering": _keyword_shape("ordering", _ORDERING_WORDS),
    "procedure": _keyword_shape("procedure", _PROCEDURE_WORDS),
    "numeric": _keyword_shape("numeric", _NUMERIC_WORDS),
    "spatial": _keyword_shape("spatial", _SPATIAL_WORDS),
    "pairing": _keyword_shape("pairing", _PAIRING_WORDS),
    "categorisation": _keyword_shape("categorisation", _CATEGORISATION_WORDS),
}


def score_shapes(signals: LessonSignals) -> dict[str, tuple[float, str]]:
    """Score every known content shape against one lesson, with the reason kept."""
    return {shape: rule(signals) for shape, rule in SHAPE_EVIDENCE.items()}


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """A game offered to the model, and why."""

    game: GameEntry
    score: float
    reasons: list[str]


def rank_games(signals: LessonSignals, guide: GameGuide) -> list[Candidate]:
    """Score and order the WHOLE registry for one lesson — no cap applied.

    Split out from `select_candidates` so `explain()` can see the scores of the games
    it did *not* offer. That distinction is load-bearing: a withheld spec can mean
    "scored lower" or "tied at the top and lost the alphabetical tie-break", and only
    the second says the ranking has stopped discriminating.

    Measured over the 31 real planner specs in `test_curriculum/`, both at once:

    | | exact 1.00 ties | top-1 split | median margin |
    |---|---|---|---|
    | old (count-based) | **29 of 31** | hangman 29 / stc 2 | 0.000 |
    | now (quality-graded) | **0 of 31** | hangman 26 / stc 5 | 0.174 |

    The old numbers are why `_shape_terms` and `_shape_judgement` were rewritten: with
    every score pinned at 1.00 the order the model saw was the alphabetical tie-break,
    and the only signal left to break it was that one injected spec is 2.1× longer than
    the other. The model chose that one on every lesson.
    """
    shape_scores = score_shapes(signals)
    ranked: list[Candidate] = []
    for game in guide.games:
        best = 0.0
        reasons: list[str] = []
        for shape in game.content_shapes:
            score, reason = shape_scores.get(shape, (0.0, f"unscorable shape {shape!r}"))
            reasons.append(f"{shape}: {score:.2f} — {reason}")
            best = max(best, score)
        ranked.append(Candidate(game=game, score=best, reasons=reasons))

    # Sort by score, then by type for a stable, reproducible order: two games with
    # identical evidence must not swap places between runs, or the same lesson spec
    # would produce different prompts.
    ranked.sort(key=lambda c: (-c.score, c.game.type))
    return ranked


def select_candidates(
    signals: LessonSignals,
    guide: GameGuide,
    cap: int,
) -> list[Candidate]:
    """Rank the registry for this lesson and return at most `cap` candidates.

    Every game is scored, and the score is its best-matching shape's score. Below
    the cap nothing is dropped — see the module docstring on why the inference is
    allowed to order but not to veto.
    """
    return rank_games(signals, guide)[:cap]


def tie_group(candidates: list[Candidate]) -> tuple[list[Candidate], str]:
    """The candidates the ranker could not meaningfully separate, and *how*.

    Returns `(members, kind)` with `kind` one of:

    - `"exact"` — identical scores. The order the reader sees is the alphabetical
      tie-break and carries no information whatsoever.
    - `"near"`  — the leader genuinely leads, but by less than `_TIE_EPSILON`. The
      order is real; the margin is not worth trusting.
    - `""`      — the ranker separated them. `members` is empty.

    One classifier, two consumers (rule 23): the sentence shown to the model and the
    line written to the log must not be able to disagree about which case this is.
    Measured on the 31 real planner specs in `test_curriculum/`: 0 exact, 4 near — and
    at 100 registered games the synthetic sweep is almost all exact, which is why both
    branches have to exist.
    """
    if len(candidates) < 2:
        return [], ""
    lead = candidates[0].score - candidates[1].score
    if lead >= _TIE_EPSILON:
        return [], ""
    kind = "exact" if lead <= _EXACT_TIE_EPSILON else "near"
    span = _EXACT_TIE_EPSILON if kind == "exact" else _TIE_EPSILON
    return [c for c in candidates if candidates[0].score - c.score <= span], kind


def explain(signals: LessonSignals, guide: GameGuide, candidates: list[Candidate]) -> str:
    """A human-readable trace of the selection, for the run log.

    Printed, not discarded: rule 27's corollary. If games stop being chosen, this is
    the only place that says whether Stage A never offered them or the model declined
    them — two very different bugs with one symptom.
    """
    lines = [
        f"GAMES: {len(guide.games)} registered, offering {len(candidates)} "
        f"(title={signals.title!r})",
        f"       signals: {len(signals.key_concepts)} key concepts, "
        f"{len(signals.objectives)} objectives, "
        f"{len(signals.misconceptions)} misconceptions",
    ]
    for c in candidates:
        lines.append(f"       {c.score:.2f}  {c.game.type}")
        for reason in c.reasons:
            lines.append(f"             {reason}")
    offered = {c.game.type for c in candidates}
    dropped = [c for c in rank_games(signals, guide) if c.game.type not in offered]
    if dropped:
        # Never silent: rule 25's "no silent caps". A game whose spec was withheld is
        # still choosable from the catalog, and saying so distinguishes "not offered"
        # from "not registered".
        lines.append(
            "       spec withheld (still choosable from the catalog): "
            + ", ".join(f"{c.game.type} {c.score:.2f}" for c in dropped)
        )
        # The cut was a coin toss, not a judgement. Worth its own line because it is
        # the symptom of a ranking that has stopped ranking: see `rank_games`, where
        # 31 of 31 real specs already top out at 1.0 with only two games registered.
        cut = min(c.score for c in candidates) if candidates else 0.0
        exact = [c.game.type for c in dropped if cut - c.score <= _EXACT_TIE_EPSILON]
        near = [c.game.type for c in dropped
                if _EXACT_TIE_EPSILON < cut - c.score <= _TIE_EPSILON]
        if exact:
            lines.append(
                f"       ⚠️  cap={len(candidates)} cut {len(exact)} game(s) tied at "
                f"{cut:.2f} with the last offered one, ordered alphabetically, so which "
                f"spec was injected is arbitrary: {', '.join(exact)}"
            )
        if near:
            # Not arbitrary — the cut is in the right direction — but a margin this
            # small is not evidence either, so it is worth seeing.
            lines.append(
                f"       cap={len(candidates)} also cut {len(near)} game(s) within "
                f"{_TIE_EPSILON:.2f} of the cut at {cut:.2f}: {', '.join(near)}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The prompt section
# ---------------------------------------------------------------------------


def registered_game_types(guide_dir: Path) -> list[str]:
    """The registered game types, or `[]` if the guide is unavailable.

    For the retry prompt's `UNKNOWN_GAME_TYPE` fix, which needs the valid list and
    nothing else. Quiet on failure — unlike the two builders above, this is called
    once per fix attempt (up to `MAX_VALIDATION_ATTEMPTS = 500`), and the loud warning
    has already been printed once by the prompt builders at the start of the lesson.
    Returning `[]` drops the guidance rather than offering an empty choice.
    """
    try:
        return [g.type for g in load_guide(guide_dir).games]
    except GuideUnavailable:
        return []


def build_game_prompt_section(
    guide_dir: Path,
    spec_text: str,
    cap: int,
    verbose: bool = True,
) -> str:
    """Build the `<Game>` portion of the generation prompt, or `""`.

    Fails **open**, loudly. This is a prompt builder on a five-hour, ~$64 course run:
    a lesson with no game is pedagogically weaker, while aborting the run costs the
    whole course. That is rule 31's fail-open/fail-closed-per-path — the *write* paths
    (the worker's upload gate, the API's edit endpoint) fail closed, and a
    read-only-ish enrichment step like this one fails open.

    Loudly matters more than usual here, because a silent failure is invisible by
    construction: no game in the lesson looks exactly like the model deciding no game
    fitted. The warning is the only thing that distinguishes them.
    """
    try:
        guide = load_guide(guide_dir)
    except GuideUnavailable as exc:
        print(f"⚠️  GAMES DISABLED: {exc}")
        print("    Lessons will generate without games. This is not a failure, but it")
        print("    is also not what was intended — the guide is a build artifact of")
        print("    mlai-games and is COPYd into the worker image from dist/.")
        return ""

    signals = extract_signals(spec_text)
    candidates = select_candidates(signals, guide, cap)
    if verbose:
        print(explain(signals, guide, candidates))

    if not candidates:
        return ""

    # The catalog and the shared rules go in the SYSTEM prompt (they are identical for
    # every lesson and benefit from prompt caching). Only the per-lesson candidate
    # specs go here.
    parts = [
        "## Interactive game for this lesson",
        "",
        "**Exactly one** `<Game>` block, at the lesson's top level, near the end — the",
        "full contract is in your system prompt under \"Game block rules\". Read it before",
        "writing the payload; the escaping rules there are NOT the same as for `<Body>`.",
        "",
        "Each candidate below is scored on evidence measured in THIS lesson's spec, with",
        "the evidence shown. Pick the type whose evidence actually describes what this",
        "lesson asks the student to do:",
        "",
    ]
    for i, c in enumerate(candidates, 1):
        parts.append(f"{i}. `{c.game.type}` ({c.score:.2f}) — {c.game.tagline}")
        for reason in c.reasons:
            parts.append(f"   - {reason}")
    parts.append("")

    # Disclose a near-tie instead of presenting the alphabetical tie-break as a ranking.
    # Measured: under the previous scoring 29 of the 31 real planner specs produced an
    # EXACT 1.00 tie, so "in order" was noise dressed as evidence — and with nothing to
    # go on, the model fell back to the only remaining signal, which was that one spec
    # below is over twice as long as the other. Both halves of that are addressed here.
    tied, kind = tie_group(candidates)
    if kind:
        names = " and ".join(f"`{c.game.type}`" for c in tied)
        if kind == "exact":
            parts.append(
                f"**The evidence does not separate {names} — both score "
                f"{candidates[0].score:.2f}.** The order above is the alphabetical "
                "tie-break, not a recommendation."
            )
        else:
            parts.append(
                f"**`{candidates[0].game.type}` leads by only "
                f"{candidates[0].score - candidates[1].score:.2f} "
                f"({candidates[0].score:.2f} vs {candidates[1].score:.2f}) — real, but "
                f"too small to settle it.**"
            )
        parts.append(
            "Decide from the lesson's own content: which of those shapes is the thing a"
            " student who understood THIS lesson could do?"
        )
        parts.append("")

    parts.append(
        "A longer authoring spec below does not mean a better fit — the specs differ in"
    )
    parts.append(
        "length because the games differ in complexity, not in suitability."
    )
    parts.append("")
    parts.append(
        "You may instead use any other type from the catalog in your system prompt, but"
    )
    parts.append(
        "you have not been given its fields, so prefer one of the specs below."
    )
    parts.append("")
    for c in candidates:
        parts.append("---")
        parts.append("")
        parts.append(guide.spec_md(c.game.type).rstrip())
        parts.append("")

    return "\n".join(parts)


def build_game_rules_section(guide_dir: Path) -> str:
    """The catalog + cross-game rules, for the SYSTEM prompt. Identical every lesson.

    Separate from `build_game_prompt_section` because these two have different cache
    behaviour: this half is the same bytes for every lesson in every course and should
    sit in the cached system prompt, while the candidate specs vary per lesson.
    """
    try:
        guide = load_guide(guide_dir)
    except GuideUnavailable as exc:
        print(f"⚠️  GAMES DISABLED (system prompt): {exc}")
        return ""

    # The banner matches the house style of the other system-prompt sections
    # (`## ═══` dividers in prompts/system.py). It lives here rather than there so the
    # whole block is one string the caller either has or does not have — a section
    # header with nothing under it is what a "games disabled" run would otherwise show.
    return (
        "## ═══════════════════════════════════════════════════════\n"
        "## INTERACTIVE GAMES\n"
        "## ═══════════════════════════════════════════════════════\n\n"
        "A lesson may end with ONE interactive game, written as a `<Game>` block. The\n"
        "game types available to you are listed below; the ones that best fit THIS\n"
        "lesson, with full authoring specs, come with the lesson specification.\n\n"
        + guide.catalog_md.rstrip()
        + "\n\n"
        + guide.rules_md.rstrip()
        + "\n"
    )
