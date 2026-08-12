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

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
# Bedrock inference-profile model ID (Claude via Amazon Bedrock)
DEFAULT_MODEL = "global.anthropic.claude-sonnet-5"
DEFAULT_MAX_TURNS = 30
MAX_VALIDATION_ATTEMPTS = 500