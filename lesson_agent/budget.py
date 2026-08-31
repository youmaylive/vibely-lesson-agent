"""Size the lesson before writing it: turn the planner's `duration` into a budget.

Stdlib only, on the `games.py` / `svg_geometry.py` precedent: no SDK import, so this
module runs and tests with no credentials and cannot fail on a dependency missing from
the worker image. Every function here fails open — a missing or malformed `duration`
costs the default band, never the run.

The problem this solves
-----------------------
Measured on the live planner output (`memebu-lesson-planner/output/test_full_pipeline_neuro/`,
89 lessons from one ontology):

    16 modules · 89 lessons · sum of stated `duration:` = 2915 min = 48.6 h
    course_spine.json estimated_total_duration: "50-65 hours"
    per-lesson spec: median 1066 words, median 13 `content_outline` bullets (max 41)

and on the 5 lessons this pipeline has actually written:

    prose words/lesson  median 1848  (9.2 min reading @200wpm)
    <Section>/lesson    median 13    (min 9, max 16)
    words per Section   median ~142  — sections over 300 words: 0 / 63
    <Svg>/lesson        median 2     (min 1, max 4) — against a stated target of 3-4

That third line is the finding that decides the design. **It is not prose bloat.** Every
section is already tight; not one of 63 exceeds 300 words. Length comes from writing 13
sections instead of 6, which tracks the spec's 13 outline bullets almost 1:1. So "be
concise" cannot work as an instruction — the writer is already concise per chunk, and
what needs a number is *how many chunks*.

The word count excludes assessment text (`<Prompt>`, `<Option>`, `<Front>`, `<Back>`) as
well as code — see `lesson_shape.py`, which is the function that produced these numbers
and the one every later run is compared with, so the comparison stays like-for-like.

Why `duration` and not a fixed constant
---------------------------------------
Because the number already exists and nothing reads it — AGENTS.md rule 27's shape, the
one this project keeps hitting. The planner writes `duration: "25 minutes"` into every
lesson's frontmatter and carries `estimated_duration` through
`curriculum_schema_v2.json`, and the strings "duration", "minutes", "word count" and
"target length" appear **zero** times anywhere in `prompts/`. It is also genuinely
varied — 30 min ×41, 25 ×22, 45 ×17, 35 ×8, 90 ×1 — so it carries real signal about
which lessons deserve more room.

Why bands and not a linear map
------------------------------
`duration` is whole-lesson time: reading, exercises, the transfer task, the reflection
questions. Scaling prose linearly off it (30 min × 200 wpm = 6000 words) would make
lessons *longer* than they are today, i.e. it would invert the whole point. Three coarse
bands keep `duration` load-bearing — a 45-minute checkpoint lesson gets more room than a
25-minute one — without pretending the mapping is precise. Rule 25: measure the thing,
and where you cannot, do not dress an assumption up as arithmetic.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from config import (
    GAME_FLOOR,
    GAME_FLOOR_ENV,
    SVG_FLOOR,
    SVG_FLOOR_ENV,
    LESSON_BUDGET_BAND_ENV,
)

# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

# A leading `---` fence, then everything up to the next `---` on its own line. Anchored
# at the start of the file on purpose: a `duration: 5 minutes` sentence in the lesson
# body must not be mistaken for the frontmatter key. `test_curriculum/` specs have no
# frontmatter at all, and that path has to stay silent rather than warn on every lesson.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)

_DURATION_RE = re.compile(r"^duration:[ \t]*(.+?)[ \t]*$", re.M | re.I)
_IS_CHECKPOINT_RE = re.compile(r"^is_checkpoint:[ \t]*(.+?)[ \t]*$", re.M | re.I)


def frontmatter(spec_text: str) -> str:
    """The raw YAML frontmatter block, or "" when the spec has none.

    Public because `games.py` needs the same block for `title:` and `concepts:`, and a
    second copy of this regex is where the anchoring would drift (rule 23) — the anchor
    is the whole reason a `duration: 5 minutes` sentence in the lesson body cannot size
    the lesson.
    """
    match = _FRONTMATTER_RE.match(spec_text or "")
    return match.group(1) if match else ""


def parse_duration_minutes(spec_text: str) -> int | None:
    """Minutes from the spec's `duration:` frontmatter key, or None.

    None means "the spec did not say", which is a normal, silent case — the specs in
    `test_curriculum/` carry no frontmatter at all. The caller falls back to the default
    band.

    Handles the shapes the planner actually emits (`"25 minutes"`, `"90 minutes"`) plus
    ranges (`"25-30 minutes"` → the low end, so a range never inflates the budget) and
    hours (`"1 hour"`, `"1.5 hours"`).
    """
    front = frontmatter(spec_text)
    if not front:
        return None

    match = _DURATION_RE.search(front)
    if not match:
        return None

    raw = match.group(1).strip().strip('"').strip("'")
    if not raw:
        return None

    # The sign is part of the match on purpose: without it `-5 minutes` parses as 5 and
    # the `> 0` guard below never fires, so a malformed spec silently sizes the lesson.
    number = re.search(r"(-?\d+(?:\.\d+)?)", raw)
    if not number:
        return None

    value = float(number.group(1))
    if re.search(r"\bh(?:ou)?rs?\b", raw, re.I):
        value *= 60

    minutes = int(round(value))
    # A 0- or negative-minute lesson is a malformed spec, not a request for an empty
    # lesson. Fall back rather than hand the writer a nonsense budget.
    return minutes if minutes > 0 else None


def parse_is_checkpoint(spec_text: str) -> bool:
    """Whether the spec's frontmatter marks this lesson as a checkpoint."""
    front = frontmatter(spec_text)
    if not front:
        return False
    match = _IS_CHECKPOINT_RE.search(front)
    if not match:
        return False
    return match.group(1).strip().strip('"').strip("'").lower() in {"true", "yes", "1"}


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Budget:
    """The target shape of one lesson. Ranges are inclusive `(low, high)`."""

    band: str
    minutes: int | None
    is_checkpoint: bool
    sections: tuple[int, int]
    words: tuple[int, int]
    svgs: tuple[int, int]
    mermaid: tuple[int, int]
    assessments: tuple[int, int]
    flashcards: tuple[int, int]
    svg_floor: int
    # Not a band shape: one game per lesson regardless of length, because the registry
    # itself caps it at one (`maxPerLesson: 1`). So this is a floor that equals the
    # ceiling — the only question is whether the lesson has its game or not.
    game_floor: int = 1

    @property
    def reading_minutes(self) -> tuple[int, int]:
        """Prose reading time at 200 wpm, rounded — for logs and the census."""
        return (round(self.words[0] / 200), round(self.words[1] / 200))


# Ordered shortest-first: `_promote` steps one to the right for a checkpoint lesson.
_BANDS: tuple[str, ...] = ("short", "standard", "deep")

_BAND_SHAPES: dict[str, dict[str, tuple[int, int]]] = {
    # ≤25 min
    "short": {
        "sections": (4, 6),
        "words": (900, 1100),
        "svgs": (3, 4),
        "mermaid": (1, 2),
        "assessments": (4, 4),
        "flashcards": (3, 4),
    },
    # 26-40 min, and the default when the spec says nothing
    "standard": {
        "sections": (5, 7),
        "words": (1000, 1300),
        "svgs": (3, 4),
        "mermaid": (1, 2),
        "assessments": (4, 5),
        "flashcards": (3, 4),
    },
    # ≥41 min, or one band up from a checkpoint lesson
    "deep": {
        "sections": (7, 9),
        "words": (1400, 1700),
        "svgs": (4, 5),
        "mermaid": (2, 2),
        "assessments": (5, 6),
        "flashcards": (4, 5),
    },
}

DEFAULT_BAND = "standard"


def _promote(band: str) -> str:
    """One band longer, saturating at the longest."""
    index = _BANDS.index(band)
    return _BANDS[min(index + 1, len(_BANDS) - 1)]


def _band_for_minutes(minutes: int | None) -> str:
    if minutes is None:
        return DEFAULT_BAND
    if minutes <= 25:
        return "short"
    if minutes <= 40:
        return "standard"
    return "deep"


def _env_floor(name: str, default: int) -> int:
    """An integer floor from the environment, falling back loudly.

    Env-overridable on the `GAME_FLOOR_RATE` precedent so a floor can be retuned without
    rebuilding the worker image. `0` disables the floor outright — a legitimate choice
    for a deliberately prose-only or game-free run.

    One function for both floors rather than two near-identical ones: the second copy is
    where the negative-value branch or the warning wording would drift (rule 23).
    """
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        print(f"   ⚠️  {name}={raw!r} is not an integer — using the default {default}.")
        return default
    if value < 0:
        print(f"   ⚠️  {name}={raw!r} is negative — using the default {default}.")
        return default
    return value


def _env_band() -> str | None:
    """`LESSON_BUDGET_BAND` from the environment — forces one band for every lesson.

    For retuning and for A/B runs. An unknown value warns and is ignored rather than
    silently selecting a band nobody asked for.
    """
    raw = os.getenv(LESSON_BUDGET_BAND_ENV, "").strip().lower()
    if not raw:
        return None
    if raw not in _BAND_SHAPES:
        print(
            f"   ⚠️  {LESSON_BUDGET_BAND_ENV}={raw!r} is not one of "
            f"{', '.join(_BANDS)} — ignoring it."
        )
        return None
    return raw


def budget_for(minutes: int | None, is_checkpoint: bool = False) -> Budget:
    """The target shape for a lesson of this stated duration.

    A checkpoint lesson is promoted one band: it synthesises several lessons' worth of
    material and legitimately needs more room. Its own stated `duration` is still the
    primary signal, which is why this is a promotion and not a jump straight to `deep`.
    """
    forced = _env_band()
    if forced is not None:
        band = forced
    else:
        band = _band_for_minutes(minutes)
        if is_checkpoint:
            band = _promote(band)

    shape = _BAND_SHAPES[band]
    floor = _env_floor(SVG_FLOOR_ENV, SVG_FLOOR)
    svgs = shape["svgs"]
    # A floor above the band's target would be self-contradictory in the prompt. Let the
    # floor win and widen the target to match it.
    if floor > svgs[0]:
        svgs = (floor, max(floor, svgs[1]))

    return Budget(
        band=band,
        minutes=minutes,
        is_checkpoint=is_checkpoint,
        sections=shape["sections"],
        words=shape["words"],
        svgs=svgs,
        mermaid=shape["mermaid"],
        assessments=shape["assessments"],
        flashcards=shape["flashcards"],
        svg_floor=floor,
        game_floor=_env_floor(GAME_FLOOR_ENV, GAME_FLOOR),
    )


def budget_for_spec(spec_text: str) -> Budget:
    """`budget_for` straight off a lesson spec's text. Never raises."""
    try:
        minutes = parse_duration_minutes(spec_text)
        is_checkpoint = parse_is_checkpoint(spec_text)
    except Exception as exc:  # pragma: no cover — defensive; regexes above cannot raise
        print(f"   ⚠️  BUDGET: could not read the spec frontmatter ({exc}) — using the default band.")
        minutes, is_checkpoint = None, False
    return budget_for(minutes, is_checkpoint)


# ---------------------------------------------------------------------------
# Prompt text
# ---------------------------------------------------------------------------


def build_budget_section(budget: Budget) -> str:
    """The budget block for the generation prompt.

    Deliberately short. Rule 32's fourth lesson is that prompt prose has a token cost
    that multiplies: an 805-char suggestion repeated across 17 findings was ~4.2k tokens
    per attempt, re-sent up to `MAX_VALIDATION_ATTEMPTS = 500` times. This block is in
    the generation prompt only, but the habit is worth keeping.
    """
    low_words, high_words = budget.words
    low_read, high_read = budget.reading_minutes
    # Omitted entirely when the floor is disabled (`GAME_FLOOR=0`), rather than printing
    # "exactly 0" — a budget row telling the writer to produce no game would forbid what
    # the knob merely stops enforcing.
    game_row = (
        f"\n| `<Game>` blocks | **exactly {budget.game_floor}** — the floor and the "
        f"ceiling are the same number |"
        if budget.game_floor > 0
        else ""
    )
    stated = (
        f"{budget.minutes} min stated"
        if budget.minutes is not None
        else "no duration in the spec"
    )

    return f"""## 📏 LENGTH BUDGET (this lesson, not a general guideline)

{stated} → **{budget.band}** lesson. Write to these numbers:

| | target |
|---|---|
| `<Section>` blocks | **{budget.sections[0]}-{budget.sections[1]}** |
| prose words (all `<Body>` text, excluding code) | **{low_words}-{high_words}** (~{low_read}-{high_read} min to read) |
| `generate_svg` calls / `<Svg>` blocks | **{budget.svgs[0]}-{budget.svgs[1]}**, never fewer than {budget.svg_floor} |
| `<Mermaid>` diagrams | **{budget.mermaid[0]}-{budget.mermaid[1]}** |
| assessment blocks (SingleSelect, MultiSelect, SortQuiz, MatchPairs, FillBlanks, Subjective — combined) | **{budget.assessments[0]}-{budget.assessments[1]}** |
| `<FlashCard>` blocks | **{budget.flashcards[0]}-{budget.flashcards[1]}** |{game_row}

**This is a ceiling, not a floor.** Longer is not better — a learner who quits halfway
learned less than one who finished a shorter lesson.

**How to hit it, since the spec will hand you more outline bullets than that:**
- You are NOT obliged to give every Content Outline bullet its own `<Section>`. Merge
  bullets that are one idea. Fold a minor bullet into a sentence, or into a FlashCard.
- Pick the {budget.assessments[0]}-{budget.assessments[1]} assessment types that actually fit what this lesson
  teaches. Do not include one of every type.
- Add nothing the spec did not ask for. No "further reading", no "historical context"
  the spec never mentioned, no recap section beyond the single summary.
- **Draw it instead of writing it.** For anything structural, spatial, or a process:
  call `generate_svg` and write two sentences, not three paragraphs. The diagram IS the
  explanation. This is why the visual floor and the word ceiling point the same way.
"""
