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

import re
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


# Validator subprocess limits. The timeout was 30s, and 4 lessons of a 50-lesson
# course hit it — a lesson that is merely slow to validate was reported to the agent
# as broken. 240s is well past the slowest observed clean parse while still bounding
# a genuinely pathological file. The heap cap exists because one lesson OOMs the
# validator outright; see the call site.
_VALIDATOR_TIMEOUT_S = 240
_HEAP_MB = 4096

# Both a timeout and a heap crash have the same underlying cause and the same fix,
# so they share one message. It must name something the agent can edit — a bare
# "timed out" is unactionable and burns fix attempts on nothing.
_PATHOLOGICAL_XML_HINT = (
    "error PATHOLOGICAL_XML: the validator {what} on this file.\n"
    "This is almost always unclosed inline tags in *text content* — prose that "
    "mentions HTML like <br>, <td>, <div> or <strong> without escaping it. Backticks "
    "alone do not help in <Prompt>/<Option>/<Front>/<Back>/<Item>, which are ordinary "
    "elements: `<td>` there opens a real <td> that is never closed, and the parser's "
    "error recovery then blows up.\n"
    "Fix: write the tag with backticks AND entities — `&lt;td&gt;` / `&lt;br&gt;` — "
    "which is correct in every element. Check every span that mentions a tag. (A `<` "
    "that is not tag-shaped, like `a < b`, needs the entity only.)"
)

# The CLI colours its output, so strip SGR sequences before matching on it.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ERROR_TOTAL_RE = re.compile(r"(\d+)\s+error\(s\)")

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


def _count_errors(output: str) -> int:
    """Count validator errors, preferring the CLI's own declared total.

    The CLI prints a ``66 error(s)`` summary line and then one ``✗ Line N  CODE:``
    line per error. The previous heuristic here counted lines *containing the word
    "error"* — which the per-error lines do not, since the word only appears in the
    summary. So a 66-error lesson was reported to the agent (and to the log) as
    ``1 error(s)``, hiding the scale of a failure and making the fix loop look
    closer to done than it was. Read the CLI's number; fall back to counting the
    ``✗ Line`` markers, then to 1 — never 0, because the caller only gets here on a
    non-zero exit and a count of 0 would read as success.
    """
    stripped = _ANSI_RE.sub("", output)
    match = _ERROR_TOTAL_RE.search(stripped)
    if match:
        return max(int(match.group(1)), 1)
    marked = sum(1 for line in stripped.splitlines() if line.lstrip().startswith("✗ Line"))
    return max(marked, 1)


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
            # --max-old-space-size: measured, module_02/lesson_04 of the html-css-basic
            # course exhausts the default heap and the process dies on SIGABRT. Node's
            # default cap is a fraction of host RAM, and the Fargate task has plenty —
            # so raise it explicitly rather than inheriting whatever the box decides.
            ["node", f"--max-old-space-size={_HEAP_MB}", str(VALIDATOR_CLI), str(file_path)],
            capture_output=True,
            text=True,
            timeout=_VALIDATOR_TIMEOUT_S,
        )

        combined_output = result.stdout
        if result.stderr:
            combined_output += "\n" + result.stderr

        # The validator CLI exits with 0 on success, non-zero on errors.
        xml_ok = result.returncode == 0
        xml_error_count = 0 if xml_ok else _count_errors(combined_output)

        # A negative return code is a signal, not a validator verdict: the process
        # was killed (SIGABRT on heap exhaustion, SIGKILL by the OOM killer) and
        # printed a V8 stack trace instead of findings. The raw trace tells the
        # agent nothing it can edit, so name the cause the same way a timeout does.
        if result.returncode < 0:
            combined_output = _PATHOLOGICAL_XML_HINT.format(
                what=f"crashed (signal {-result.returncode}, heap limit {_HEAP_MB} MB)"
            )
            xml_error_count = 1

    except subprocess.TimeoutExpired:
        # Not an infra problem, and not unfixable: in every observed case the cause
        # was pathological XML — unclosed inline tags (`<br>`, `<td>`, `<strong>` in
        # prose) make the parser's recovery branch blow up combinatorially. Saying
        # only "timed out" gives the fix loop nothing to act on (rule 24: the retry
        # message must be fixable by the thing it names), so state the likely cause.
        return ValidationResult(
            success=False,
            raw_output=_PATHOLOGICAL_XML_HINT.format(
                what=f"timed out after {_VALIDATOR_TIMEOUT_S}s"
            ),
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
