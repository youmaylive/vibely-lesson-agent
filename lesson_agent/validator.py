"""
External MLAI validator.

Runs the vibely-v2-parser CLI via subprocess and parses results.
This is the mechanically enforced validation — the agent cannot skip it.

Two independent layers run on every file:

1. the MLAI validator CLI (XML structure + component schemas), and
2. the Mermaid gate (``scripts/mermaid-check.mjs``), which runs the real
   ``mermaid.parse()`` plus an entity check.

Layer 2 exists because layer 1 never parses Mermaid — the schema for
``<Mermaid>`` is only "text must be non-empty". Without it, a diagram that
cannot render passes validation and fails in the student's browser instead.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import MERMAID_CHECK_CLI, VALIDATOR_CLI


@dataclass
class ValidationResult:
    """Result of running the MLAI validator."""

    success: bool
    """True if zero errors were found."""

    raw_output: str
    """Full stdout + stderr from the validator CLI."""

    error_count: int
    """Number of errors detected."""

    mermaid_gate_ran: bool = True
    """False if the Mermaid gate could not run (missing deps, crash, timeout).

    A False here does NOT fail the lesson — an infra problem should not halt the
    whole pipeline — but it does mean the diagrams in this file were never
    checked, which the caller reports so it never passes silently.
    """


# Exit codes of scripts/mermaid-check.mjs
_MERMAID_OK = 0
_MERMAID_FINDINGS = 1
_MERMAID_UNAVAILABLE = 2


def _run_mermaid_check(file_path: Path) -> tuple[str, int, bool]:
    """Run the Mermaid gate.

    Returns
    -------
    (output, error_count, gate_ran)
        ``output`` is empty when there is nothing to report. ``gate_ran`` is
        False when the checker itself failed, in which case ``error_count`` is 0
        — an unavailable gate must not be reported to the agent as a content
        error it can fix.
    """
    if not MERMAID_CHECK_CLI.exists():
        return (
            f"MERMAID GATE UNAVAILABLE: checker not found at {MERMAID_CHECK_CLI}",
            0,
            False,
        )

    try:
        result = subprocess.run(
            ["node", str(MERMAID_CHECK_CLI), str(file_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return ("MERMAID GATE UNAVAILABLE: checker timed out after 120s", 0, False)
    except FileNotFoundError:
        return ("MERMAID GATE UNAVAILABLE: 'node' not found on PATH", 0, False)
    except Exception as exc:  # noqa: BLE001 - never let the gate crash a run
        return (f"MERMAID GATE UNAVAILABLE: {exc}", 0, False)

    if result.returncode == _MERMAID_OK:
        return ("", 0, True)

    combined = result.stdout
    if result.stderr:
        combined += "\n" + result.stderr
    combined = combined.strip()

    if result.returncode == _MERMAID_FINDINGS:
        # Count only the finding headers — the indented "    | ..." context lines
        # that follow a parse error also contain the word "error".
        count = sum(
            1 for line in combined.splitlines() if line.startswith("error MERMAID_")
        )
        return (combined, max(count, 1), True)

    # Exit 2, or anything unexpected: the checker itself failed.
    detail = combined or f"exit code {result.returncode}"
    return (f"MERMAID GATE UNAVAILABLE: {detail}", 0, False)


def validate_mlai_file(file_path: Path) -> ValidationResult:
    """Run the MLAI validator CLI and the Mermaid gate against a file.

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

        xml_ok = result.returncode == 0
        xml_error_count = 0 if xml_ok else max(len(error_lines), 1)

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

    # Run the Mermaid gate regardless of the XML result, so the agent gets every
    # problem in one fix prompt instead of discovering diagrams after structure.
    mermaid_output, mermaid_error_count, mermaid_gate_ran = _run_mermaid_check(file_path)

    if mermaid_output:
        combined_output = (combined_output.strip() + "\n\n" + mermaid_output).strip()

    return ValidationResult(
        success=xml_ok and mermaid_error_count == 0,
        raw_output=combined_output.strip(),
        error_count=xml_error_count + mermaid_error_count,
        mermaid_gate_ran=mermaid_gate_ran,
    )
