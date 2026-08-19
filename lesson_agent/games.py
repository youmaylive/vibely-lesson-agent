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
                                 payload — or write no game at all

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


def extract_signals(spec_text: str) -> LessonSignals:
    """Parse a lesson spec's markdown into the signals games are matched against.

    Structural, not keyword-based, wherever the structure exists: a spec's
    `## Key Concepts` list IS the set of terms the lesson teaches, and its
    `## Common Misconceptions` list IS a set of claims that are false — which is
    exactly the raw material a judgement game needs. Those two are worth more than
    any amount of scanning the prose.
    """
    signals = LessonSignals(text=spec_text)

    # Title: the first H1, else the first non-empty line.
    for line in spec_text.splitlines():
        if line.startswith("# "):
            signals.title = line[2:].strip()
            break
        if line.strip() and not signals.title:
            signals.title = line.strip()

    # Split on H2/H3 headings and bucket the blocks by what they are called.
    parts = re.split(r"^#{2,3}\s+(.+)$", spec_text, flags=re.MULTILINE)
    # parts = [preamble, heading1, body1, heading2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip().lower()
        body = parts[i + 1]
        for attr, needles in _SECTION_KEYS.items():
            if any(n in heading for n in needles):
                getattr(signals, attr).extend(_bullets(body))
                break

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


def _hits(haystacks: list[str], needles: tuple[str, ...]) -> list[str]:
    """Which needles appear in any haystack, lowercased substring match."""
    blob = " \n ".join(haystacks).lower()
    return [n for n in needles if n in blob]


def _shape_terms(signals: LessonSignals) -> tuple[float, str]:
    """term-recall: does the lesson teach a term the game could hide?"""
    usable = [t for t in signals.key_concepts if _RECALLABLE_TERM.match(t)]
    if usable:
        # Scored on how many, capped: one usable term is enough to author the game,
        # more is mildly better because the author has a choice.
        return min(1.0, 0.6 + 0.1 * len(usable)), (
            f"{len(usable)} of {len(signals.key_concepts)} key concepts are single "
            f"recallable terms (e.g. {usable[0]!r})"
        )
    if signals.key_concepts:
        return 0.1, (
            f"has {len(signals.key_concepts)} key concepts but none match "
            f"[A-Za-z ]{{3,40}} — digits/symbols cannot be guessed on an A-Z keyboard"
        )
    return 0.0, "the spec lists no key concepts"


def _shape_judgement(signals: LessonSignals) -> tuple[float, str]:
    """judgement: is there a rule the student must apply to cases?"""
    if signals.misconceptions:
        # A misconception IS a claim with a correct yes/no verdict and a reason to
        # give back. This is the strongest structural signal in the whole spec.
        return 1.0, (
            f"the spec lists {len(signals.misconceptions)} common misconceptions — "
            f"each is a claim with a correct verdict and an explanation"
        )
    found = _hits([signals.title, *signals.objectives, *signals.outline], _JUDGEMENT_WORDS)
    if found:
        return 0.5, f"objectives/outline mention {found[:3]}"
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
    it did *not* offer. That distinction is load-bearing: measured over the 31 real
    planner specs in `test_curriculum/`, the top score is **1.0 on 31 of 31**, because
    `_shape_terms` saturates at four recallable key concepts and every spec lists six.
    So a withheld spec today means "tied at the top and lost the alphabetical
    tie-break", not "scored lower" — two different facts, and only the first says the
    ranking has stopped discriminating.
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
        tied = [c.game.type for c in dropped if c.score >= cut]
        if tied:
            lines.append(
                f"       ⚠️  cap={len(candidates)} cut {len(tied)} game(s) tied at "
                f"{cut:.2f} with the last offered one, ordered alphabetically, so which "
                f"spec was injected is arbitrary: {', '.join(tied)}"
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
        "One `<Game>` block, at the lesson's top level, near the end — the full contract",
        "is in your system prompt under \"Game block rules\". Read it before writing the",
        "payload; the escaping rules there are NOT the same as for `<Body>`.",
        "",
        "Based on this lesson's content, these game types look like the best fits, in",
        "order. Full authoring specs follow. Choose ONE, or write no `<Game>` block at",
        "all if none of them genuinely suits what this lesson teaches — a forced game",
        "asks the student to practise something the game cannot test.",
        "",
    ]
    for i, c in enumerate(candidates, 1):
        parts.append(f"{i}. `{c.game.type}` — {c.game.tagline}")
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
