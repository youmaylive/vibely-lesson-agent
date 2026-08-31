"""Render an animated <Svg> the way a student sees it *after* the build finishes.

Why this exists
---------------
Chrome headless does not advance the SMIL clock. Measured against this repo's own
first animated diagram: `--virtual-time-budget=8000`, `--headless=new`,
`--timeout=9000` and `--run-all-compositor-stages-before-draw` all produce a
**byte-identical** screenshot of the *initial* state — so a diagram that opens with
`<g opacity="0">` photographs as a blank canvas. The first three animated diagrams
generated here rendered as an empty axis frame, an empty membrane and an empty
bathtub, and nothing about that was wrong with the diagrams.

That matters beyond convenience: rendering and looking is how every SVG claim in this
project has been checked (rule 18/25), and animation silently took that instrument
away. Without this script the only honest verdict on an animated diagram would be "I
cannot see it", and the temptation would be to judge the source instead — which is
the reasoning-instead-of-measuring failure those rules exist to stop.

What it does
------------
Applies each `fill="freeze"` animation's FINAL value to the element it targets, then
drops the animation elements. That is the frozen end state by definition: SMIL holds
the last value of `values` (or `to`) when an animation with `fill="freeze"` ends.

Deliberately narrow, because a general SMIL interpreter is not needed and would be
wrong more often than it was right:

  * `fill="freeze"` only. An animation without it reverts to the start value, so its
    end state IS the start state and there is nothing to apply — which is also why
    `REVEAL_WITHOUT_FREEZE` is a hard finding in `svg_geometry.py` rather than advice.
  * `repeatCount="indefinite"` loops are left alone and dropped. An ambient pulse has
    no end state; freezing it at an arbitrary phase would invent a frame the student
    never dwells on.
  * `<animateMotion>` is dropped without applying anything. Its end position depends
    on path arithmetic this script deliberately does not do; a wrong position is worse
    than an unmoved one, and the spec restricts motion to accents.

The output is for looking at and for measuring — NOT for shipping. It is a different
document from the one the student loads.

Usage:
    python3 tools/freeze_svg.py lesson.mlai --out-dir /tmp/render     # every <svg>
    python3 tools/freeze_svg.py diagram.svg  --out /tmp/frozen.svg    # one file
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Case-SENSITIVE, and that is the whole point. MLAI's wrapper is `<Svg>` and the SVG
# root inside it is `<svg>` (the parser enforces the lowercase root as
# INVALID_SVG_ROOT). An `re.IGNORECASE` here matches from the wrapper instead, so the
# extracted "diagram" carries a stray `<Svg>` open tag that the browser turns into an
# unknown element wrapping the real one — which is what made the first frozen render
# come out 215px wide inside a 1400px window. Same trap as the case-insensitive count
# that once reported 4 diagrams per lesson where there were 2, by counting `<Svg>` and
# `<svg>` both.
SVG_BLOCK_RE = re.compile(r"<svg[\s\S]*?</svg>")

# One animation element, with its attributes. Self-closing or with a body (an
# <animateMotion> carrying an <mpath> child).
ANIM_RE = re.compile(
    r"<(animate|animateTransform|animateMotion|set)\b([^>]*?)(/>|>[\s\S]*?</\1\s*>)",
    re.IGNORECASE,
)
ATTR_RE = re.compile(r'([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*"([^"]*)"')

# The opening tag that an animation element sits inside. Matching backwards from the
# animation to its parent is the whole trick: SMIL targets the parent element, and
# the parent's own attribute is what has to change.
OPEN_TAG_RE = re.compile(r"<([A-Za-z_][-A-Za-z0-9_:.]*)((?:[^>\"]|\"[^\"]*\")*?)>")


def _attrs(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in ATTR_RE.finditer(text)}


def _final_value(anim: dict[str, str]) -> str | None:
    """The value SMIL holds when this animation ends, or None if it holds nothing."""
    if anim.get("fill", "").strip().lower() != "freeze":
        return None
    if anim.get("repeatCount", "").strip().lower() == "indefinite":
        return None
    if "values" in anim:
        items = [item.strip() for item in anim["values"].split(";") if item.strip()]
        return items[-1] if items else None
    if "to" in anim:
        return anim["to"].strip()
    return None


def _set_attribute(open_tag: str, name: str, value: str) -> str:
    """Return `open_tag` with `name="value"`, replacing any existing one."""
    pattern = re.compile(r'(\s' + re.escape(name) + r'\s*=\s*")[^"]*(")')
    if pattern.search(open_tag):
        return pattern.sub(lambda m: m.group(1) + value + m.group(2), open_tag, count=1)
    close = "/>" if open_tag.rstrip().endswith("/>") else ">"
    body = open_tag.rstrip()[: -len(close)].rstrip()
    return f'{body} {name}="{value}"{close}'


def _parent_span(markup: str, anim_start: int) -> tuple[int, int] | None:
    """Locate the opening tag of the element the animation at `anim_start` targets.

    The nearest unclosed opening tag before it. Scanning backwards over every tag is
    cheaper and less breakable here than building a tree: the markup has already been
    through `XMLValidator` by the time a diagram reaches this script.
    """
    depth = 0
    for match in reversed(list(OPEN_TAG_RE.finditer(markup, 0, anim_start))):
        tag = match.group(0)
        if tag.startswith("</"):
            depth += 1
            continue
        if tag.rstrip().endswith("/>") or tag.startswith("<!") or tag.startswith("<?"):
            continue
        if depth:
            depth -= 1
            continue
        return match.start(), match.end()
    return None


def freeze(markup: str) -> tuple[str, int, int]:
    """Return (frozen markup, animations applied, animations dropped)."""
    applied = dropped = 0
    # Right to left, so the offsets of animations still to process stay valid while
    # the parent tags before them are being rewritten.
    for anim in reversed(list(ANIM_RE.finditer(markup))):
        attrs = _attrs(anim.group(2))
        target = attrs.get("attributeName", "").strip()
        value = _final_value(attrs)
        markup = markup[: anim.start()] + markup[anim.end():]
        if anim.group(1).lower() == "animatemotion" or not target or value is None:
            dropped += 1
            continue
        span = _parent_span(markup, anim.start())
        if span is None:
            dropped += 1
            continue
        start, end = span
        markup = markup[:start] + _set_attribute(markup[start:end], target, value) + markup[end:]
        applied += 1
    return markup, applied, dropped


def _html(svg: str) -> str:
    # `svg{width:100%}` is not cosmetic. A diagram carrying width/height attributes
    # photographs at its intrinsic size in the corner of the window, and a 1000x700
    # canvas inside a 1200x900 screenshot is small enough that a label collision is
    # invisible — which is the one thing these renders exist to reveal. The lesson
    # viewer stretches it the same way (`.mlai-svg__canvas > svg { width: 100% }`).
    return (
        "<!doctype html><body style=\"margin:0;background:#fff\">"
        "<style>svg{width:100%;height:auto;display:block}</style>" + svg
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, help="single output file")
    ap.add_argument("--out-dir", type=pathlib.Path, help="one file per <svg> found")
    ap.add_argument("--html", action="store_true", help="wrap output for a browser screenshot")
    args = ap.parse_args()

    if not args.path.is_file():
        print(f"no such file: {args.path}")
        return 2
    source = args.path.read_text(encoding="utf-8")
    blocks = SVG_BLOCK_RE.findall(source)
    if not blocks:
        print(f"no <svg> found in {args.path}")
        return 2

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.path.stem
    for index, block in enumerate(blocks, 1):
        frozen, applied, dropped = freeze(block)
        payload = _html(frozen) if (args.html or args.out_dir) else frozen
        suffix = ".html" if (args.html or args.out_dir) else ".svg"
        if args.out and len(blocks) == 1:
            out = args.out
        elif args.out_dir:
            out = args.out_dir / f"{stem}_{index}{suffix}"
        else:
            print(payload)
            continue
        out.write_text(payload, encoding="utf-8")
        print(f"{out}  ({applied} frozen, {dropped} dropped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
