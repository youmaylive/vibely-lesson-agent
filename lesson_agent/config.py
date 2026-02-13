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
MLAI_FORMAT_GUIDE = Path(__file__).resolve().parent / "prompts" / "mlai_format_guide.md"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "claude-opus-4-5"
DEFAULT_MAX_TURNS = 30
MAX_VALIDATION_ATTEMPTS = 500