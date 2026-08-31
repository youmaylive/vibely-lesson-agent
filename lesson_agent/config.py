"""
Shared configuration: paths and constants.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# memebu-course-engine root (parent of vibely-lesson-agent/)
COURSE_ENGINE_ROOT = PROJECT_ROOT.parent
VALIDATOR_CLI = (
    COURSE_ENGINE_ROOT
    / "vibely-v2"
    / "vibely-v2-parser"
    / "dist"
    / "cli.js"
)
# Second validation layer: runs the real mermaid.parse() (the same one the
# student's browser runs) plus an entity check. The MLAI validator above never
# parses Mermaid — its schema for <Mermaid> is only "text must be non-empty" —
# so without this a broken diagram passes validation and fails in the viewer.
# Source .mjs, not dist/: the worker image never runs `npm run build`.
MERMAID_CHECK_CLI = (
    COURSE_ENGINE_ROOT
    / "vibely-v2"
    / "vibely-v2-parser"
    / "scripts"
    / "mermaid-check.mjs"
)
MLAI_FORMAT_GUIDE = Path(__file__).resolve().parent / "prompts" / "mlai_format_guide.md"

# The SVG design framework the generator must follow. Every rule in it that can be
# measured is measured by `svg_geometry.py`, and every Finding cites the rule ID it
# breaks — see the module docstring there. Loaded from disk (like the MLAI guide
# above) so the spec can be revised without touching prompt code.
SVG_DESIGN_SPEC = Path(__file__).resolve().parent / "prompts" / "svg_design_spec.md"

# The interactive-game guide, GENERATED from `mlai-games`' schema registry by
# `mlai-games/scripts/emit-agent-guide.mjs` (`npm run build`). Read from where it is
# built rather than copied into this repo — a copy is what `mlai_format_guide.md`
# became: a hand-saved snapshot of `component-registry.ts`'s output, now 509 lines
# that mention neither `<Svg>` nor `<Game>`.
#
# Resolved across repos exactly like VALIDATOR_CLI above, and like it, `dist/` is
# gitignored and built locally before the worker image COPYs it (the image never runs
# `npm run build`). `emit-agent-guide.mjs --check` is what stops a stale one shipping.
GAMES_GUIDE_DIR = (
    COURSE_ENGINE_ROOT
    / "vibely-v2"
    / "mlai-games"
    / "dist"
    / "agent-guide"
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
# Bedrock inference-profile model ID (Claude via Amazon Bedrock)
DEFAULT_MODEL = "global.anthropic.claude-sonnet-5"
DEFAULT_MAX_TURNS = 30
MAX_VALIDATION_ATTEMPTS = 500

# How many per-game specs may be injected into one generation prompt. This is a
# COST bound, not a capability bound: the catalog in the system prompt always lists
# every registered game, so the agent can choose a type whose spec was withheld.
#
# Measured on the 2-game registry: catalog 182 + rules 782 tokens always-on, ~2.2k
# per spec. At 100 games this projects to ~15k tokens and stays flat, against ~220k
# for inlining every spec.
MAX_GAME_CANDIDATES = 5

# ---------------------------------------------------------------------------
# Lesson shape budget
# ---------------------------------------------------------------------------
# The minimum number of <Svg> blocks a lesson must carry. This is a FLOOR, not the
# target: the target (3-4) has been in the generation prompt since the SVG framework
# landed and has NEVER been met. Measured over the 5 lessons this pipeline has written,
# with a case-SENSITIVE count: median 2, min 1, max 4 — so 4 of 5 are under target and
# one shipped with a single diagram. (A case-insensitive count says 4/2/8 because it
# counts the `<Svg>` wrapper AND the `<svg>` inside it — exactly double, every time.
# Rule 25 applies to one's own measurements too.)
#
# So this floor closes a live gap, not a hypothetical drift — rule 26: a rule stated in
# a prompt and enforced by nothing is a regression no test catches.
#
# Enforced OUTSIDE the MAX_VALIDATION_ATTEMPTS loop, by one bounded top-up pass in
# `agent.py`, and it fails open loudly — see `lesson_shape.py`.
SVG_FLOOR = 3

# One playable game in every lesson — the same shape of gap as SVG_FLOOR, one level up.
# Measured cause: nothing has ever counted games PER LESSON. The only game check is the
# course-level census (`GAME_FLOOR_RATE`, `workers/phases/curriculum.py`), and at its
# 0.30 default 70% of lessons may legitimately carry none. Meanwhile three prompt copies
# told the model "if no catalogued type fits, write no `<Game>` block at all" — a hatch
# that is never legitimately true: every one of the 31 real planner specs in
# `test_curriculum/` scores a genuine fit for at least one registered game.
#
# 1, not 2: `maxPerLesson: 1` is the registry's own statement (`hangman.ts`,
# `sort-the-court.ts`), so the floor and the ceiling meet at exactly one game.
GAME_FLOOR = 1

# Env-overridable so retuning needs no image rebuild, on the GAME_FLOOR_RATE
# precedent. `budget.py` reads these; unset or unparseable falls back to the value
# here, loudly.
SVG_FLOOR_ENV = "SVG_FLOOR"
GAME_FLOOR_ENV = "GAME_FLOOR"
LESSON_BUDGET_BAND_ENV = "LESSON_BUDGET_BAND"