"""
Shared configuration: paths and constants.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR_CLI = (
    Path.home()
    / "Documents"
    / "CODING"
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