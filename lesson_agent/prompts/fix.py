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

**First, sort the errors into two kinds — they need opposite fixes.**

---

**KIND 1 — `MERMAID_*` codes: the diagram is not valid Mermaid.** These come from running the real
Mermaid parser, the same one in the student's browser. The XML is fine; the *diagram syntax* is wrong.
Do NOT add XML escaping to fix these.

- `MERMAID_PARSE_ERROR` — the diagram will not render at all. The quoted message includes Mermaid's
  own `Parse error on line N` and a `^` marker. Almost always one of:
  - **A bare `"` inside a label** (`got 'STR'`). Wrap the whole label in quotes and write the inner
    quotes as `#quot;` — note there is **no leading ampersand**:
    `E{{Parameter blank or "not done"?}}` → `E{{"Parameter blank or #quot;not done#quot;?"}}`
  - **Unquoted `(` or `)` in a label** (`got 'PS'`). Quote the label: `A[f(x)]` → `A["f(x)"]`
  - **A `timeline` with no `section`**, or `HH:MM` labels whose `:` collides with the separator
    (`Expecting ... 'section'`). Add `section <name>` before the entries and rename `06:00` to
    `Morning` / `Day 1` etc.
  - When in doubt, **double-quote every node and edge label** — that alone fixes most of these.
- `MERMAID_NUMERIC_ENTITY` / `MERMAID_BAD_ENTITY` — the diagram parses but renders as visible
  garbage, because nothing decodes these entities and the renderer adds a stray `&`:
  - `&#10;` / `&#13;` (intended as a line break) → `&lt;br/&gt;`
  - `&#40;` `&#41;` `&#58;` → write the literal `(` `)` `:` **and wrap that label in double quotes**,
    or the decoded character becomes a hard parse error instead.
  - `&nbsp;` → a normal space. `&rarr;` / `&divide;` → the literal `→` / `÷` character.
  - **Never** repair these by writing `&amp;#40;` — that guarantees a visible `&#40;` on screen.
  - Do not delete the label content to make the error go away.

---

**KIND 2 — everything else is usually unescaped XML, not a structural problem.** Before restructuring
anything, check for this — `<Mermaid>` and `<Code>` are parsed as XML, so `<`, `>` and `&` must be
escaped:
- `INVALID_CHILD: Invalid child element <br> in <Mermaid>` or `UNKNOWN_ELEMENT: <br>` means you
  wrote a raw `<br/>` in a node label. Replace it with `&lt;br/&gt;` — do NOT delete the line break
  and do NOT restructure the diagram. Ignore any "Did you mean: ...?" suggestion here; the element
  name is not the problem, the escaping is.
- An unescaped `<` or `&` (comparison operators, LaTeX, `D&C`, `&nbsp;`) can also cascade into
  *bogus* structural errors like `INVALID_CHILD` on elements that are actually fine. Fix the
  escaping first, then re-check whether the structural errors were real.
- `&nbsp;` is not a valid entity — use a normal space.

Fix every error of both kinds in one pass, then confirm that you are done."""