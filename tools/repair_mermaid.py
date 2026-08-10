#!/usr/bin/env python3
"""
Repair Mermaid defects in already-generated .mlai files.

Lessons produced before the Mermaid gate existed (see
vibely-v2-parser/scripts/mermaid-check.mjs) contain three mechanical defects:

1. numeric entities (&#10; &#40; &#41; &#58; ...) — nothing decodes them, so the
   renderer emits a stray ampersand and the student reads `f&(x&)`. Replaced with
   the literal character, and the containing label gets quoted so the decoded
   character does not become a *parse* error (decoding `&#40;` inside an unquoted
   label converts a cosmetic bug into a diagram that will not render at all).
   `&quot;` is normalised the same way: both decode stages turn it into a bare `"`.
2. bare `"` inside a label — a hard parse error. Rewritten to `#quot;`.
3. `timeline` period labels containing a colon (`06:00 : Baseline`) — the colon
   collides with the period/event separator. Renamed to `0600 hrs`. Quoting does
   not help, and a `section` is optional, so neither is a fix.
4. unquoted flowchart labels containing `( ) [ ] { } |`, or an `@` against a
   non-space character (`alice@example.com` — mermaid 11 reads that as the
   `A@{...}` node-metadata syntax). Quoting is a complete fix for all of these.
5. `;` inside a sequenceDiagram message — it is a statement separator, so the
   message truncates. Rewritten to `#59;`; quoting does NOT help here.

This script is a best-effort repair, not a guarantee: `mermaid-check.mjs` is the
gate. Always run it afterwards.

Operates on raw text with byte-level regexes and never round-trips the XML: an
XML parser decodes `&#10;` to a real newline on read, so a parse/serialise cycle
would silently rewrite content we are trying to preserve exactly.

Usage:
    python tools/repair_mermaid.py <dir-or-file>...        # report only
    python tools/repair_mermaid.py --write <dir-or-file>...  # rewrite in place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MERMAID_BLOCK = re.compile(r"(<Mermaid(?:\s[^>]*)?>)((?:(?!<Mermaid[\s>])[\s\S])*?)(</Mermaid>)")

# Numeric entities fast-xml-parser already decodes; leaving them alone keeps the
# diff minimal and they are harmless. Mirrors DECODED_NUMERIC in mermaid-check.mjs.
ALREADY_DECODED = {
    "&#39;", "&#x27;", "&#62;", "&#x3e;", "&#60;", "&#x3c;",
    "&#34;", "&#x22;", "&#38;", "&#x26;",
}

NUMERIC_ENTITY = re.compile(r"&#x?[0-9a-fA-F]+;")

# Line-break intent: these become <br/>, escaped for the XML layer.
LINEBREAK_CODEPOINTS = {10, 13}

# Label shapes, one pattern per delimiter pair, tried in this order (longest
# delimiter first so `{{` wins over `{`). Each body deliberately ALLOWS parentheses
# — a label containing a bare `(` is precisely the case that needs quoting — and
# excludes its own delimiters and newlines so a match cannot span two labels.
#
# Round shapes (`A(text)`) are intentionally absent: there the paren is both the
# delimiter and the payload, so an automated rewrite is ambiguous. The gate still
# catches those, which is the point — nothing broken passes silently.
LABEL_SHAPES = (
    re.compile(r"(?P<open>\[)(?P<body>[^\[\]\n]*)(?P<close>\])"),
    re.compile(r"(?P<open>\{\{)(?P<body>[^{}\n]*)(?P<close>\}\})"),
    re.compile(r"(?P<open>\{)(?P<body>[^{}\n]*)(?P<close>\})"),
    re.compile(r"(?P<open>\|)(?P<body>[^|\n]*)(?P<close>\|)"),
)


def _sub_labels(block: str, repl) -> str:
    """Apply `repl` to every label body, across every shape."""
    for pattern in LABEL_SHAPES:
        block = pattern.sub(repl, block)
    return block


def _entity_char(ent: str) -> str | None:
    """Decode a numeric entity to its character, or None if we should skip it."""
    if ent.lower() in ALREADY_DECODED:
        return None
    body = ent[2:-1]
    try:
        cp = int(body[1:], 16) if body[:1].lower() == "x" else int(body)
    except ValueError:
        return None
    if cp in LINEBREAK_CODEPOINTS:
        return "&lt;br/&gt;"
    if cp < 32:
        return " "
    return chr(cp)


# `@` directly against a non-space character is mermaid 11's `A@{...}` node-metadata
# syntax, so `alice@example.com` hard-fails while `a @ b` parses. Verified by probing
# every ASCII punctuation character against a `graph TD` label.
AT_NODE_REF = re.compile(r"\S@|@\S")

# Characters that break an *unquoted* flowchart label. Verified exhaustively: inside
# double quotes only a bare `"` still breaks, so quoting is a complete fix for all of
# these. (`;` breaks a sequenceDiagram *message*, where quoting does NOT help — that
# needs `#59;` and is left to the gate + the agent.)
UNQUOTED_BREAKERS = "()[]{}|"


def _needs_quoting(body: str) -> bool:
    """True if this label body must be double-quoted to parse."""
    if '"' in body:
        return False  # handled by the bare-quote passes, which quote as they escape
    return any(c in body for c in UNQUOTED_BREAKERS) or bool(AT_NODE_REF.search(body))


def _quote_labels(block: str) -> tuple[str, int]:
    """Wrap label bodies in double quotes where an unquoted char would break parsing."""
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        body = m.group("body")
        stripped = body.strip()
        if not stripped or stripped.startswith('"'):
            return m.group(0)
        if not _needs_quoting(stripped):
            return m.group(0)
        count += 1
        return f'{m.group("open")}"{stripped}"{m.group("close")}'

    return _sub_labels(block, repl), count


def _fix_bare_quotes(block: str) -> tuple[str, int]:
    """Rewrite `"..."` inside an already-quoted label to `#quot;...#quot;`.

    Only touches labels whose body both starts and ends with a quote and has more
    quotes in between — the unambiguous "inner quote" case.
    """
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        body = m.group("body")
        stripped = body.strip()
        if len(stripped) < 2 or not (stripped.startswith('"') and stripped.endswith('"')):
            return m.group(0)
        inner = stripped[1:-1]
        if '"' not in inner:
            return m.group(0)
        count += inner.count('"')
        return f'{m.group("open")}"{inner.replace(chr(34), "#quot;")}"{m.group("close")}'

    return _sub_labels(block, repl), count


def _fix_unquoted_bare_quotes(block: str) -> tuple[str, int]:
    """Quote a label that contains quotes but is not itself quoted.

    `E{Parameter blank or "not done"?}` → `E{"Parameter blank or #quot;not done#quot;?"}`
    """
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        body = m.group("body")
        stripped = body.strip()
        if '"' not in stripped or stripped.startswith('"'):
            return m.group(0)
        count += 1
        escaped = stripped.replace('"', "#quot;")
        return f'{m.group("open")}"{escaped}"{m.group("close")}'

    return _sub_labels(block, repl), count


# A timeline period label of the form `06:00 :` — the clock colon collides with the
# period/event separator and hard-fails. Verified: quoting it does not help, and a
# `section` is optional in a timeline, so neither is a fix. Renaming the period is.
TIMELINE_CLOCK_PERIOD = re.compile(r"^(?P<indent>\s*)(?P<h>\d{1,2}):(?P<m>\d{2})(?=\s*:)", re.MULTILINE)


def _fix_timeline_clocks(block: str) -> tuple[str, int]:
    """Rewrite `06:00 : ...` to `0600 hrs : ...` inside a timeline."""
    if not re.match(r"^\s*timeline\b", block.strip()):
        return block, 0
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        h, minute = int(m.group("h")), m.group("m")
        # `39:00` is hour 39 (elapsed time), not a wall clock — "3900 hrs" would be
        # nonsense. Anything outside a real clock keeps its number and loses the colon.
        if h > 23 or int(minute) > 59:
            replacement = f"hour {h}" if minute == "00" else f"hour {h} min {minute}"
        else:
            replacement = f"{h:02d}{minute} hrs"
        count += 1
        return f"{m.group('indent')}{replacement}"

    return TIMELINE_CLOCK_PERIOD.sub(repl, block), count


# In a sequenceDiagram, `;` is a statement separator, so a semicolon anywhere in a
# message text truncates the statement and hard-fails. Verified: quoting does NOT
# help (`A->>B: "one; two"` fails identically) — `#59;` is the only escape that works.
SEQ_MESSAGE = re.compile(
    r"^(?P<head>\s*\S+\s*(?:-|=)(?:-|=)?[>x)]{1,2}[+-]?\s*\S+\s*:)(?P<text>[^\n]*)$",
    re.MULTILINE,
)

# An entity body sitting immediately before the current position: `&gt`, `&#39`, `#59`.
# If this matches, the `;` we are looking at closes an entity and is not a separator.
ENTITY_TAIL = re.compile(r"&#?[a-zA-Z0-9]+$|#[0-9]+$")


def _fix_sequence_semicolons(block: str) -> tuple[str, int]:
    """Rewrite `;` to `#59;` inside sequenceDiagram message text."""
    if not re.match(r"^\s*sequenceDiagram\b", block.strip()):
        return block, 0
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        text = m.group("text")
        if ";" not in text:
            return m.group(0)

        # A `;` that terminates an entity (`&gt;`, `&#39;`, `#59;`) is NOT a separator
        # and must be left alone — rewriting it produces `&gt#59;`, which is worse than
        # the bug being fixed. Only bare semicolons are escaped.
        out, n = [], 0
        for i, ch in enumerate(text):
            if ch == ";" and not ENTITY_TAIL.search(text[:i]):
                out.append("#59;")
                n += 1
            else:
                out.append(ch)
        if not n:
            return m.group(0)
        count += n
        return m.group("head") + "".join(out)

    return SEQ_MESSAGE.sub(repl, block), count


def repair_text(source: str) -> tuple[str, dict[str, int]]:
    """Repair every <Mermaid> block in a file's text. Returns (new_text, counts)."""
    counts = {
        "entities": 0,
        "quoted_labels": 0,
        "inner_quotes": 0,
        "timeline_clocks": 0,
        "seq_semicolons": 0,
    }

    def fix_block(m: re.Match[str]) -> str:
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)

        # Entities first: decoding may introduce a `(` that then needs quoting.
        def ent_repl(em: re.Match[str]) -> str:
            replacement = _entity_char(em.group(0))
            if replacement is None:
                return em.group(0)
            counts["entities"] += 1
            return replacement

        body = NUMERIC_ENTITY.sub(ent_repl, body)

        # `&quot;` reaches mermaid as a bare `"` (both fast-xml-parser and the
        # client decode it), which terminates the label and hard-fails. Normalise
        # to a real quote here so the label-quoting passes below can reason about
        # it, exactly as the renderer will see it.
        n_quot = body.count("&quot;")
        if n_quot:
            body = body.replace("&quot;", '"')
            counts["entities"] += n_quot

        body, n = _fix_unquoted_bare_quotes(body)
        counts["inner_quotes"] += n
        body, n = _fix_bare_quotes(body)
        counts["inner_quotes"] += n
        body, n = _quote_labels(body)
        counts["quoted_labels"] += n
        body, n = _fix_timeline_clocks(body)
        counts["timeline_clocks"] += n
        body, n = _fix_sequence_semicolons(body)
        counts["seq_semicolons"] += n

        return open_tag + body + close_tag

    return MERMAID_BLOCK.sub(fix_block, source), counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", help=".mlai files or directories to scan")
    ap.add_argument("--write", action="store_true", help="rewrite files in place")
    args = ap.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.mlai")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"⚠️  not found: {p}", file=sys.stderr)

    changed = 0

    for path in files:
        original = path.read_text(encoding="utf-8")
        repaired, counts = repair_text(original)

        if repaired == original:
            continue

        changed += 1
        summary = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
        print(f"{'✏️ ' if args.write else '🔍'} {path}: {summary}")
        if args.write:
            path.write_text(repaired, encoding="utf-8")

    print(f"\n{changed} file(s) {'repaired' if args.write else 'would change'} of {len(files)} scanned.")
    print("Now run mermaid-check.mjs over the same files — this script repairs the known "
          "mechanical defects, the gate is what decides whether a diagram renders.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
