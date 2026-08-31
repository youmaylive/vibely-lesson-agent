"""Measure the shape of a written lesson: sections, prose words, visuals, assessments.

Stdlib only, no SDK, on the `svg_geometry.py` precedent — one check per checkable rule,
every `Finding` cites the rule ID it breaks, and the module runs with no credentials so
it can be tested inside the worker image.

What this is for
----------------
`budget.py` tells the writer what shape to aim for. This tells us what shape it actually
produced. AGENTS.md rule 26: a rule stated in a prompt and enforced by nothing is a
regression no test will catch — and this project already has the receipts. The
generation prompt has asked for "3-4 `generate_svg` calls" since the SVG framework
landed; measured across the 5 lessons this pipeline has written, the median is **2** and
the minimum is **1**. Nothing noticed, because nothing counted.

That number is also why `_count_tag` is case-sensitive. A case-insensitive count reads
4/4/2/4/8 rather than 2/2/1/2/4, because it counts the `<Svg>` wrapper *and* the `<svg>`
element inside it — exactly double, on every lesson, which is enough to make a target
that was never met look comfortably exceeded.

Hard vs advisory, and why the split is not a matter of taste
-----------------------------------------------------------
Two rules are hard: `LS-SVG-FLOOR` and `LS-GAME-FLOOR`. Two reasons, and both come from
rules this project learned by hitting them.

Rule 24 — the retry message must be fixable by the thing it names. "Call `generate_svg`
once more and embed the result" is a complete, mechanical instruction, and so is "add one
`<Game type="hangman">` block here with these fields". "Your prose is 400 words over
budget" is not: the model can cut the wrong 400 words, and it has no way to know which
paragraph was load-bearing. So length findings inform a human and the per-course census;
they are never fed to the fix loop.

`LS-GAME-FLOOR` exists because nothing has ever counted games **per lesson**. The only
game check is the course-level census in `workers/phases/curriculum.py`, and at its
`GAME_FLOOR_RATE = 0.30` default 70% of lessons may legitimately carry none — while three
prompt copies told the writer "if no catalogued type fits, write no `<Game>` block at
all". Its ceiling is hard for a different reason: `maxPerLesson: 1` is the registry's own
statement and the parser does **not** enforce it, so a second game validates clean and
ships.

Rule 24 again, plus rule 31 — where a check runs decides what it can do. This runs on a
**generation** path: a five-hour, ~$64 course run. `MAX_VALIDATION_ATTEMPTS = 500` has
no spend cap, so nothing advisory may enter that loop, and even the hard rule gets ONE
bounded top-up pass in `agent.py` before it gives up, prints loudly and ships the
lesson. A missing third diagram makes a lesson weaker; refusing to ship over it is the
wrong trade. Compare the *write* path (an admin edit), which correctly fails closed.

Counting rules, and why they are not obvious
--------------------------------------------
`prose_words` counts text inside `<Body>`, `<H1>`, `<H2>` and `<H3>` only, after the
`<Code>`, `<Mermaid>`, `<Svg>` and `<Game>` subtrees and XML comments have been blanked.
Three consequences worth stating, because each one was a real trap:

  * Code is excluded, so a code-heavy lesson is not punished for teaching with examples.
    (The baseline measurement excluded it too, so the numbers compare.)
  * Blanking `<Svg>`/`<Game>` matters more than it looks: an SVG's `<text>` labels and a
    game payload's JSON strings are words, and counting them would make "draw it instead
    of writing it" *raise* the measured word count — inverting the incentive the budget
    exists to create. This is the same exclusion `game_census` makes in
    `workers/phases/curriculum.py` so a lesson *teaching* MLAI is not counted as
    *having* a game.
  * Assessment text (`<Prompt>`, `<Option>`, `<Front>`, `<Back>`, `<Item>`) is excluded
    from the word count because those blocks are budgeted by *count* instead. Counting
    them twice would make a lesson with 5 quizzes look verbose.

Counting is by regex, not by an XML parse, and that is deliberate: this runs on files
that may not yet be well-formed (it fires before the validation loop has repaired them),
and a parse failure here must not cost the measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from budget import Budget

# ---------------------------------------------------------------------------
# Severities — same vocabulary as svg_geometry.py
# ---------------------------------------------------------------------------
HARD = "hard"
ADVISORY = "advisory"

# The six interactive assessment types, from `LESSON_TOP_LEVEL_TAGS` in
# `vibely-v2-parser/src/components/content/lesson.ts`. FlashCard is deliberately NOT in
# this list — it is reinforcement rather than assessment, and it is budgeted separately.
ASSESSMENT_TAGS = (
    "SingleSelect",
    "MultiSelect",
    "FillBlanks",
    "MatchPairs",
    "SortQuiz",
    "Subjective",
)

# Subtrees whose text is not lesson prose. See the module docstring — `Svg` and `Game`
# are the two that matter, because including them would penalise using a diagram.
_OPAQUE_TAGS = ("Code", "Mermaid", "Svg", "Game")

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_PROSE_RE = re.compile(r"<(Body|H1|H2|H3)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]*>", re.S)
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")

# Reading speed for turning a word count into minutes. 200 wpm is the figure the
# baseline was quoted at; it is a convention, not a measurement of these learners.
WORDS_PER_MINUTE = 200


def _blank_opaque(text: str) -> str:
    """Blank comments and the opaque subtrees, preserving length.

    Length is preserved (whitespace of the same size) so that any offset or line number
    derived from the result still points at the right place in the original — the same
    trick the API's truncation scan uses when it blanks comments and CDATA.
    """
    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = _COMMENT_RE.sub(blank, text)
    for tag in _OPAQUE_TAGS:
        # Non-greedy to the matching close tag; also swallow self-closing forms, which
        # `<Svg concept="..." />` placeholders use before `resolve_svgs` runs.
        text = re.sub(
            rf"<{tag}\b[^>]*/>|<{tag}\b[^>]*>.*?</{tag}>",
            blank,
            text,
            flags=re.S | re.I,
        )
    return text


_EXAMPLE_CONTENT_RE = re.compile(r"(<(Code|Mermaid)\b[^>]*>)(.*?)(</\2>)", re.S | re.I)


def _blank_examples(text: str) -> str:
    """Blank comments and the *contents* of `<Code>`/`<Mermaid>`, keeping their tags.

    Element counts come from this, not from the raw file, so a lesson that *teaches*
    MLAI — a `<Code>` block showing `<Game type="hangman">`, or a `<Svg>` skeleton — is
    not counted as *having* a game or a diagram. This is the same exclusion `game_census`
    makes in `workers/phases/curriculum.py`; measured there: 0 occurrences of `<Game`
    across all 1091 local `.mlai` files today, so it is for a future false positive
    rather than a current one.

    Two functions rather than one, and the difference is load-bearing: `_blank_opaque`
    removes `<Code>`/`<Mermaid>`/`<Svg>`/`<Game>` *wholesale* for the word count, which
    would take the tags with it and drive every count of those elements to zero. Here
    only the contents go, so the elements themselves stay countable.
    """
    def blank_inner(match: re.Match) -> str:
        return match.group(1) + re.sub(r"[^\n]", " ", match.group(3)) + match.group(4)

    text = _COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return _EXAMPLE_CONTENT_RE.sub(blank_inner, text)


def _count_tag(text: str, tag: str) -> int:
    """Occurrences of an opening `<tag …>` (self-closing included), case-sensitive.

    Case-sensitive on purpose: MLAI element names are case-sensitive to the parser
    (`<game>` is `UNKNOWN_ELEMENT`, not a game), so a lower-cased `<svg>` inside an
    `<Svg>` wrapper must not be counted as a second diagram.
    """
    return len(re.findall(rf"<{tag}\b", text))


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """One shape deviation, citing the budget rule it breaks."""

    rule_id: str
    code: str
    severity: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule_id}/{self.code}: {self.message}"


@dataclass
class ShapeReport:
    """What one lesson measured, and how it compares to its budget."""

    sections: int = 0
    prose_words: int = 0
    svgs: int = 0
    svg_placeholders: int = 0
    mermaid: int = 0
    assessments: int = 0
    assessment_types: dict[str, int] = field(default_factory=dict)
    flashcards: int = 0
    games: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def hard(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == HARD]

    @property
    def advisory(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ADVISORY]

    @property
    def has_hard(self) -> bool:
        return bool(self.hard)

    @property
    def reading_minutes(self) -> float:
        return round(self.prose_words / WORDS_PER_MINUTE, 1)

    def one_line(self) -> str:
        """The measurement as a single log line. Contains no `:` — see `curriculum.py`.

        `courses.py::_parse_marker` splits a marker body on `:` before splitting fields
        on the first `=`, so anything that may ride a `##PHASE##` marker must avoid the
        colon. Keeping this line colon-free means it can be logged and carried unchanged.
        """
        return (
            f"words={self.prose_words} read={self.reading_minutes}min "
            f"sections={self.sections} svg={self.svgs} mermaid={self.mermaid} "
            f"assess={self.assessments} flashcards={self.flashcards} "
            f"games={self.games}"
        )


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def measure(content: str) -> ShapeReport:
    """Count a lesson's shape from its .mlai text. Never raises, never parses XML."""
    text = content or ""
    blanked = _blank_opaque(text)
    # Counted on the example-blanked text, never the raw file — see `_blank_examples`.
    counted = _blank_examples(text)

    prose = " ".join(match.group(2) for match in _PROSE_RE.finditer(blanked))
    # Strip any residual inline markup (`<strong>`, `<br/>`) before counting words, so
    # tag names are never counted as prose.
    prose = _TAG_RE.sub(" ", prose)

    types = {tag: _count_tag(counted, tag) for tag in ASSESSMENT_TAGS}

    # `<Svg>` counts embedded diagrams; a self-closing `<Svg ... />` is an UNRESOLVED
    # placeholder and is reported separately. Counting a placeholder as a diagram is how
    # a lesson with zero rendered visuals would pass a floor of 3.
    svg_total = _count_tag(counted, "Svg")
    placeholders = len(re.findall(r"<Svg\b[^>]*/>", counted))

    return ShapeReport(
        sections=_count_tag(counted, "Section"),
        prose_words=len(_WORD_RE.findall(prose)),
        svgs=max(0, svg_total - placeholders),
        svg_placeholders=placeholders,
        mermaid=_count_tag(counted, "Mermaid"),
        assessments=sum(types.values()),
        assessment_types={tag: n for tag, n in types.items() if n},
        flashcards=_count_tag(counted, "FlashCard"),
        games=_count_tag(counted, "Game"),
    )


def _range_finding(
    rule_id: str,
    code: str,
    label: str,
    actual: int,
    low: int,
    high: int,
    severity: str = ADVISORY,
) -> Finding | None:
    if actual < low:
        return Finding(
            rule_id, code, severity, f"{label} {actual}, budget {low}-{high} (under)"
        )
    if actual > high:
        return Finding(
            rule_id, code, severity, f"{label} {actual}, budget {low}-{high} (over)"
        )
    return None


def check(content: str, budget: Budget) -> ShapeReport:
    """Measure a lesson and judge it against its budget.

    Two hard rules, five advisory. See the module docstring for why the split is what it
    is — in short, only the visual and game floors have a fix the model can actually
    carry out.
    """
    report = measure(content)

    # -- HARD: LS-SVG-FLOOR -------------------------------------------------
    # The one rule that blocks, because it is the one with a mechanical fix. A floor of
    # 0 disables it (SVG_FLOOR=0), which is a legitimate setting for a prose-only run.
    if budget.svg_floor > 0 and report.svgs < budget.svg_floor:
        missing = budget.svg_floor - report.svgs
        report.findings.append(
            Finding(
                "LS-SVG-FLOOR",
                "TOO_FEW_SVGS",
                HARD,
                f"{report.svgs} embedded <Svg> block(s), floor is {budget.svg_floor} — "
                f"{missing} more needed",
            )
        )

    # An unresolved placeholder is a separate defect: `resolve_svgs` should have replaced
    # it, so seeing one means the tool errored or the agent hand-wrote the tag. Hard,
    # because it renders as nothing at all for the student and the fix is the same call.
    if report.svg_placeholders:
        report.findings.append(
            Finding(
                "LS-SVG-FLOOR",
                "UNRESOLVED_SVG_PLACEHOLDER",
                HARD,
                f"{report.svg_placeholders} self-closing <Svg .../> placeholder(s) left "
                f"unresolved — these render as nothing",
            )
        )

    # -- HARD: LS-GAME-FLOOR ------------------------------------------------
    # One playable game per lesson. Hard for the same reason as the SVG floor and no
    # other: the fix is mechanical and complete — "add one `<Game>` block of type X,
    # here, with these fields" — which is what rule 24 requires of anything that enters
    # a retry. `GAME_FLOOR=0` disables it.
    #
    # The ceiling is hard too, and it is not symmetry for its own sake: `maxPerLesson: 1`
    # is the registry's statement, and the parser does NOT enforce it (`LESSON_SCHEMA`
    # has `min: 1` and no maximum), so a second game would validate clean and ship.
    if budget.game_floor > 0 and report.games < budget.game_floor:
        report.findings.append(
            Finding(
                "LS-GAME-FLOOR",
                "NO_GAME",
                HARD,
                f"{report.games} <Game> block(s), floor is {budget.game_floor} — every "
                f"lesson needs a playable game",
            )
        )
    if budget.game_floor > 0 and report.games > budget.game_floor:
        report.findings.append(
            Finding(
                "LS-GAME-FLOOR",
                "TOO_MANY_GAMES",
                HARD,
                f"{report.games} <Game> block(s), the registry allows "
                f"{budget.game_floor} per lesson (maxPerLesson) — remove the extras",
            )
        )

    # -- ADVISORY -----------------------------------------------------------
    for finding in (
        _range_finding(
            "LS-WORDS", "WORD_COUNT", "prose words", report.prose_words, *budget.words
        ),
        _range_finding(
            "LS-SECTIONS", "SECTION_COUNT", "<Section> blocks", report.sections, *budget.sections
        ),
        _range_finding(
            "LS-MERMAID", "MERMAID_COUNT", "<Mermaid> diagrams", report.mermaid, *budget.mermaid
        ),
        _range_finding(
            "LS-ASSESS",
            "ASSESSMENT_COUNT",
            "assessment blocks",
            report.assessments,
            *budget.assessments,
        ),
        _range_finding(
            "LS-FLASHCARDS",
            "FLASHCARD_COUNT",
            "<FlashCard> blocks",
            report.flashcards,
            *budget.flashcards,
        ),
    ):
        if finding is not None:
            report.findings.append(finding)

    return report


# ---------------------------------------------------------------------------
# Top-up feedback
# ---------------------------------------------------------------------------


def _game_topup_lines(
    report: ShapeReport,
    budget: Budget,
    game_types: list[str] | None,
    extra_games: int,
) -> list[str]:
    """The `LS-GAME-FLOOR` half of the top-up message.

    Written to be self-sufficient even though this turn resumes the same session and the
    candidate specs are still in context: rule 32's fourth lesson is that retry feedback
    is a cost, so this stays short, but a message that only works if an earlier turn is
    still in the window is a message that fails silently when it isn't.

    The escaping line is the one that cannot be dropped, because it is the **inverse** of
    the `<Body>` rule the model has been following all lesson: a `<Game>` payload is a
    plain React child, not markdown, so backticks reach the student literally while
    entities decode correctly.
    """
    if extra_games:
        return [
            f"It has **{report.games}** `<Game>` blocks. The registry allows "
            f"**{budget.game_floor}** per lesson (`maxPerLesson`), and the parser does "
            f"not enforce that — so delete {extra_games} of them, keeping the one that "
            f"best fits what this lesson teaches.",
            "",
        ]

    known = ", ".join(f"`{t}`" for t in game_types) if game_types else "the catalog"
    return [
        f"It has **no `<Game>` block**. Every lesson needs exactly "
        f"**{budget.game_floor}** — a game is the only part of the lesson the student "
        f"*does* rather than reads.",
        "",
        f"Add one now, choosing the type from {known} — pick the one whose shape matches "
        f"what a student who understood THIS lesson could do, not the first in the list.",
        "",
        "- A direct child of `<Lesson>`, never inside a `<Section>` (that is "
        "`INVALID_CHILD`).",
        "- Near the end, after the assessments, before the summary.",
        "- Quiz only facets this lesson actually taught — the payload is not checked "
        "against the lesson, so this one is on you.",
        "- **Escaping is the OPPOSITE of `<Body>` here**: use `&lt;` `&gt;` `&amp;` and "
        "**never backticks**. The payload is a plain React child, not markdown, so a "
        "backtick reaches the student literally.",
        "- The type must be spelled exactly as listed. A wrong type is "
        "`UNKNOWN_GAME_TYPE`, which no payload edit can fix.",
        "",
    ]


def build_topup_prompt(
    report: ShapeReport,
    budget: Budget,
    output_file,
    section_headings: list[str] | None = None,
    game_types: list[str] | None = None,
) -> str:
    """The one bounded retry that the hard rules earn.

    Rule 24's second half: the message must be fixable by the thing it names. Each block
    here names the tool or the element, the exact count, and where the gap is — and none
    of them says anything about prose length, because the model would pay for that by
    cutting explanation.

    Two hard rules, so two blocks, and only the unmet ones are included: a lesson that
    has its diagrams and is missing its game must not be told to add diagrams.
    """
    missing = max(0, budget.svg_floor - report.svgs)
    placeholders = report.svg_placeholders
    needs_game = budget.game_floor > 0 and report.games < budget.game_floor
    extra_games = max(0, report.games - budget.game_floor) if budget.game_floor else 0

    shortfalls = []
    if missing or placeholders:
        shortfalls.append("diagrams")
    if needs_game or extra_games:
        shortfalls.append("its interactive game")
    parts = [
        f"The lesson at {output_file} is short on {' and '.join(shortfalls) or 'shape'}.",
        "",
    ]

    if needs_game or extra_games:
        parts += _game_topup_lines(report, budget, game_types, extra_games)

    if not (missing or placeholders):
        return "\n".join(parts).rstrip() + "\n"

    if missing:
        parts.append(
            f"It has **{report.svgs}** embedded `<Svg>` block(s). Every lesson needs at "
            f"least **{budget.svg_floor}**. Add **{missing}** more."
        )
    if placeholders:
        parts.append(
            f"It also has **{placeholders}** self-closing `<Svg ... />` placeholder(s). "
            f"Those render as nothing for the student — replace each one with a real "
            f"`generate_svg` result."
        )

    parts += [
        "",
        "For each one:",
        "1. Pick a concept in this lesson that is structural, spatial, or a process — "
        "something a diagram explains better than a paragraph.",
        "2. Call `generate_svg(concept=..., context=..., lesson_excerpt=...)`, passing "
        "the **actual lesson text you wrote for that part**, verbatim, as "
        "`lesson_excerpt`. Without it the generator invents its own example values and "
        "the labels will not match your lesson.",
        "3. Paste the returned markup verbatim inside `<Svg>...</Svg>`, placed DIRECTLY "
        "under `<Lesson>` (never inside a `<Section>`), right after the text it "
        "illustrates.",
        "",
        "Do not shorten or rewrite the existing lesson text, and do not hand-write "
        "`<svg>` markup. If `generate_svg` returns an ERROR, say so and stop.",
    ]

    if section_headings:
        shown = section_headings[:12]
        parts += [
            "",
            "Sections with no diagram nearby (good candidates):",
            *(f"- {heading}" for heading in shown),
        ]

    return "\n".join(parts)


_HEADING_RE = re.compile(r"<(H1|H2|H3)\b[^>]*>(.*?)</\1>", re.S | re.I)


def sections_without_visuals(content: str, window: int = 1200) -> list[str]:
    """Headings that have no `<Svg>` or `<Mermaid>` within `window` chars after them.

    A crude proximity measure, and deliberately so — it only has to produce *candidates*
    for the top-up prompt. Being wrong costs a suboptimal suggestion, not a failure, and
    the model is free to diagram something else.
    """
    text = content or ""
    visuals = [m.start() for m in re.finditer(r"<(?:Svg|Mermaid)\b", text)]
    out: list[str] = []
    for match in _HEADING_RE.finditer(text):
        start = match.end()
        if any(start <= pos <= start + window for pos in visuals):
            continue
        heading = _TAG_RE.sub(" ", match.group(2))
        heading = " ".join(heading.split())
        if heading:
            out.append(heading)
    return out
