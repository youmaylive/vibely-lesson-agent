#!/usr/bin/env python3
"""
Executable expectations for budget.py and lesson_shape.py.

Rule 18 and rule 26 together are the whole reason this file exists. The generation
prompt has asked for "3-4 `generate_svg` calls" since the SVG framework landed, and it
was never met — median 2, min 1 across the 5 lessons this pipeline has written — because
nothing counted. A rule stated in a prompt and enforced by nothing is a regression no
test catches. These are the cases that make the counting itself provable.

Stdlib only, no pytest, no network, no credentials — it must run identically on a Mac and
inside the worker image, where `lesson_agent` is flattened to `/app/lesson-agent/*.py`
(so `import lesson_shape`, never `import lesson_agent.lesson_shape`).

    python3 lesson_shape.test.py                # everything
    python3 lesson_shape.test.py band svg       # only cases matching a substring
    python3 lesson_shape.test.py --list

    # in the worker image, before pushing (rule 22):
    docker run --rm --entrypoint python3 memebu-worker:latest \
      /app/lesson-agent/lesson_shape.test.py

Corpus cases read the real generated lessons from $LESSON_CORPUS_ROOT (default: this
repo's `test_curriculum/`) and SKIP loudly when absent — a skip is never a pass. They pin
the *baseline*: the numbers a future run is compared against. If they start failing
because the lessons were regenerated, that is the point; re-read the numbers, don't
loosen the case.

Environment
───────────
`budget.py` reads SVG_FLOOR and LESSON_BUDGET_BAND from the environment. Every case that
touches them sets and restores them explicitly, because a stray export in the shell would
otherwise silently retune the thing under test.
"""

from __future__ import annotations

import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import budget as B  # noqa: E402
import lesson_shape as S  # noqa: E402

# ---------------------------------------------------------------------------
# Harness — same shape as svg_geometry.test.py
# ---------------------------------------------------------------------------

CASES: list[tuple[str, object, str | None]] = []


def case(name: str, xfail: str | None = None):
    def wrap(fn):
        CASES.append((name, fn, xfail))
        return fn

    return wrap


class Skip(Exception):
    """Inputs unavailable (the lesson corpus is absent). Fires the loud banner."""


def eq(actual, expected, what: str) -> None:
    if actual != expected:
        raise AssertionError(f"{what}: expected {expected!r}, got {actual!r}")


def true(cond, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def contains(haystack: str, needle: str, what: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{what}: {needle!r} not found in {haystack[:400]!r}")


class env:
    """Set env vars for one case and restore them, whatever happens."""

    def __init__(self, **values: str | None):
        self.values = values
        self.saved: dict[str, str | None] = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return False


def codes(report: S.ShapeReport) -> list[str]:
    return [f.code for f in report.findings]


def clean_env() -> env:
    """No SVG_FLOOR / GAME_FLOOR / LESSON_BUDGET_BAND — the shipped defaults."""
    return env(SVG_FLOOR=None, GAME_FLOOR=None, LESSON_BUDGET_BAND=None)


def spec(duration: str | None = None, checkpoint: bool | None = None) -> str:
    """A lesson spec with YAML frontmatter, in the shape agent_v2 actually emits."""
    lines = ["---", "title: A Lesson"]
    if duration is not None:
        lines.append(f'duration: "{duration}"')
    if checkpoint is not None:
        lines.append(f"is_checkpoint: {str(checkpoint).lower()}")
    lines += ["---", "", "## Content Outline", "- one", "- two"]
    return "\n".join(lines)


def lesson(body: str) -> str:
    """A minimal .mlai document. Deliberately not valid MLAI — the measurement runs
    before the validation loop has repaired anything, and must not need a parse."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<Lesson>\n'
        "  <Meta><Id>x</Id><Title>T</Title><Version>1</Version></Meta>\n"
        f"{body}\n</Lesson>\n"
    )


def words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def sections(count: int, each: int = 10) -> str:
    return "\n".join(
        f"  <Section type=\"concept\"><H2>Heading {i}</H2>"
        f"<Body>{words(each)}</Body></Section>"
        for i in range(count)
    )


def svgs(count: int) -> str:
    return "\n".join(
        f'  <Svg><svg viewBox="0 0 10 10"><text x="1" y="1">label {i}</text></svg></Svg>'
        for i in range(count)
    )


def game(gtype: str = "hangman") -> str:
    """One `<Game>` block, so a case about some *other* rule is not also below the game
    floor. Payload shape is irrelevant here — `lesson_shape` counts tags, it never parses
    JSON (that is the real `dist/cli.js`'s job)."""
    return f'\n  <Game type="{gtype}">{{"word": "cat"}}</Game>'


def std_budget(**over) -> B.Budget:
    """The default standard budget, with fields overridden for a focused case."""
    with clean_env():
        base = B.budget_for(30)
    from dataclasses import replace

    return replace(base, **over) if over else base


# ---------------------------------------------------------------------------
# budget.py — frontmatter parsing
# ---------------------------------------------------------------------------


@case("duration/plain minutes")
def _():
    eq(B.parse_duration_minutes(spec("25 minutes")), 25, "25 minutes")


@case("duration/bare number")
def _():
    eq(B.parse_duration_minutes(spec("45")), 45, "bare 45")


@case("duration/range takes the low end")
def _():
    # A range must never inflate the budget — the whole point is a ceiling.
    eq(B.parse_duration_minutes(spec("25-30 minutes")), 25, "25-30 minutes")


@case("duration/hours are converted")
def _():
    eq(B.parse_duration_minutes(spec("1 hour")), 60, "1 hour")
    eq(B.parse_duration_minutes(spec("1.5 hours")), 90, "1.5 hours")


@case("duration/no frontmatter is silent None")
def _():
    # Every spec in test_curriculum/ looks like this. It must not warn on each lesson.
    eq(B.parse_duration_minutes("# A Lesson\n\nSome prose.\n"), None, "no frontmatter")


@case("duration/missing key is None")
def _():
    eq(B.parse_duration_minutes(spec(None)), None, "frontmatter without duration")


@case("duration/zero and negative fall back")
def _():
    # A 0-minute lesson is a malformed spec, not a request for an empty lesson.
    eq(B.parse_duration_minutes(spec("0 minutes")), None, "0 minutes")
    eq(B.parse_duration_minutes(spec("-5 minutes")), None, "-5 minutes")


@case("duration/a body mention is not frontmatter")
def _():
    # The regex is anchored at the start of the file on purpose: prose saying
    # "duration: 5 minutes" inside the lesson must not size the lesson.
    text = "# Lesson\n\nSet duration: 5 minutes on the animation.\n"
    eq(B.parse_duration_minutes(text), None, "duration in the body")


@case("duration/only the frontmatter block is searched")
def _():
    text = spec("25 minutes") + "\nduration: 90 minutes\n"
    eq(B.parse_duration_minutes(text), 25, "a later duration line must not win")


@case("checkpoint/true forms")
def _():
    for value in ("true", "True", "yes", "1"):
        text = spec("25 minutes").replace("is_checkpoint: ", "")
        text = text.replace("---\n\n", f"is_checkpoint: {value}\n---\n\n", 1)
        true(B.parse_is_checkpoint(text), f"is_checkpoint: {value}")


@case("checkpoint/absent is False")
def _():
    eq(B.parse_is_checkpoint(spec("25 minutes")), False, "no is_checkpoint key")
    eq(B.parse_is_checkpoint("no frontmatter"), False, "no frontmatter")


@case("checkpoint/false is False")
def _():
    eq(B.parse_is_checkpoint(spec("25 minutes", checkpoint=False)), False, "false")


# ---------------------------------------------------------------------------
# budget.py — bands
# ---------------------------------------------------------------------------


@case("band/boundaries")
def _():
    with clean_env():
        # The boundaries themselves, not values comfortably inside each band — an
        # off-by-one in `<=` is exactly the bug a mid-band case cannot see.
        eq(B.budget_for(1).band, "short", "1 min")
        eq(B.budget_for(25).band, "short", "25 min (boundary)")
        eq(B.budget_for(26).band, "standard", "26 min")
        eq(B.budget_for(40).band, "standard", "40 min (boundary)")
        eq(B.budget_for(41).band, "deep", "41 min")
        eq(B.budget_for(90).band, "deep", "90 min")


@case("band/None is the default band")
def _():
    with clean_env():
        eq(B.budget_for(None).band, B.DEFAULT_BAND, "no duration")
        eq(B.DEFAULT_BAND, "standard", "the default band itself")


@case("band/checkpoint promotes exactly one band")
def _():
    with clean_env():
        eq(B.budget_for(20, True).band, "standard", "short + checkpoint")
        eq(B.budget_for(30, True).band, "deep", "standard + checkpoint")


@case("band/promotion saturates at deep")
def _():
    with clean_env():
        eq(B.budget_for(90, True).band, "deep", "deep + checkpoint stays deep")


@case("band/every band is a ceiling below today's median")
def _():
    # The point of the whole change: the measured baseline is 1848 prose words and 13
    # Sections. If any band's high end reaches that, the budget cannot shrink anything.
    with clean_env():
        for minutes in (20, 30, 45):
            b = B.budget_for(minutes)
            true(b.words[1] < 1848, f"{b.band} word ceiling {b.words[1]} must be < 1848")
            true(
                b.sections[1] < 13,
                f"{b.band} section ceiling {b.sections[1]} must be < 13",
            )


@case("band/ranges are ordered and non-empty")
def _():
    with clean_env():
        for minutes in (20, 30, 45):
            b = B.budget_for(minutes)
            for label, (low, high) in (
                ("sections", b.sections),
                ("words", b.words),
                ("svgs", b.svgs),
                ("mermaid", b.mermaid),
                ("assessments", b.assessments),
                ("flashcards", b.flashcards),
            ):
                true(low <= high, f"{b.band} {label} range {low}-{high} is inverted")
                true(low > 0, f"{b.band} {label} low end must be positive, got {low}")


@case("band/longer bands are monotonically larger")
def _():
    with clean_env():
        short, standard, deep = (B.budget_for(m) for m in (20, 30, 45))
        for label in ("sections", "words", "svgs", "assessments"):
            a, b, c = (getattr(x, label)[1] for x in (short, standard, deep))
            true(a <= b <= c, f"{label} ceilings must not decrease: {a}, {b}, {c}")


@case("band/svg target meets the floor and never contradicts it")
def _():
    with clean_env():
        for minutes in (20, 30, 45):
            b = B.budget_for(minutes)
            true(
                b.svgs[0] >= b.svg_floor,
                f"{b.band} svg target {b.svgs} starts below its own floor "
                f"{b.svg_floor} — the prompt would contradict itself",
            )


@case("band/reading_minutes derives from words")
def _():
    b = std_budget(words=(1000, 1300))
    eq(b.reading_minutes, (5, 6), "1000-1300 words at 200 wpm")


# ---------------------------------------------------------------------------
# budget.py — environment overrides
# ---------------------------------------------------------------------------


@case("env/SVG_FLOOR overrides the constant")
def _():
    with env(SVG_FLOOR="4", LESSON_BUDGET_BAND=None):
        eq(B.budget_for(30).svg_floor, 4, "SVG_FLOOR=4")


@case("env/SVG_FLOOR above the band target widens the target")
def _():
    # Otherwise the prompt would say "3-4 diagrams, never fewer than 5".
    with env(SVG_FLOOR="5", LESSON_BUDGET_BAND=None):
        b = B.budget_for(30)
        eq(b.svg_floor, 5, "floor")
        eq(b.svgs, (5, 5), "target widened to meet the floor")


@case("env/SVG_FLOOR=0 disables the hard rule")
def _():
    # A legitimate setting for a deliberately prose-only run.
    with env(SVG_FLOOR="0", LESSON_BUDGET_BAND=None):
        b = B.budget_for(30)
        eq(b.svg_floor, 0, "floor disabled")
        # The game is present so this asserts what it says it asserts: SVG_FLOOR=0
        # disables the SVG floor. LS-GAME-FLOOR is a separate knob and still applies.
        report = S.check(lesson(sections(5) + svgs(0) + game()), b)
        eq(report.has_hard, False, "no hard finding when the floor is 0")


@case("env/SVG_FLOOR garbage falls back to the default, loudly")
def _():
    with env(SVG_FLOOR="three", LESSON_BUDGET_BAND=None):
        eq(B.budget_for(30).svg_floor, B.SVG_FLOOR, "non-integer")
    with env(SVG_FLOOR="-1", LESSON_BUDGET_BAND=None):
        eq(B.budget_for(30).svg_floor, B.SVG_FLOOR, "negative")
    with env(SVG_FLOOR="   ", LESSON_BUDGET_BAND=None):
        eq(B.budget_for(30).svg_floor, B.SVG_FLOOR, "blank")


@case("env/LESSON_BUDGET_BAND forces a band")
def _():
    with env(LESSON_BUDGET_BAND="short", SVG_FLOOR=None):
        # It must beat both the duration AND the checkpoint promotion, or an A/B run
        # would silently measure two different bands.
        eq(B.budget_for(90, True).band, "short", "forced short")


@case("env/LESSON_BUDGET_BAND unknown value is ignored")
def _():
    with env(LESSON_BUDGET_BAND="epic", SVG_FLOOR=None):
        eq(B.budget_for(30).band, "standard", "unknown band ignored")


# ---------------------------------------------------------------------------
# budget.py — budget_for_spec and the prompt text
# ---------------------------------------------------------------------------


@case("spec/budget_for_spec reads duration and checkpoint together")
def _():
    with clean_env():
        b = B.budget_for_spec(spec("45 minutes", checkpoint=True))
        eq(b.minutes, 45, "minutes")
        eq(b.is_checkpoint, True, "checkpoint")
        eq(b.band, "deep", "45 min promoted, saturating")


@case("spec/budget_for_spec never raises")
def _():
    with clean_env():
        for text in ("", "---\n", "---\nduration:\n---\n", "\x00\x01", "---\n---\n"):
            b = B.budget_for_spec(text)
            true(b.band in ("short", "standard", "deep"), f"band for {text!r}")


@case("prompt/budget section states every number")
def _():
    b = std_budget()
    text = B.build_budget_section(b)
    for expected in (
        f"{b.sections[0]}-{b.sections[1]}",
        f"{b.words[0]}-{b.words[1]}",
        f"never fewer than {b.svg_floor}",
        f"{b.mermaid[0]}-{b.mermaid[1]}",
        f"{b.flashcards[0]}-{b.flashcards[1]}",
    ):
        contains(text, expected, "budget section")


@case("prompt/budget section says ceiling, not floor")
def _():
    # Every other sizing instruction in this pipeline is an "At least…" line. If this
    # block reads the same way it changes nothing.
    text = B.build_budget_section(std_budget())
    contains(text, "ceiling, not a floor", "ceiling framing")
    contains(text, "Draw it instead of writing it", "the diagram-replaces-prose rule")
    true("At least" not in text, "the budget must not contain an 'At least' line")


@case("prompt/budget section names the stated duration")
def _():
    contains(B.build_budget_section(std_budget()), "30 min stated", "stated duration")
    with clean_env():
        contains(
            B.build_budget_section(B.budget_for(None)),
            "no duration in the spec",
            "absent duration",
        )


@case("prompt/budget section stays cheap")
def _():
    # Rule 32's fourth lesson: prompt prose has a token cost. This block is per-lesson,
    # so it is cheap by construction — but the number is worth pinning so it stays that
    # way. ~4 chars/token, so 2500 chars is roughly 600 tokens.
    text = B.build_budget_section(std_budget())
    true(len(text) < 2500, f"budget section is {len(text)} chars, budget 2500")


@case("prompt/every band produces a coherent section")
def _():
    with clean_env():
        for minutes in (None, 20, 30, 45, 90):
            text = B.build_budget_section(B.budget_for(minutes))
            true(len(text) > 200, f"{minutes}: section suspiciously short")
            true("{" not in text, f"{minutes}: unformatted f-string braces leaked")


# ---------------------------------------------------------------------------
# lesson_shape.py — counting
# ---------------------------------------------------------------------------


@case("count/sections, svgs, mermaid, assessments, flashcards")
def _():
    doc = lesson(
        sections(5)
        + svgs(3)
        + "\n  <Mermaid>flowchart LR\n A --> B\n  </Mermaid>"
        + '\n  <SingleSelect id="q1"><Prompt>P</Prompt></SingleSelect>'
        + '\n  <MatchPairs id="q2"><Left>a</Left><Right>b</Right></MatchPairs>'
        + '\n  <FlashCard id="f1"><Front>F</Front><Back>B</Back></FlashCard>'
        + '\n  <Game type="hangman">{"word": "cat"}</Game>'
    )
    r = S.measure(doc)
    eq(r.sections, 5, "sections")
    eq(r.svgs, 3, "svgs")
    eq(r.mermaid, 1, "mermaid")
    eq(r.assessments, 2, "assessments")
    eq(r.assessment_types, {"SingleSelect": 1, "MatchPairs": 1}, "assessment types")
    eq(r.flashcards, 1, "flashcards")
    eq(r.games, 1, "games")


@case("count/the <svg> inside <Svg> is not a second diagram")
def _():
    # The measurement error that made a never-met target look exceeded: a
    # case-insensitive count reads every lesson at exactly double.
    r = S.measure(lesson(svgs(2)))
    eq(r.svgs, 2, "two <Svg> wrappers, each holding one <svg>")


@case("count/nested <svg> groups do not inflate the count")
def _():
    doc = lesson(
        '  <Svg><svg viewBox="0 0 10 10"><g><svg viewBox="0 0 5 5" /></g></svg></Svg>'
    )
    eq(S.measure(doc).svgs, 1, "one <Svg> block")


@case("count/self-closing placeholders are not diagrams")
def _():
    # This is the one that decides whether a lesson with zero rendered visuals can pass
    # a floor of 3.
    doc = lesson(svgs(1) + '\n  <Svg concept="a" />\n  <Svg concept="b"/>')
    r = S.measure(doc)
    eq(r.svgs, 1, "embedded diagrams")
    eq(r.svg_placeholders, 2, "placeholders")


@case("count/an empty document measures zero, not an error")
def _():
    for text in ("", None):
        r = S.measure(text)
        eq(r.sections, 0, f"sections for {text!r}")
        eq(r.prose_words, 0, f"words for {text!r}")
        eq(r.svgs, 0, f"svgs for {text!r}")


@case("count/malformed XML still measures")
def _():
    # Phase 1c runs BEFORE the validation loop has repaired anything, so the measurement
    # must never depend on a parse. An unclosed <Section> is the common real case.
    doc = "<Lesson><Section><Body>one two three</Body>" + svgs(3)
    r = S.measure(doc)
    eq(r.prose_words, 3, "prose words in an unclosed document")
    eq(r.svgs, 3, "svgs in an unclosed document")


# ---------------------------------------------------------------------------
# lesson_shape.py — word counting exclusions
# ---------------------------------------------------------------------------


@case("words/prose counts Body and headings")
def _():
    doc = lesson(
        f'  <Section type="concept"><H1>{words(3)}</H1>'
        f"<H2>{words(2)}</H2><Body>{words(10)}</Body></Section>"
    )
    eq(S.measure(doc).prose_words, 15, "H1 + H2 + Body")


@case("words/Code is excluded")
def _():
    doc = lesson(
        f'  <Section type="code"><Body>{words(5)}</Body>'
        f'<Code lang="python">{words(500)}</Code></Section>'
    )
    eq(S.measure(doc).prose_words, 5, "code text must not count")


@case("words/Mermaid is excluded")
def _():
    doc = lesson(
        f'  <Section type="concept"><Body>{words(5)}</Body></Section>'
        f"\n  <Mermaid>flowchart LR\n {words(100)}\n  </Mermaid>"
    )
    eq(S.measure(doc).prose_words, 5, "mermaid source must not count")


@case("words/Svg labels are excluded — the incentive must not invert")
def _():
    # Directionally load-bearing, not cosmetic: if an SVG's <text> labels counted, then
    # "draw it instead of writing it" would RAISE the measured word count and the visual
    # floor would fight the word ceiling.
    body = f'  <Section type="concept"><Body>{words(5)}</Body></Section>'
    labels = "".join(f'<text x="1" y="{i}">{words(20)}</text>' for i in range(5))
    doc = lesson(body + f'\n  <Svg><svg viewBox="0 0 10 10">{labels}</svg></Svg>')
    eq(S.measure(doc).prose_words, 5, "svg labels must not count")


@case("words/Game payload strings are excluded")
def _():
    body = f'  <Section type="concept"><Body>{words(5)}</Body></Section>'
    payload = '{"title": "' + words(50) + '"}'
    doc = lesson(body + f'\n  <Game type="hangman">{payload}</Game>')
    eq(S.measure(doc).prose_words, 5, "game payload must not count")


@case("words/assessment text is excluded — it is budgeted by count")
def _():
    # Counting it twice would make a quiz-heavy lesson read as verbose, and it is why the
    # baseline is 1848 rather than the 2513 an inclusive count gives.
    body = f'  <Section type="concept"><Body>{words(5)}</Body></Section>'
    quiz = (
        '\n  <SingleSelect id="q1"><Prompt>' + words(30) + "</Prompt>"
        "<Options><Option correct=\"true\">" + words(20) + "</Option></Options>"
        "</SingleSelect>"
    )
    card = '\n  <FlashCard id="f1"><Front>' + words(15) + "</Front><Back>" + words(
        15
    ) + "</Back></FlashCard>"
    eq(S.measure(lesson(body + quiz + card)).prose_words, 5, "assessment text")


@case("words/XML comments are excluded")
def _():
    body = f'  <Section type="concept"><Body>{words(5)}</Body></Section>'
    doc = lesson(body + f"\n  <!-- {words(100)} -->")
    eq(S.measure(doc).prose_words, 5, "comment text")


@case("words/inline markup tag names are not words")
def _():
    doc = lesson(
        '  <Section type="concept"><Body>one <strong>two</strong> '
        "three<br/>four</Body></Section>"
    )
    eq(S.measure(doc).prose_words, 4, "one two three four")


@case("words/blanking preserves length so offsets stay valid")
def _():
    doc = lesson(sections(3) + svgs(2))
    eq(len(S._blank_opaque(doc)), len(doc), "blanked length")
    eq(
        S._blank_opaque(doc).count("\n"),
        doc.count("\n"),
        "blanked line count",
    )


@case("words/reading_minutes at 200 wpm")
def _():
    eq(S.WORDS_PER_MINUTE, 200, "the convention the baseline was quoted at")
    doc = lesson(f'  <Section type="concept"><Body>{words(1000)}</Body></Section>')
    eq(S.measure(doc).reading_minutes, 5.0, "1000 words")


# ---------------------------------------------------------------------------
# lesson_shape.py — findings
# ---------------------------------------------------------------------------


@case("check/a lesson inside budget has no findings")
def _():
    b = std_budget()
    doc = lesson(
        sections(b.sections[0], each=b.words[0] // b.sections[0])
        + svgs(b.svgs[0])
        + "\n  <Mermaid>flowchart LR\n A --> B\n  </Mermaid>"
        + "".join(
            f'\n  <SingleSelect id="q{i}"><Prompt>P</Prompt></SingleSelect>'
            for i in range(b.assessments[0])
        )
        + "".join(
            f'\n  <FlashCard id="f{i}"><Front>F</Front><Back>B</Back></FlashCard>'
            for i in range(b.flashcards[0])
        )
        + game()
    )
    r = S.check(doc, b)
    eq(codes(r), [], f"a lesson written to budget must be clean; got {r.one_line()}")


@case("LS-SVG-FLOOR/TOO_FEW_SVGS is hard")
def _():
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(b.svg_floor - 1) + game()), b)
    contains(str(codes(r)), "TOO_FEW_SVGS", "code")
    eq(len(r.hard), 1, "exactly one hard finding")
    eq(r.has_hard, True, "has_hard")
    finding = r.hard[0]
    eq(finding.rule_id, "LS-SVG-FLOOR", "rule id")
    eq(finding.severity, S.HARD, "severity")
    # Rule 24: the message must name the fix's magnitude, or the retry cannot act on it.
    contains(finding.message, "1 more needed", "the message must say how many")


@case("LS-SVG-FLOOR/at the floor exactly is clean")
def _():
    # A gate that cannot be satisfied is as bad as one that never fires.
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(b.svg_floor) + game()), b)
    eq([f.code for f in r.hard], [], "at the floor")


@case("LS-SVG-FLOOR/UNRESOLVED_SVG_PLACEHOLDER is hard even above the floor")
def _():
    b = std_budget()
    doc = lesson(sections(5) + svgs(b.svg_floor) + game() + '\n  <Svg concept="x" />')
    r = S.check(doc, b)
    hard = [f.code for f in r.hard]
    eq(hard, ["UNRESOLVED_SVG_PLACEHOLDER"], "a placeholder renders as nothing")


@case("LS-SVG-FLOOR/placeholders do not count toward the floor")
def _():
    b = std_budget()
    doc = lesson(sections(5) + svgs(1) + '\n  <Svg concept="a" />\n  <Svg concept="b"/>')
    r = S.check(doc, b)
    codes_ = [f.code for f in r.hard]
    true("TOO_FEW_SVGS" in codes_, f"1 real + 2 placeholders is below the floor: {codes_}")


# ---------------------------------------------------------------------------
# lesson_shape.py — LS-GAME-FLOOR
#
# The floor and the ceiling are both 1, for two different reasons. The floor: nothing
# has ever counted games per lesson, and the course-level census permits 70% of lessons
# to have none. The ceiling: `maxPerLesson: 1` is the registry's statement and the
# parser does NOT enforce it, so a second game would validate clean and ship.
# ---------------------------------------------------------------------------


@case("LS-GAME-FLOOR/no game is hard")
def _():
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(b.svg_floor)), b)
    hard = [f.code for f in r.hard]
    eq(hard, ["NO_GAME"], f"a game-free lesson must block once: {hard}")
    finding = r.hard[0]
    eq(finding.rule_id, "LS-GAME-FLOOR", "rule id")
    eq(finding.severity, S.HARD, "severity")
    contains(finding.message, "floor is 1", "the message must name the floor")


@case("LS-GAME-FLOOR/exactly one game is clean")
def _():
    # A gate that cannot be satisfied is as bad as one that never fires.
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(b.svg_floor) + game()), b)
    eq([f.code for f in r.hard], [], "one game at the floor")


@case("LS-GAME-FLOOR/two games is hard — the parser does not cap it")
def _():
    b = std_budget()
    doc = lesson(sections(5) + svgs(b.svg_floor) + game() + game("sort-the-court"))
    r = S.check(doc, b)
    eq([f.code for f in r.hard], ["TOO_MANY_GAMES"], "two games must block")
    contains(r.hard[0].message, "maxPerLesson", "the message must cite the registry")


@case("LS-GAME-FLOOR/GAME_FLOOR=0 disables it")
def _():
    # The knob a run uses when games are deliberately off. It must disable the ceiling
    # too, or "no games wanted" would still reject a lesson that has one.
    with env(GAME_FLOOR="0", SVG_FLOOR=None, LESSON_BUDGET_BAND=None):
        b = B.budget_for(30)
        eq(b.game_floor, 0, "floor disabled")
        eq(S.check(lesson(sections(5) + svgs(b.svg_floor)), b).hard, [], "none")
        eq(S.check(lesson(sections(5) + svgs(b.svg_floor) + game()), b).hard, [], "one")
        eq(
            S.check(lesson(sections(5) + svgs(b.svg_floor) + game() + game()), b).hard,
            [],
            "two",
        )


@case("LS-GAME-FLOOR/GAME_FLOOR garbage falls back to the default, loudly")
def _():
    for bad in ("one", "-1", "   "):
        with env(GAME_FLOOR=bad, SVG_FLOOR=None, LESSON_BUDGET_BAND=None):
            eq(B.budget_for(30).game_floor, B.GAME_FLOOR, f"GAME_FLOOR={bad!r}")


@case("LS-GAME-FLOOR/a game inside <Code> is not a game")
def _():
    # A lesson TEACHING MLAI must not count as HAVING a game. Same exclusion as
    # `game_census` in workers/phases/curriculum.py. Measured there: 0 occurrences of
    # `<Game` across all 1091 local .mlai files, so this is for a future false positive.
    b = std_budget()
    taught = (
        '\n  <Code lang="xml">&lt;Game type="hangman"&gt;{}&lt;/Game&gt;</Code>'
        '\n  <Code lang="xml"><Game type="hangman">{}</Game></Code>'
    )
    r = S.check(lesson(sections(5) + svgs(b.svg_floor) + taught), b)
    eq(S.measure(lesson(taught)).games, 0, "a <Game> inside <Code> is an example")
    contains(str([f.code for f in r.hard]), "NO_GAME", "so the lesson is still game-free")


@case("LS-GAME-FLOOR/a diagram inside <Code> is not a diagram either")
def _():
    # The same exclusion, on the rule that already existed — `measure()` counted every
    # tag on the RAW text before LS-GAME-FLOOR needed this, so an MLAI-teaching lesson
    # could reach the SVG floor on quoted examples alone.
    taught = "\n".join(
        '  <Code lang="xml"><Svg><svg viewBox="0 0 1 1"/></Svg></Code>' for _ in range(4)
    )
    m = S.measure(lesson(taught))
    eq(m.svgs, 0, "quoted <Svg> examples are not diagrams")
    eq(m.svg_placeholders, 0, "nor placeholders")


@case("LS-GAME-FLOOR/both floors miss — one prompt naming both")
def _():
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(0)), b)
    eq(sorted(f.code for f in r.hard), ["NO_GAME", "TOO_FEW_SVGS"], "both fire")
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai", [], ["hangman", "sort-the-court"])
    contains(text, "diagrams and its interactive game", "the opening names both")
    contains(text, "generate_svg", "the SVG half survives")
    contains(text, "`hangman`", "the game half names the valid types")


@case("topup/game half is self-sufficient and states the INVERTED escaping rule")
def _():
    # The one line that cannot be dropped: a <Game> payload is a plain React child, so
    # backticks reach the student literally while entities decode. That is the opposite
    # of the <Body> rule the model has followed all lesson (AGENTS.md rule 32).
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(b.svg_floor)), b)
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai", [], ["hangman"])
    contains(text, "never backticks", "backticks are forbidden in a payload")
    contains(text, "&lt;", "entities are the escaping form here")
    contains(text, "INVALID_CHILD", "placement: not inside a <Section>")
    contains(text, "UNKNOWN_GAME_TYPE", "and why the type must be exact")
    # It must NOT ask for diagrams: this lesson already has its three.
    true("generate_svg" not in text, f"no SVG instructions on a game-only miss: {text}")


@case("topup/too many games is told to delete, not to add")
def _():
    b = std_budget()
    doc = lesson(sections(5) + svgs(b.svg_floor) + game() + game("sort-the-court"))
    text = S.build_topup_prompt(S.check(doc, b), b, "/tmp/x.mlai", [], ["hangman"])
    contains(text, "delete 1 of them", "the fix is a deletion")
    true("Add one now" not in text, "and must not also ask for another game")


@case("topup/no game types available still produces a usable prompt")
def _():
    # `registered_game_types` fails open to [] when the guide is missing. The prompt must
    # still be actionable rather than naming an empty list.
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(b.svg_floor)), b)
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai", [], [])
    contains(text, "the catalog", "falls back to the catalog in the system prompt")
    true("from  —" not in text, "no empty type list")


@case("LS-GAME-FLOOR/the budget prompt states the rule the gate enforces")
def _():
    # Rule 26: a rule enforced by a gate but absent from the prompt is a trap — the
    # model is failed for something it was never told. And the row must vanish when the
    # floor is disabled, rather than telling the writer to produce "exactly 0".
    b = std_budget()
    table = B.build_budget_section(b)
    contains(table, "`<Game>` blocks", "the row is present")
    contains(table, "exactly 1", "and states the number")
    eq(table.count("`<Game>` blocks"), 1, "one row, not two")
    with env(GAME_FLOOR="0", SVG_FLOOR=None, LESSON_BUDGET_BAND=None):
        off = B.build_budget_section(B.budget_for(30))
    true("`<Game>` blocks" not in off, f"no row when the floor is off: {off}")


@case("LS-WORDS/WORD_COUNT over and under, advisory")
def _():
    b = std_budget(words=(1000, 1300))
    over = S.check(lesson(sections(5, each=400) + svgs(3) + game()), b)
    contains(str(codes(over)), "WORD_COUNT", "over budget")
    true(all(f.severity == S.ADVISORY for f in over.findings), "must be advisory")
    contains([f for f in over.findings if f.code == "WORD_COUNT"][0].message, "(over)", "over")

    under = S.check(lesson(sections(2, each=10) + svgs(3) + game()), b)
    contains(
        [f for f in under.findings if f.code == "WORD_COUNT"][0].message,
        "(under)",
        "under",
    )


@case("LS-WORDS/never hard — 'cut 400 words' is not a fix the model can carry out")
def _():
    b = std_budget()
    r = S.check(lesson(sections(20, each=400) + svgs(b.svg_floor) + game()), b)
    eq(r.hard, [], "an enormous lesson must still not block")
    true(len(r.advisory) >= 2, f"but it must be reported: {codes(r)}")


@case("LS-SECTIONS/SECTION_COUNT advisory")
def _():
    b = std_budget(sections=(5, 7))
    r = S.check(lesson(sections(13, each=5) + svgs(3)), b)
    contains(str(codes(r)), "SECTION_COUNT", "13 sections against a 5-7 budget")


@case("LS-MERMAID/MERMAID_COUNT advisory")
def _():
    b = std_budget(mermaid=(1, 2))
    r = S.check(lesson(sections(5) + svgs(3)), b)
    contains(str(codes(r)), "MERMAID_COUNT", "zero Mermaid against a 1-2 budget")


@case("LS-ASSESS/ASSESSMENT_COUNT advisory")
def _():
    b = std_budget(assessments=(4, 5))
    quizzes = "".join(
        f'\n  <SingleSelect id="q{i}"><Prompt>P</Prompt></SingleSelect>' for i in range(10)
    )
    r = S.check(lesson(sections(5) + svgs(3) + quizzes), b)
    contains(str(codes(r)), "ASSESSMENT_COUNT", "10 assessments against a 4-5 budget")


@case("LS-FLASHCARDS/FLASHCARD_COUNT advisory")
def _():
    b = std_budget(flashcards=(3, 4))
    cards = "".join(
        f'\n  <FlashCard id="f{i}"><Front>F</Front><Back>B</Back></FlashCard>'
        for i in range(9)
    )
    r = S.check(lesson(sections(5) + svgs(3) + cards), b)
    contains(str(codes(r)), "FLASHCARD_COUNT", "9 flashcards against a 3-4 budget")


@case("check/every finding cites a rule id and a known severity")
def _():
    b = std_budget()
    r = S.check(lesson(sections(20, each=400)), b)
    true(len(r.findings) >= 3, f"expected several findings, got {codes(r)}")
    for f in r.findings:
        true(f.rule_id.startswith("LS-"), f"rule id {f.rule_id!r}")
        true(f.severity in (S.HARD, S.ADVISORY), f"severity {f.severity!r}")
        contains(str(f), f.rule_id, "__str__ must cite the rule id")
        contains(str(f), f.code, "__str__ must cite the code")


@case("check/FlashCard is not counted as an assessment")
def _():
    # It is reinforcement, budgeted separately. Conflating them would make the
    # assessment ceiling unreachable for any lesson with flashcards.
    true("FlashCard" not in S.ASSESSMENT_TAGS, "FlashCard must not be an assessment tag")
    doc = lesson('  <FlashCard id="f1"><Front>F</Front><Back>B</Back></FlashCard>')
    r = S.measure(doc)
    eq(r.assessments, 0, "assessments")
    eq(r.flashcards, 1, "flashcards")


@case("check/all six assessment types are recognised")
def _():
    # From LESSON_TOP_LEVEL_TAGS in vibely-v2-parser's lesson.ts. A type missing here
    # would silently under-count and make an over-budget lesson look fine.
    eq(
        sorted(S.ASSESSMENT_TAGS),
        ["FillBlanks", "MatchPairs", "MultiSelect", "SingleSelect", "SortQuiz", "Subjective"],
        "assessment tags",
    )
    doc = lesson("".join(f'\n  <{tag} id="a{i}"/>' for i, tag in enumerate(S.ASSESSMENT_TAGS)))
    eq(S.measure(doc).assessments, 6, "one of each")


# ---------------------------------------------------------------------------
# lesson_shape.py — one_line and the marker constraint
# ---------------------------------------------------------------------------


@case("one_line/contains no colon")
def _():
    # courses.py::_parse_marker splits a ##PHASE## body on ':' before splitting fields on
    # the first '='. A colon here would silently truncate the census in the phase
    # metadata.
    line = S.measure(lesson(sections(5) + svgs(3))).one_line()
    true(":" not in line, f"one_line must be colon-free: {line!r}")


@case("one_line/states every measured number")
def _():
    r = S.measure(lesson(sections(5) + svgs(3)))
    line = r.one_line()
    for key in ("words=", "read=", "sections=", "svg=", "mermaid=", "assess=", "flashcards=", "games="):
        contains(line, key, "one_line")


# ---------------------------------------------------------------------------
# lesson_shape.py — top-up prompt (rule 24: fixable by the thing it names)
# ---------------------------------------------------------------------------


@case("topup/names the tool, the count and the gap")
def _():
    b = std_budget()
    r = S.check(lesson(sections(5) + svgs(1)), b)
    text = S.build_topup_prompt(r, b, "/tmp/lesson.mlai")
    contains(text, "generate_svg", "the tool to call")
    contains(text, "Add **2** more", "how many are missing")
    contains(text, "lesson_excerpt", "the grounding argument")
    contains(text, "/tmp/lesson.mlai", "the file to edit")


@case("topup/says nothing about prose length")
def _():
    # Rule 24 exactly. The retry exists to add a diagram; if it also mentions the word
    # ceiling, the model pays for the diagram by cutting explanation.
    b = std_budget()
    r = S.check(lesson(sections(20, each=400) + svgs(1)), b)
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai").lower()
    for forbidden in ("word", "shorten", "too long", "trim", "concise"):
        if forbidden == "shorten":
            # "Do not shorten the existing lesson text" is the one legitimate use.
            contains(text, "do not shorten", "the do-not-shorten instruction")
            continue
        true(forbidden not in text, f"the top-up must not mention {forbidden!r}")


@case("topup/mentions placeholders when that is the defect")
def _():
    b = std_budget()
    doc = lesson(sections(5) + svgs(3) + '\n  <Svg concept="x" />')
    r = S.check(doc, b)
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai")
    contains(text, "placeholder", "placeholders named")
    true("Add **" not in text, "at the floor already — must not ask for more diagrams")


@case("topup/section candidates are included and capped")
def _():
    b = std_budget()
    doc = lesson(sections(30, each=5) + svgs(1) + game())
    r = S.check(doc, b)
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai", S.sections_without_visuals(doc))
    contains(text, "Heading 0", "a candidate heading")
    # Capped so a 30-section lesson does not produce a 30-line prompt.
    # Counted on the heading lines specifically, not every "- " bullet: the game half of
    # this prompt is a bullet list too, so a loose count would measure two things at once.
    headings = text.count("\n- Heading")
    true(headings <= 12, f"candidate list must be capped, got {headings}")


@case("topup/no candidates still produces a usable prompt")
def _():
    b = std_budget()
    r = S.check(lesson(svgs(1)), b)
    text = S.build_topup_prompt(r, b, "/tmp/x.mlai", [])
    contains(text, "generate_svg", "the tool is still named")
    true("candidates" not in text, "no empty candidate heading")


# ---------------------------------------------------------------------------
# lesson_shape.py — sections_without_visuals
# ---------------------------------------------------------------------------


@case("visuals/a heading with a diagram right after it is not a candidate")
def _():
    doc = lesson(
        '  <Section type="concept"><H2>Covered</H2><Body>x</Body></Section>' + svgs(1)
    )
    eq(S.sections_without_visuals(doc), [], "the diagram follows the heading")


@case("visuals/a heading with no diagram nearby is a candidate")
def _():
    doc = lesson(
        f'  <Section type="concept"><H2>Bare</H2><Body>{words(400)}</Body></Section>'
    )
    eq(S.sections_without_visuals(doc), ["Bare"], "no diagram within the window")


@case("visuals/a diagram BEFORE a heading does not cover it")
def _():
    doc = lesson(
        svgs(1) + f'\n  <Section type="concept"><H2>After</H2>'
        f"<Body>{words(400)}</Body></Section>"
    )
    eq(S.sections_without_visuals(doc), ["After"], "only what follows counts")


@case("visuals/Mermaid counts as a visual too")
def _():
    doc = lesson(
        '  <Section type="concept"><H2>Flow</H2><Body>x</Body></Section>'
        "\n  <Mermaid>flowchart LR\n A --> B\n  </Mermaid>"
    )
    eq(S.sections_without_visuals(doc), [], "Mermaid covers the heading")


@case("visuals/heading markup is stripped")
def _():
    doc = lesson(
        f'  <Section type="concept"><H2>The <strong>GIL</strong> explained</H2>'
        f"<Body>{words(400)}</Body></Section>"
    )
    eq(S.sections_without_visuals(doc), ["The GIL explained"], "markup stripped")


@case("visuals/never raises on junk")
def _():
    for text in ("", None, "<H2>unclosed", "<<<>>>"):
        S.sections_without_visuals(text)


# ---------------------------------------------------------------------------
# Corpus — the baseline the next run is compared against
# ---------------------------------------------------------------------------

CORPUS_ROOT = Path(
    os.getenv("LESSON_CORPUS_ROOT", str(Path(__file__).resolve().parent.parent / "test_curriculum"))
)


def corpus() -> list[Path]:
    if not CORPUS_ROOT.is_dir():
        raise Skip(f"{CORPUS_ROOT} is not a directory")
    files = sorted(CORPUS_ROOT.rglob("*.mlai"))
    if not files:
        raise Skip(f"no .mlai files under {CORPUS_ROOT}")
    return files


@case("corpus/measures every lesson without raising")
def _():
    for path in corpus():
        S.measure(path.read_text(encoding="utf-8", errors="replace"))


@case("corpus/baseline — the median lesson is over every band's ceiling")
def _():
    # The reason this change exists. If a future corpus makes this case fail, the shrink
    # worked; re-read the numbers and update them rather than loosening the assertion.
    reports = [S.measure(p.read_text(encoding="utf-8", errors="replace")) for p in corpus()]
    med_words = statistics.median(r.prose_words for r in reports)
    med_sections = statistics.median(r.sections for r in reports)
    with clean_env():
        ceiling = B.budget_for(45)  # the most generous band
    true(
        med_words > ceiling.words[1],
        f"baseline median {med_words} words vs the deep ceiling {ceiling.words[1]}",
    )
    true(
        med_sections > ceiling.sections[1],
        f"baseline median {med_sections} sections vs the deep ceiling "
        f"{ceiling.sections[1]}",
    )


@case("corpus/baseline — the stated 3-4 SVG target was never met")
def _():
    # Measured with the case-sensitive counter. A case-insensitive one reads double and
    # makes this look comfortably exceeded, which is how it went unnoticed for months.
    reports = [S.measure(p.read_text(encoding="utf-8", errors="replace")) for p in corpus()]
    med = statistics.median(r.svgs for r in reports)
    with clean_env():
        floor = B.budget_for(30).svg_floor
    true(
        med < floor,
        f"baseline median {med} <Svg> vs floor {floor} — if this now passes, the corpus "
        f"was regenerated with the floor in place",
    )


@case("corpus/no lesson counts its own <svg> children as diagrams")
def _():
    # The double-count, pinned on real files: an insensitive count must be strictly
    # larger on any lesson that has a diagram at all.
    import re

    found_any = False
    for path in corpus():
        text = path.read_text(encoding="utf-8", errors="replace")
        sensitive = len(re.findall(r"<Svg\b", text))
        insensitive = len(re.findall(r"<svg\b", text, re.I))
        if sensitive:
            found_any = True
            true(
                insensitive > sensitive,
                f"{path.name}: sensitive {sensitive}, insensitive {insensitive} — "
                f"expected the insensitive count to be inflated",
            )
        eq(S.measure(text).svgs, sensitive - len(re.findall(r"<Svg\b[^>]*/>", text)),
           f"{path.name}: measured svgs")
    true(found_any, "no corpus lesson had an <Svg> block at all")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run(filters: list[str]) -> int:
    selected = [
        (name, fn, xf)
        for name, fn, xf in CASES
        if not filters or any(f.lower() in name.lower() for f in filters)
    ]

    passed = failed = skipped = xfailed = xpassed = 0
    failures: list[tuple[str, str]] = []
    skips: list[tuple[str, str]] = []

    for name, fn, xf in selected:
        try:
            fn()
        except Skip as exc:
            skipped += 1
            skips.append((name, str(exc)))
            print(f"  SKIP  {name}  ({exc})")
            continue
        except AssertionError as exc:
            if xf:
                xfailed += 1
                print(f"  xfail {name}  ({exc})")
            else:
                failed += 1
                failures.append((name, str(exc)))
                print(f"  FAIL  {name}\n        {exc}")
            continue
        except Exception:
            import traceback

            detail = traceback.format_exc(limit=3).strip().splitlines()[-1]
            if xf:
                xfailed += 1
                print(f"  xfail {name}  ({detail})")
            else:
                failed += 1
                failures.append((name, detail))
                print(f"  ERROR {name}\n        {detail}")
            continue

        if xf:
            xpassed += 1
            print(f"  XPASS {name}  <- fixed; drop the xfail marker")
        else:
            passed += 1
            print(f"  ok    {name}")

    print(f"\n{passed} passed, {failed} failed, {xfailed} xfail, {xpassed} xpass, {skipped} skipped")

    if skips:
        print(
            "\n!! CORPUS_SKIPPED — the baseline cases did not run. A skip is not a pass.\n"
            f"   Set LESSON_CORPUS_ROOT to a directory of generated .mlai files "
            f"(tried {CORPUS_ROOT})."
        )
    if xpassed:
        print(f"\n{xpassed} case(s) now pass that were marked xfail. Remove the marker.")
    if failures:
        print("\nFailures:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, _, xf in CASES:
            print(f"{'xfail' if xf else '     '} {name}")
        return 0
    return run([a for a in argv if not a.startswith("-")])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
