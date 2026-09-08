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

# The course-cover brief, in two halves loaded from disk like the specs above.
#
# THUMBNAIL_SKILL is a VERBATIM vendored third-party skill — `youtube-thumbnail-design`
# from github.com/qu-skills/skills, installed with `npx skills add`. Do not edit it;
# see PROVENANCE.md beside it for the commit, the digest and the re-install line. It
# targets YouTube and about half of it is unusable here (5 of its 12 sections, 52% of
# their characters — measured, not estimated) — it drives an `inference.sh`
# CLI (`belt app run`) we do not have, and its Face Expression Psychology section is
# tuned for reaction-video CTR — so `thumbnail_agent.load_skill()` whitelists the design
# sections by heading and strips every fenced block before the text reaches a prompt.
# Each drop has its recorded reason in `_SKILL_DROP`. That loader RAISES if a
# whitelisted heading is missing, so an upstream rename fails loudly instead of
# shipping a brief with the colour rules silently absent (rule 26).
#
# THUMBNAIL_SPEC is ours: only the deltas the skill cannot know — that the cover is
# painted by an image model through OpenRouter (`openrouter.py`), the two rules that
# invert for a course (the title IS the payload, and it is read back off the pixels by a
# vision model), the palette table, and the exact values `thumbnail_agent` enforces.
# Split in two so re-installing upstream is a copy, not a merge.
#
# Both halves reach the model through `thumbnail_agent._DESIGN`, which is built at
# IMPORT time — so a spec file that has been moved or made unreadable breaks the module
# rather than degrading the brief. This comment said "we author SVG rather than diffuse
# pixels" until the pivot; the premise it rested on (that diffusion cannot spell a
# title) was measured false on five models, and the spec's own retired-rules table is
# the record of what that cost.
THUMBNAIL_SKILL = (
    Path(__file__).resolve().parent
    / "prompts"
    / "skills"
    / "youtube-thumbnail-design"
    / "SKILL.md"
)
THUMBNAIL_SPEC = Path(__file__).resolve().parent / "prompts" / "course_thumbnail_spec.md"

# Two more VERBATIM vendored skills, from github.com/zlh-428/naruto-skills (Apache 2.0),
# installed with `npx skillfish add ... -y --project`. Same rule as THUMBNAIL_SKILL: do
# not edit them; PROVENANCE.md beside each records the commit, the tree hash, the
# re-install line and — the part worth reading before touching this — what is
# deliberately NOT used from each.
#
# These are roots, not files, because unlike `youtube-thumbnail-design` the useful part
# is not one document: it is a GALLERY. `cover-image` supplies 20 visual styles and
# `infographic` 20 information layouts, one small reference file each, and only the two
# the model actually picks are ever loaded. The one-line gallery tables go in the cached
# system half; `thumbnail_agent.load_style()` / `load_layout()` read a single file per
# cover (~700 B and ~900 B). Loading all 40 would cost ~35k tokens to use one of them —
# the same bound `mlai-games`' registry hit, resolved the same way.
#
# Only ONE gallery owns each dimension: styles from `cover-image`, layouts from
# `infographic`. Both skills ship a style gallery and they do NOT agree — `chalkboard.md`
# is byte-identical across the two while `pixel-art.md` differs — so `infographic`'s 17
# styles are declined wholesale rather than merged (rule 23: two implementations of one
# list is the divergence, however similar they look on the day).
THUMBNAIL_STYLES = (
    Path(__file__).resolve().parent / "prompts" / "skills" / "cover-image"
)
THUMBNAIL_LAYOUTS = (
    Path(__file__).resolve().parent / "prompts" / "skills" / "infographic"
)

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