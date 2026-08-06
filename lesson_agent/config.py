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
# Bedrock inference-profile model ID (Claude via Amazon Bedrock)
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_MAX_TURNS = 30
MAX_VALIDATION_ATTEMPTS = 500