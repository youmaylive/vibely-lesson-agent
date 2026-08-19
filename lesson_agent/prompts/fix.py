"""
User prompt for fixing validation errors.

Sent to the agent when the external validator detects errors in the
generated MLAI file.
"""

from collections.abc import Sequence
from pathlib import Path


def _game_kind(game_types: Sequence[str] | None, validation_errors: str) -> str:
    """The `GAME_*` repair guidance, or `""` when games are not in play.

    Each code gets its **own** fix text, because they are not variations of one
    problem and the wrong pairing is worse than silence: `UNKNOWN_GAME_TYPE` cannot
    be fixed by editing the payload at all, so telling the agent to "fix the payload"
    guarantees a loop that cannot terminate. That is the trap AGENTS.md rule 24
    records — a `MISSING_TEXT_ANCHOR` finding whose feedback said "reposition these so
    nothing overlaps", which no amount of repositioning fixes.

    The per-type field rules are deliberately NOT re-injected here. The spec was in
    the generation prompt and this file is edited in a resumed session, so the agent
    already has it; re-sending ~2.2k tokens on every one of up to
    `MAX_VALIDATION_ATTEMPTS` attempts is the cost rule 32 measured (an 805-char
    suggestion × 17 findings was ~4.2k tokens per attempt). The valid `type` list is
    the one exception — it is ~20 tokens and it is what `UNKNOWN_GAME_TYPE` needs.

    Included only when the errors could involve a game (~440 tokens otherwise wasted on
    every attempt, and `MAX_VALIDATION_ATTEMPTS` is 500 with no spend cap). The test is
    deliberately generous, because the two failure directions are not symmetric: an
    unnecessary 440 tokens costs pennies, while omitting this when a game *is* broken
    leaves the agent with KIND 2b's advice — "add backticks" — which is actively wrong
    inside a payload. So `MALFORMED_XML` and `PATHOLOGICAL_XML` count too: an unescaped
    `<` inside a payload produces them without ever naming `<Game>`.
    """
    if not game_types:
        return ""
    haystack = validation_errors.upper()
    if not any(k in haystack for k in ("GAME", "MALFORMED_XML", "PATHOLOGICAL_XML")):
        return ""
    types = ", ".join(f"`{t}`" for t in game_types)
    return f"""
---

**KIND 3 — `GAME_*` codes and `<Game>`: the payload, not the prose.** Each of these has a
different fix, and only one of them is fixed by editing the JSON:

- `UNKNOWN_GAME_TYPE` — **no payload edit can fix this.** The `type` attribute is not a
  registered game. There are exactly two fixes: change the `type` to one of the registered
  ones ({types}), or delete the `<Game>` block. Do not invent a type, and do not touch the
  payload — it is not what failed.
- `EMPTY_GAME_PAYLOAD` — the element has no text. Write the JSON payload, or delete the block.
- `INVALID_GAME_JSON` — the text is not parseable JSON. Usually a trailing comma, single
  quotes instead of double, or prose left inside the element. `Unterminated string` here
  normally means an unescaped `<` opened a real element mid-payload — see the escaping note
  below, and fix that rather than the quoting.
- `INVALID_GAME_PAYLOAD` — parseable JSON that breaks the type's schema. The message names the
  offending path. Every schema is closed, so an **extra** field is an error, not extra credit;
  check the field list in the spec you were given and write exactly those fields.
- `INVALID_CHILD: Invalid child element <Game> in <Section>` — the block is in the wrong place.
  **Move it out to the lesson's top level** (a direct child of `<Lesson>`, near the end). Do not
  rename it and do not delete it.

**Escaping inside a `<Game>` payload is NOT the KIND 2b rule.** Write `&lt;` `&gt;` `&amp;` and
**no backticks** — the payload is rendered as plain text, not Markdown, so a backtick reaches the
student as a literal backtick. A bare `<p>` in the payload produces `INVALID_CHILD` *and*
`INVALID_GAME_JSON` together; a bare `3 < 5` makes the whole file `MALFORMED_XML`.
"""


def build_fix_prompt(
    output_file: Path,
    validation_errors: str,
    attempt: int,
    game_types: Sequence[str] | None = None,
) -> str:
    """Build a prompt that gives the agent validation errors to fix.

    Parameters
    ----------
    output_file:
        Path to the .mlai file that failed validation.
    validation_errors:
        Raw output from the validator CLI (error messages).
    attempt:
        Current fix attempt number (1-indexed).
    game_types:
        The registered game types, for the `UNKNOWN_GAME_TYPE` fix. `None` or empty
        omits the game guidance entirely — a run with no game guide must not be told
        to pick "one of ()".
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
  - **An unquoted `(` `)` `[` `]` `{{` `}}` `|` in a label** (`got 'PS'`, `got 'PIPE'`, `got 'SQE'`), or an
    **`@` touching a non-space character** (`got 'LINK_ID'` — mermaid reads `a@b.com` as node syntax).
    Quote the label and all of them become safe: `A[f(x)]` → `A["f(x)"]`,
    `E[|Δt| &gt; 40ms]` → `E["|Δt| &gt; 40ms"]`, `H[a@b.com]` → `H["a@b.com"]`
  - **A `;` in a `sequenceDiagram` message** (`got 'NEWLINE'`, expecting an arrow). `;` separates
    statements. Quoting does NOT help here — replace it with a comma, or write `#59;`.
  - **A `timeline` period label containing a colon** (`Expecting ... 'section', got 'INVALID'`).
    `timeline` uses `:` to separate period from events, so `06:00 : Baseline` breaks. Rename the
    period so it has no colon — `0600 hrs : Baseline`, `Hour 0 : Baseline`. Quoting it does NOT
    help, and adding a `section` does NOT help.
  - When in doubt, **double-quote every node and edge label** — that alone fixes most of these.
- `MERMAID_NUMERIC_ENTITY` / `MERMAID_BAD_ENTITY` — the diagram parses but renders as visible
  garbage, because nothing decodes these entities and the renderer adds a stray `&`:
  - `&#10;` / `&#13;` (intended as a line break) → `&lt;br/&gt;`
  - `&#40;` `&#41;` `&#58;` → write the literal `(` `)` `:` **and wrap that label in double quotes**,
    or the decoded character becomes a hard parse error instead.
  - `&nbsp;` → a normal space. `&uarr;` / `&divide;` → the literal `↑` / `÷` character (these resolve
    in a flowchart but appear literally in `timeline`/`pie` and vanish in `stateDiagram`).
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

**KIND 2b — a tag named in ordinary prose, which is the most common cause of a long error list.**
`<Body>`, `<H1>`/`<H2>`/`<H3>`, `<Prompt>`, `<Option>`, `<Front>`/`<Back>`, `<Item>` are all parsed
as XML *and then* rendered as Markdown. **The one fix that is correct in every one of them:
`` `&lt;td&gt;` `` — backticks AND the entity.** Each half alone fails, and the two failures look
nothing alike:

- **`INVALID_CHILD` / `UNKNOWN_ELEMENT`** means the entity is missing. `` `<td>` `` in an `<Option>`
  opens a real `<td>` that never closes; `</Option>` then closes the wrong element and every error
  after that point is a *symptom*, not a separate bug. A long run of these starting partway down the
  file is almost always ONE unescaped tag above the first reported line — find it, escape it,
  re-validate, and do not restructure the sections. (Inside `<Body>`/`<Code>`/`<Mermaid>` the content
  is captured whole so this does not fire, which is exactly why the habit does not survive being
  moved into a quiz option.)
- **`UNESCAPED_TAG_IN_TEXT`** means the backticks are missing. `&lt;td&gt;` parses fine, but the
  parser decodes it, so the renderer receives a bare `<td>` and **injects it into the page** — the
  student sees nothing where the tag should be. Adding more escaping cannot fix this one; wrap it in
  backticks. The error names each tag it found.
- Fix by escaping and backticking, never by deleting the explanation or renaming the tag being
  taught. The student still reads `<td>`, styled as inline code.
- Watch for self-closing tags (`` `<br>` ``, `` `<img>` ``, `` `<hr>` ``) — they never close, so they
  cascade the furthest — and for a stray closing tag like `</g>` left over from an SVG.
- `error PATHOLOGICAL_XML` (the validator timed out or crashed) is the missing-entity defect at
  scale: several unclosed inline tags in prose.
- A `<` that is *not* tag-shaped (`width < 600px`, `a < b`) is the opposite mix: `MALFORMED_XML`,
  fixed by `&lt;` alone. Backticks there are only for code styling.
{_game_kind(game_types, validation_errors)}
Fix every error of all kinds in one pass, then confirm that you are done."""