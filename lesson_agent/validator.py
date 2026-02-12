"""
External MLAI validator.

Runs the vibely-v2-parser CLI via subprocess and parses results.
This is the mechanically enforced validation — the agent cannot skip it.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import VALIDATOR_CLI


@dataclass
class ValidationResult:
    """Result of running the MLAI validator."""

    success: bool
    """True if zero errors were found."""

    raw_output: str
    """Full stdout + stderr from the validator CLI."""

    error_count: int
    """Number of errors detected."""


def validate_mlai_file(file_path: Path) -> ValidationResult:
    """Run the MLAI validator CLI against a file.

    Parameters
    ----------
    file_path:
        Path to the .mlai file to validate.

    Returns
    -------
    ValidationResult with success flag, raw output, and error count.
    """
    if not VALIDATOR_CLI.exists():
        return ValidationResult(
            success=False,
            raw_output=f"Validator CLI not found at {VALIDATOR_CLI}. "
            "Build it with: cd vibely-v2/vibely-v2-parser && npm run build",
            error_count=1,
        )

    if not file_path.exists():
        return ValidationResult(
            success=False,
            raw_output=f"File not found: {file_path}",
            error_count=1,
        )

    try:
        result = subprocess.run(
            ["node", str(VALIDATOR_CLI), str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        combined_output = result.stdout
        if result.stderr:
            combined_output += "\n" + result.stderr

        # The validator CLI exits with 0 on success, non-zero on errors.
        # Count error lines for reporting (lines containing "error" or "Error").
        error_lines = [
            line
            for line in combined_output.splitlines()
            if "error" in line.lower() and not line.strip().startswith("#")
        ]

        is_success = result.returncode == 0
        return ValidationResult(
            success=is_success,
            raw_output=combined_output.strip(),
            error_count=0 if is_success else max(len(error_lines), 1),
        )

    except subprocess.TimeoutExpired:
        return ValidationResult(
            success=False,
            raw_output="Validator timed out after 30 seconds.",
            error_count=1,
        )
    except FileNotFoundError:
        return ValidationResult(
            success=False,
            raw_output="Node.js not found. Ensure 'node' is on your PATH.",
            error_count=1,
        )
    except Exception as exc:
        return ValidationResult(
            success=False,
            raw_output=f"Unexpected error running validator: {exc}",
            error_count=1,
        )