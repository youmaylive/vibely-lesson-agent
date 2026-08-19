"""Executed contract for game selection (`games.py`).

Run:
    cd lesson_agent && python3 games.test.py

Stdlib only and credential-free, like `svg_geometry.test.py`, so it runs inside the
worker image with no AWS configuration.

What this suite is for
----------------------
Two claims carry the whole design, and neither is self-evident:

1. **The prompt cost is flat in the number of games.** Asserted here against a
   synthetic 100-game registry, not on the 2 real ones — the real registry cannot
   distinguish "flat" from "small".
2. **A wrong shape inference is cheap.** The inference is written from reasoning about
   what lesson specs look like, which AGENTS.md rule 25 rates at roughly zero without
   measurement. So the tests assert the *containment* properties that make being wrong
   survivable: below the cap nothing is dropped, the order is deterministic, and a
   withheld game is still reachable through the catalog.

The suite also pins the two structural signals, because they are the only parts of
the inference with real evidence behind them: `## Key Concepts` bullets that match
hangman's own `word` pattern, and `## Common Misconceptions` as judgement material.
`load_guide` warning about an unscorable shape is asserted too — that warning is the
only thing standing between "a new content shape was added" and "a game is registered,
valid, documented and silently never chosen".
"""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import games  # noqa: E402
from games import (  # noqa: E402
    GuideUnavailable,
    build_game_prompt_section,
    build_game_rules_section,
    extract_signals,
    load_guide,
    score_shapes,
    select_candidates,
)

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  ✗ {name}" + (f": {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# A real spec's shape, transcribed from test_curriculum/module_04/lesson_04_03.md —
# the headings and bullet style the lesson planner actually emits.
TERM_HEAVY_SPEC = """# Multi-Compartment Models: Detailed Morphology

## Key Insight
Multi-compartment models discretize complex neuronal morphology into coupled
compartments.

## Learning Objectives
- Discretize cable equation into compartmental ODEs
- Construct coupling matrices from morphological data

## Key Concepts
- Compartmental model
- Coupling matrix
- Sparse matrix
- Morphology reconstruction

## Practical Examples
- Simple multi-compartment model: soma + dendrite + axon
"""

MISCONCEPTION_SPEC = """# When to Use const, let and var

## Learning Objectives
- Decide which declaration keyword a situation calls for

## Key Concepts
- Binding
- Mutation

## Common Misconceptions
- Assuming const makes the value immutable rather than the binding
- Believing var and let are interchangeable
- Thinking await freezes the whole page
"""

NO_SIGNAL_SPEC = """# A Reflective Essay on Learning

Some prose with no headings the planner would emit, no bullets, and nothing a game
could consume.
"""

# Terms a term-recall game cannot use: a digit, a hyphen, an over-long phrase.
UNUSABLE_TERMS_SPEC = """# Pandemic Virology

## Key Concepts
- COVID19
- T-CELL
- The rough endoplasmic reticulum organelle system and its many functions
"""


def synthetic_guide(root: Path, count: int, shapes: list[str] | None = None) -> Path:
    """Write a guide directory with `count` games, for the scale tests.

    Real spec files, not stubs: `build_game_prompt_section` reads them off disk, so a
    token-cost measurement against stubs would measure nothing.
    """
    guide = root / "agent-guide"
    (guide / "spec").mkdir(parents=True, exist_ok=True)
    all_shapes = shapes or [
        "term-recall", "ordering", "pairing", "categorisation",
        "procedure", "numeric", "spatial", "judgement",
    ]
    entries = []
    for i in range(count):
        gtype = f"game-{i:03d}"
        shape = all_shapes[i % len(all_shapes)]
        entries.append({
            "type": gtype,
            "label": f"Game {i}",
            "tagline": f"A synthetic game number {i} for scale testing.",
            "contentShapes": [shape],
            "minutes": 3,
            "gradable": True,
            "maxPerLesson": 1,
            "spec": f"spec/{gtype}.md",
        })
        # Sized to the real specs: hangman is 5.9 KB, sort-the-court 11.6 KB.
        (guide / "spec" / f"{gtype}.md").write_text(
            f"# `{gtype}` — Game {i}\n\n" + ("Spec prose. " * 700) + "\n",
            encoding="utf-8",
        )
    (guide / "index.json").write_text(
        json.dumps({"contentShapes": all_shapes, "games": entries}, indent=2),
        encoding="utf-8",
    )
    rows = "\n".join(f"| `{e['type']}` | {e['label']} | {e['tagline']} |" for e in entries)
    (guide / "catalog.md").write_text(f"# Game catalog\n\n{rows}\n", encoding="utf-8")
    (guide / "rules.md").write_text("# Game block rules\n\nThe shared contract.\n", encoding="utf-8")
    return guide


def approx_tokens(text: str) -> int:
    """~4 chars per token — enough to catch a regression of the shape this bounds."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# 1. Signal extraction
# ---------------------------------------------------------------------------
print("1. signal extraction")

s = extract_signals(TERM_HEAVY_SPEC)
check("title from H1", s.title == "Multi-Compartment Models: Detailed Morphology", repr(s.title))
check("key concepts parsed", s.key_concepts == [
    "Compartmental model", "Coupling matrix", "Sparse matrix", "Morphology reconstruction",
], repr(s.key_concepts))
check("objectives parsed", len(s.objectives) == 2, repr(s.objectives))
check("no misconceptions here", s.misconceptions == [], repr(s.misconceptions))
# "Practical Examples" folds into outline — it describes what the lesson does, which is
# the same kind of evidence as the content outline.
check("outline picked up", len(s.outline) == 1, repr(s.outline))

m = extract_signals(MISCONCEPTION_SPEC)
check("misconceptions parsed", len(m.misconceptions) == 3, repr(m.misconceptions))

n = extract_signals(NO_SIGNAL_SPEC)
check("no-signal spec is empty", not (n.key_concepts or n.objectives or n.misconceptions))
check("no-signal spec still has a title", n.title == "A Reflective Essay on Learning", repr(n.title))

# A spec with no headings at all must not raise — the planner's output is not
# guaranteed, and a crash here would take down a whole course run.
check("bare text does not raise", extract_signals("just one line").title == "just one line")
check("empty string does not raise", extract_signals("").title == "")

# ---------------------------------------------------------------------------
# 2. Shape scoring — the two structural rules
# ---------------------------------------------------------------------------
print("2. shape scoring")

term_scores = score_shapes(extract_signals(TERM_HEAVY_SPEC))
check("term-recall scores high on a term-heavy spec",
      term_scores["term-recall"][0] >= 0.9, str(term_scores["term-recall"]))
check("judgement scores low with no misconceptions",
      term_scores["judgement"][0] < 0.6, str(term_scores["judgement"]))

misc_scores = score_shapes(extract_signals(MISCONCEPTION_SPEC))
check("judgement maxes out on listed misconceptions",
      misc_scores["judgement"][0] == 1.0, str(misc_scores["judgement"]))

# The precise part: a term the game physically cannot use must not count as evidence.
# This is hangman's own `word` pattern as a predicate — a digit or a hyphen is
# unguessable on an A-Z keyboard, so such a lesson has no term-recall material even
# though it has a Key Concepts list.
unusable = score_shapes(extract_signals(UNUSABLE_TERMS_SPEC))
check("unusable terms score near zero",
      unusable["term-recall"][0] <= 0.2, str(unusable["term-recall"]))
check("...and the reason says why",
      "A-Z keyboard" in unusable["term-recall"][1], unusable["term-recall"][1])

none_scores = score_shapes(extract_signals(NO_SIGNAL_SPEC))
check("no-signal spec scores zero everywhere",
      all(v[0] == 0.0 for v in none_scores.values()),
      str({k: v[0] for k, v in none_scores.items() if v[0]}))
# Every score carries a reason. A ranking with no explanation is a ranking nobody can
# debug, and `explain()` is the only window into Stage A at runtime.
check("every shape gives a reason",
      all(isinstance(v[1], str) and v[1] for v in term_scores.values()))

# ---------------------------------------------------------------------------
# 3. Selection against the REAL guide
# ---------------------------------------------------------------------------
print("3. selection against the real generated guide")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GAMES_GUIDE_DIR, MAX_GAME_CANDIDATES  # noqa: E402

real_guide_available = (GAMES_GUIDE_DIR / "index.json").is_file()
if not real_guide_available:
    # Loud, and NOT counted as a pass: rule 21. The synthetic tests below still run.
    print(f"  ⚠️  REAL GUIDE MISSING at {GAMES_GUIDE_DIR}")
    print("      Run `npm run build` in vibely-v2/mlai-games. Skipping 6 cases.")
else:
    guide = load_guide(GAMES_GUIDE_DIR)
    check("real guide loads", len(guide.games) >= 2, f"{len(guide.games)} games")
    check("shape vocabulary is fully scorable",
          all(sh in games.SHAPE_EVIDENCE for sh in guide.known_shapes),
          f"unscorable: {[s for s in guide.known_shapes if s not in games.SHAPE_EVIDENCE]}")

    term_cands = select_candidates(extract_signals(TERM_HEAVY_SPEC), guide, MAX_GAME_CANDIDATES)
    check("term-heavy lesson ranks hangman first",
          term_cands[0].game.type == "hangman",
          f"got {[c.game.type for c in term_cands]}")

    misc_cands = select_candidates(extract_signals(MISCONCEPTION_SPEC), guide, MAX_GAME_CANDIDATES)
    check("misconception lesson ranks sort-the-court first",
          misc_cands[0].game.type == "sort-the-court",
          f"got {[c.game.type for c in misc_cands]}")

    # THE containment property. With 2 games and a cap of 5, the inference cannot
    # exclude anything — so being wrong about a shape costs nothing today. This is the
    # assertion that makes the reasoned keyword rules acceptable to ship.
    check("below the cap, nothing is dropped",
          len(misc_cands) == len(guide.games),
          f"{len(misc_cands)} candidates from {len(guide.games)} games")
    check("...even for a spec with no signal at all",
          len(select_candidates(extract_signals(NO_SIGNAL_SPEC), guide, MAX_GAME_CANDIDATES))
          == len(guide.games))

# ---------------------------------------------------------------------------
# 4. Scale — the claim that the design rests on
# ---------------------------------------------------------------------------
print("4. scale: 100 games")

with tempfile.TemporaryDirectory() as tmp:
    big = synthetic_guide(Path(tmp), 100)
    big_guide = load_guide(big)
    check("100-game guide loads", len(big_guide.games) == 100)

    cands = select_candidates(extract_signals(MISCONCEPTION_SPEC), big_guide, MAX_GAME_CANDIDATES)
    check("capped at MAX_GAME_CANDIDATES", len(cands) == MAX_GAME_CANDIDATES, str(len(cands)))
    check("the top candidate matches the strongest shape",
          "judgement" in cands[0].game.content_shapes,
          f"{cands[0].game.type} has {cands[0].game.content_shapes}")

    # Deterministic order: the same spec must produce the same prompt every run, or a
    # regenerate is not reproducible and a cached prefix is wasted.
    again = select_candidates(extract_signals(MISCONCEPTION_SPEC), big_guide, MAX_GAME_CANDIDATES)
    check("selection is deterministic",
          [c.game.type for c in cands] == [c.game.type for c in again])

    # ...and deterministic in a way that survives the REGISTRY being reordered, which
    # is the case that actually happens: `GAME_TYPES` order comes from `GAME_SCHEMAS`'
    # key order, so registering a new game can shuffle equal-scoring neighbours.
    # Python's sort is stable, so re-running with the same input order proves nothing
    # about the tie-break — a version of this suite without this case stayed green with
    # `sort(key=lambda c: -c.score)` and no tie-break at all.
    shuffled_guide = load_guide(big)
    shuffled_guide.games.reverse()
    shuffled = select_candidates(
        extract_signals(MISCONCEPTION_SPEC), shuffled_guide, MAX_GAME_CANDIDATES
    )
    check("selection is invariant to registry order",
          [c.game.type for c in cands] == [c.game.type for c in shuffled],
          f"{[c.game.type for c in cands]} vs {[c.game.type for c in shuffled]}")
    # There must genuinely be ties for that assertion to mean anything: 100 games over
    # 8 shapes is ~12 games per shape, all scoring identically.
    tied = sum(1 for c in cands if c.score == cands[0].score)
    check("...and there are real ties to break", tied == MAX_GAME_CANDIDATES,
          f"only {tied} of {MAX_GAME_CANDIDATES} candidates share the top score")

    # The token bound, measured rather than asserted.
    buf = io.StringIO()
    with redirect_stdout(buf):
        big_section = build_game_prompt_section(big, MISCONCEPTION_SPEC, MAX_GAME_CANDIDATES)
        big_rules = build_game_rules_section(big)
    big_total = approx_tokens(big_section) + approx_tokens(big_rules)

    small_dir = Path(tmp) / "small"
    small = synthetic_guide(small_dir, 2)
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        small_section = build_game_prompt_section(small, MISCONCEPTION_SPEC, MAX_GAME_CANDIDATES)
        small_rules = build_game_rules_section(small)
    small_total = approx_tokens(small_section) + approx_tokens(small_rules)

    # 2 games → 2 specs injected; 100 games → 5 specs injected, plus 98 extra catalog
    # rows. So the growth is bounded by 3 specs + ~100 rows, NOT by 98 specs. Naive
    # inlining would be ~50x this.
    print(f"     2 games: ~{small_total} tokens    100 games: ~{big_total} tokens")
    check("100 games costs under 25k tokens", big_total < 25_000, f"{big_total}")
    check("growth is sublinear, not 50x",
          big_total < small_total * 4,
          f"{small_total} -> {big_total} is {big_total / max(small_total, 1):.1f}x")
    # The catalog is the only part that grows with the registry. Assert the per-game
    # marginal directly, since that is the term that scales.
    marginal = (approx_tokens(big_rules) - approx_tokens(small_rules)) / 98
    check("marginal cost per game is under 50 tokens", marginal < 50, f"{marginal:.1f}/game")

    # A withheld spec must still be nameable by the model, or the cap becomes a
    # capability bound. The catalog it reads lists all 100.
    check("the catalog still lists every game",
          all(f"game-{i:03d}" in big_rules for i in (0, 50, 99)))
    check("only the capped specs are injected",
          sum(1 for i in range(100) if f"`game-{i:03d}` — Game" in big_section)
          <= MAX_GAME_CANDIDATES)
    check("the prompt says a withheld type is still allowed",
          "any other type from the catalog" in big_section)

    # -----------------------------------------------------------------------
    # The cut itself must be inspectable. Measured on the 31 real planner specs
    # in test_curriculum/, the top score is 1.0 on 31 of 31 — `_shape_terms`
    # saturates at 4 recallable key concepts and every spec lists 6. So at 100
    # games the ≤5 injected specs are chosen by the ALPHABETICAL tie-break, not
    # by evidence, and the log has to say so: "withheld" and "withheld on a coin
    # toss" are different facts, and only the second means the ranking is no
    # longer ranking.
    # -----------------------------------------------------------------------
    all_ranked = games.rank_games(extract_signals(MISCONCEPTION_SPEC), big_guide)
    check("rank_games returns the whole registry, uncapped",
          len(all_ranked) == 100, str(len(all_ranked)))
    check("select_candidates is rank_games truncated — same order, same scores",
          [(c.game.type, c.score) for c in all_ranked[:MAX_GAME_CANDIDATES]]
          == [(c.game.type, c.score) for c in cands])

    trace = games.explain(extract_signals(MISCONCEPTION_SPEC), big_guide, cands)
    check("explain names the tie-break as arbitrary when it cuts ties",
          "arbitrary" in trace and "tied at" in trace, trace[-400:])
    check("...quantifying how many were cut, not just that some were",
          any(f"cut {n} game(s)" in trace for n in range(1, 100)), trace[-400:])
    check("...and the withheld list carries their scores, so a reader can check",
          "1.00" in trace.split("spec withheld")[1][:200] or
          "0." in trace.split("spec withheld")[1][:200],
          trace.split("spec withheld")[1][:200])

    # The inverse, or the case above passes for the wrong reason: when the dropped
    # games genuinely scored LOWER, there was no coin toss and no warning belongs.
    lower_guide = load_guide(big)
    lower_guide.games = (
        [g for g in lower_guide.games if "judgement" in g.content_shapes][:2]
        + [g for g in lower_guide.games if "judgement" not in g.content_shapes][:20]
    )
    lower_cands = select_candidates(
        extract_signals(MISCONCEPTION_SPEC), lower_guide, 2
    )
    lower_trace = games.explain(
        extract_signals(MISCONCEPTION_SPEC), lower_guide, lower_cands
    )
    check("no tie warning when the withheld games simply scored lower",
          "spec withheld" in lower_trace and "arbitrary" not in lower_trace,
          lower_trace[-300:])

# ---------------------------------------------------------------------------
# 5. Unscorable shapes must warn, not silently drop
# ---------------------------------------------------------------------------
print("5. an unknown content shape warns loudly")

with tempfile.TemporaryDirectory() as tmp:
    exotic = synthetic_guide(Path(tmp), 3, shapes=["term-recall", "sonification", "haptics"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        eguide = load_guide(exotic)
    out = buf.getvalue()
    check("warns about the unscorable shapes", "sonification" in out and "haptics" in out, out)
    check("names the fix", "SHAPE_EVIDENCE" in out, out)
    # The games are still offered — an unscorable shape must degrade to "ranks last",
    # never to "unreachable". UNKNOWN_GAME_TYPE is not fixable by editing content, but
    # a game the agent is never shown is not fixable at all.
    still = select_candidates(extract_signals(TERM_HEAVY_SPEC), eguide, MAX_GAME_CANDIDATES)
    check("unscorable games are still offered", len(still) == 3, str(len(still)))
    check("...and rank below the scorable one", still[0].game.content_shapes == ["term-recall"],
          str(still[0].game.content_shapes))

# ---------------------------------------------------------------------------
# 6. Fail-open, loudly
# ---------------------------------------------------------------------------
print("6. a missing guide fails open, loudly")

with tempfile.TemporaryDirectory() as tmp:
    missing = Path(tmp) / "nope"
    buf = io.StringIO()
    with redirect_stdout(buf):
        section = build_game_prompt_section(missing, TERM_HEAVY_SPEC, MAX_GAME_CANDIDATES)
    out = buf.getvalue()
    check("returns empty rather than raising", section == "", repr(section[:80]))
    check("says GAMES DISABLED", "GAMES DISABLED" in out, out)
    check("names the missing path", str(missing) in out, out)
    check("names how to fix it", "npm run build" in out, out)

    # load_guide itself still raises, so a caller that wants to fail closed can.
    try:
        load_guide(missing)
        check("load_guide raises for a caller that wants it", False, "no exception")
    except GuideUnavailable:
        check("load_guide raises for a caller that wants it", True)

    # An empty registry is a broken build, not "no games available".
    empty = Path(tmp) / "empty-guide"
    (empty).mkdir()
    (empty / "index.json").write_text('{"contentShapes": [], "games": []}', encoding="utf-8")
    (empty / "catalog.md").write_text("# empty\n", encoding="utf-8")
    (empty / "rules.md").write_text("# empty\n", encoding="utf-8")
    try:
        load_guide(empty)
        check("an empty registry raises", False, "no exception")
    except GuideUnavailable as exc:
        check("an empty registry raises", "declares no games" in str(exc), str(exc))

    # Malformed JSON must be reported as such, not crash with a JSONDecodeError
    # halfway through a course run.
    bad = Path(tmp) / "bad-guide"
    bad.mkdir()
    (bad / "index.json").write_text("{not json", encoding="utf-8")
    try:
        load_guide(bad)
        check("malformed index.json raises GuideUnavailable", False, "no exception")
    except GuideUnavailable:
        check("malformed index.json raises GuideUnavailable", True)

# ---------------------------------------------------------------------------
# 7. The prompt section's content
# ---------------------------------------------------------------------------
print("7. prompt section content")

if real_guide_available:
    buf = io.StringIO()
    with redirect_stdout(buf):
        section = build_game_prompt_section(GAMES_GUIDE_DIR, MISCONCEPTION_SPEC, MAX_GAME_CANDIDATES)
        rules = build_game_rules_section(GAMES_GUIDE_DIR)
    trace = buf.getvalue()

    check("section is non-empty", len(section) > 500, str(len(section)))
    check("names the chosen candidate", "sort-the-court" in section)
    check("includes the full spec, not just the tagline",
          "## JSON Schema" in section and "Payloads that are rejected" in section)
    check("permits writing no game at all", "no `<Game>` block" in section)
    check("rules section carries the catalog", "# Game catalog" in rules)
    check("rules section carries the escaping contract",
          "Do NOT use backticks here" in rules)
    check("rules section states the placement rule", "Never inside a `<Section>`" in rules)
    # The trace is printed, not returned — rule 27's corollary. Without it, "no games
    # in the course" cannot be told apart from "Stage A never offered any".
    check("the selection is traced to stdout", "GAMES:" in trace, trace[:200])
    check("the trace shows the scores", re.search(r"\d\.\d\d\s+sort-the-court", trace) is not None,
          trace[:400])

# ---------------------------------------------------------------------------
# 8. The three prompt call sites
# ---------------------------------------------------------------------------
print("8. prompt wiring (system, generation, fix)")

# `prompts/` is a package next to this file but its modules import `config` flat, the
# way agent.py's sys.path has it.
sys.path.insert(0, str(Path(__file__).resolve().parent / "prompts"))
from prompts.fix import build_fix_prompt  # noqa: E402
from prompts.generation import build_generation_prompt  # noqa: E402

if real_guide_available:
    from prompts.system import build_system_prompt  # noqa: E402

    buf = io.StringIO()
    with redirect_stdout(buf):
        sysp = build_system_prompt()
    check("system prompt carries the catalog", "| `hangman` |" in sysp)
    check("system prompt carries the cross-game rules", "UNKNOWN_GAME_TYPE" in sysp)
    check("system prompt carries the numbered structural rule",
          "12. **Interactive game**" in sysp)
    # The rule must not name a game. A rule that said "hangman" would be a second place
    # to edit per new game, which is how mlai_format_guide.md came to describe a
    # pipeline that no longer exists.
    rule12 = sysp[sysp.index("12. **Interactive game**"):sysp.index("## Your Workflow")]
    check("...and names no specific game type",
          not any(g.type in rule12 for g in load_guide(GAMES_GUIDE_DIR).games), rule12[:200])
    # The per-game specs must NOT be here: this prompt is cached and identical for every
    # lesson, so a spec in it is paid for on every lesson of every course.
    check("system prompt does NOT carry the per-game specs",
          "## JSON Schema" not in sysp)

# The generation prompt is an f-string over a template containing `{...}` JSON. A brace
# it fails to double is a KeyError at runtime, on every lesson.
gen = build_generation_prompt("spec.md", "curriculum.json", Path("/w/l.mlai"), "lesson-01-01",
                              "## CANDIDATE SPECS GO HERE")
check("generation prompt renders", "lesson-01-01" in gen)
check("...with <Game> in the structural template", "<Game type=" in gen)
check("...and the game section appended", "## CANDIDATE SPECS GO HERE" in gen)
check("...and the top-level placement rule",
      "<Game>` inside a `<Section>` is `INVALID_CHILD" in gen)
# Default must stay "" — a lesson with no candidates, or a run with no guide, has to
# cost zero here rather than emitting a header with nothing under it.
check("generation prompt defaults to no game section",
      "CANDIDATE" not in build_generation_prompt("s", "c", Path("/w/l.mlai"), "l-1"))

# The fix prompt's game guidance is gated on the errors, because it is re-sent on every
# attempt and MAX_VALIDATION_ATTEMPTS is 500 with no spend cap. Both directions matter,
# and asymmetrically: a false negative leaves the agent following KIND 2b's "add
# backticks", which is actively wrong inside a payload.
TYPES = ["hangman", "sort-the-court"]
GATE_CASES = [
    ("UNKNOWN_GAME_TYPE: Unknown game type \"crossword\"", True),
    ("INVALID_GAME_PAYLOAD: /petitions must NOT have more than 4 items", True),
    ("EMPTY_GAME_PAYLOAD", True),
    ("INVALID_GAME_JSON: Unterminated string in JSON at position 34", True),
    ("INVALID_CHILD: Invalid child element <Game> in <Section>", True),
    # No mention of a game, but reachable from a bad payload — include it anyway.
    ("error MALFORMED_XML: not well-formed (invalid token)", True),
    ("error PATHOLOGICAL_XML: validator killed by signal", True),
    ("MERMAID_PARSE_ERROR: Parse error on line 2", False),
    ("UNESCAPED_TAG_IN_TEXT: <h2>", False),
]
for errors, want in GATE_CASES:
    got = "KIND 3" in build_fix_prompt(Path("/x.mlai"), errors, 1, TYPES)
    check(f"fix gate {'includes' if want else 'omits'}: {errors[:34]}", got == want)

game_fix = build_fix_prompt(Path("/x.mlai"), "UNKNOWN_GAME_TYPE", 1, TYPES)
check("fix prompt lists the valid types", "`hangman`, `sort-the-court`" in game_fix)
# Rule 24: the retry text must name a change that can actually satisfy the error.
check("...and says a payload edit cannot fix UNKNOWN_GAME_TYPE",
      "no payload edit can fix this" in game_fix)
check("...and states the payload escaping is not the <Body> rule",
      "no backticks" in game_fix)
# No guide → no guidance, rather than "change it to one of ()".
check("no registered types → no game guidance",
      "KIND 3" not in build_fix_prompt(Path("/x.mlai"), "UNKNOWN_GAME_TYPE", 1, []))
check("...and none by default either",
      "KIND 3" not in build_fix_prompt(Path("/x.mlai"), "UNKNOWN_GAME_TYPE", 1))
# The non-game path must not have grown: this is the prompt sent on 500 attempts.
plain = build_fix_prompt(Path("/x.mlai"), "MERMAID_PARSE_ERROR", 1, TYPES)
check("non-game fix prompt stays under 1.6k tokens", approx_tokens(plain) < 1600,
      str(approx_tokens(plain)))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
