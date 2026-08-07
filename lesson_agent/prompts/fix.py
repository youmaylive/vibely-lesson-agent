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

**Most of these errors are unescaped XML, not structural problems.** Before restructuring anything,
check for this — `<Mermaid>` and `<Code>` are parsed as XML, so `<`, `>` and `&` must be escaped:
- `INVALID_CHILD: Invalid child element <br> in <Mermaid>` or `UNKNOWN_ELEMENT: <br>` means you
  wrote a raw `<br/>` in a node label. Replace it with `&lt;br/&gt;` — do NOT delete the line break
  and do NOT restructure the diagram. Ignore any "Did you mean: ...?" suggestion here; the element
  name is not the problem, the escaping is.
- An unescaped `<` or `&` (comparison operators, LaTeX, `D&C`, `&nbsp;`) can also cascade into
  *bogus* structural errors like `INVALID_CHILD` on elements that are actually fine. Fix the
  escaping first, then re-check whether the structural errors were real.
- `&nbsp;` is not a valid entity — use a normal space.

After making your fixes, confirm that you are done."""