"""
User prompt for fixing validation errors.

Sent to the agent when the external validator detects errors in the
generated MLAI file.
"""

from pathlib import Path


def build_fix_prompt(output_file: Path, validation_errors: str, attempt: int) -> str:
    """Build a prompt that gives the agent validation errors to fix.

    Parameters
    ----------
    output_file:
        Path to the .mlai file that failed validation.
    validation_errors:
        Raw output from the validator CLI (error messages).
    attempt:
        Current fix attempt number (1-indexed).
    """
    return f"""The MLAI file you generated failed validation (attempt {attempt}).

**File**: {output_file}

**Validation errors**:
```
{validation_errors}
```

Read the error messages carefully, then edit the file to fix every error.
After making your fixes, confirm that you are done."""