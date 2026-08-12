#!/usr/bin/env python3
"""
Geometric measurement and design gates for generated SVGs.

This module is the *enforcement* half of the SVG design framework. The other two
halves are `prompts/svg_design_spec.md` (the rules, loaded into the generation
prompt) and `svg_geometry.test.py` (the proof that the rules are actually
checked). Project rule 18: a rule about generated content is worth nothing until
it is executed — so every spec rule that can be measured is measured here, and
every Finding cites the spec rule ID it violates.

Design constraints, all load-bearing:

* **Pure stdlib, synchronous, no SDK.** `svg_agent.py` constructs
  `AsyncAnthropicBedrock` at module scope, so geometry could not be tested
  without credentials while it lived there. It also means nothing in here can
  call `query()` — a nested SDK session deadlocks MCP init.
* **No npm dependency.** `workers/Dockerfile` runs
  `npm install --production ... || true`, which swallows failures (rule 22).
  Stdlib-only sidesteps that class of silent breakage entirely.
* **A gate that cannot run must not pass silently** (rule 21). Malformed input
  sets `gate_ran = False` on the report; callers must log that, never count it
  as clean.

────────────────────────────────────────────────────────────────────────────
WHAT THIS REPLACED, and why every part of it matters

The geometry that shipped inside `svg_agent.py` reported that **114 of 150**
generated diagrams (76%) had overlapping elements, and rewrote **41** of their
canvases to be wider than 1300 units for 1000 units of drawing — worst case
`viewBox="-1122 -50 3245 800"`, i.e. 27% content and 73% empty space, off
centre. Neither number described the drawings. Both came from measurement bugs:

  1. **the central one** — a `<text>` with `<tspan>` children was measured as a
     single box holding every line concatenated. The generation prompt asks for
     multi-line labels as `<tspan x="…" dy="1.2em">`, so a 5-line centred
     caption was modelled as one box five line-widths across at one x. On
     `module_03/lesson_03.mlai` a label that occupies x = 0…1000 was believed to
     span x = −1072…2072.
  2. width was `len(s) * font_size * 0.62` — one ratio for every glyph. Against
     real Arial metrics that errs **+179%** on "iiii…" and **−34%** on "WWWW…".
  3. `line`, `polyline`, `path` and `polygon` were not measured at all, so the
     old `_autofit_viewbox` docstring's "guarantees nothing is clipped" was
     false: 4/150 blocks clipped connector geometry, worst by 190px.
  4. `<defs>`/`<marker>` subtrees were traversed, so arrowhead coordinates
     counted as page content (159 markers, 87% of blocks).
  5. presentation attributes were read off the element alone — a `font-size` or
     `text-anchor` on an ancestor `<g>` was ignored (57 texts inherit a size,
     956 set `dominant-baseline`).
  6. `transform` was ignored entirely.
  7. the canvas was recomputed from scratch with 50px padding instead of
     honouring the declared `viewBox` — defect 7 is what turned defects 1-3 into
     the visible 27%-fill diagrams.

Because the overlap check ran *before* the LLM quality review and `continue`d on
failure, those phantom findings also meant the review never ran for most
diagrams: they burned all 4 attempts on unfixable geometry and shipped whatever
candidate happened to be first.

The consequence for anyone editing this file: **a false positive here is
expensive.** It costs a full generate+review cycle and corrupts the retry
loop's ranking. That is why the pairwise tests exclude the background rect,
connectors, and any subtree we cannot measure faithfully, and why only three
craft checks are `HARD`.

One rule here was added *after* the framework shipped, by rendering its own
output: SD-FONT. The first diagrams generated against the new spec declared no
`font-family` at all — the old prompt had it as an unenforced bullet that did not
survive the rewrite — and headless Chrome rendered them in a **serif**. Every
width in this module is an Arial advance, so the measurements described a font no
student would see, and the gate was silent about it. It fires on 0 of 150
archived blocks (they all carry the old prompt's family) and fired on 3 of 3
fresh ones. Rule 18, again: measure, render, look.

Measured on the corpus after this rewrite: flag rate **76% → 33%** (50/150), and
on simulated fresh output canvases >1300 **41 → 0**, widest canvas **3245 → 1081**.
Of the 47 blocks carrying a hard finding, 30 carry *only* MISSING_TEXT_ANCHOR —
spec compliance the generator fixes by adding an attribute. Actual collisions
account for 15 blocks (10%): TEXT_SPILL 27, SHAPE_OVERLAP 7, TEXT_OVERLAP 6.

Getting SHAPE_OVERLAP from 74 raw pairs to 7 real ones took naming six
composition idioms, each measured on the corpus and each in its own helper below:
curved-path hulls (`bbox_only`), the background wash (`_mark_background`),
nesting (`NESTING_SHARE`), translucent zone bands (`is_wash`), edge-mounted
markers (`_mounted_on_edge`), and corner joints (`_corner_joined`). All 7
survivors were confirmed by rendering the diagrams to PNG and looking at them
(rule 18) — a decision diamond eating its neighbour's label, a pressure-cooker
whistle covering the lid, callouts over the anatomy figure they annotate, a
caption bar run through two cards. Two blunter rules were tried and rejected
against the same renders: "exempt shapes thinner than 24 units" cannot tell a
30-unit hammer handle from a 50-unit caption bar, and "exempt anything nested"
misses the diamond. `svg_geometry.test.py` (81 cases) pins all of it.
────────────────────────────────────────────────────────────────────────────

CLI (doubles as the operator tool; exit codes mirror `mermaid-check.mjs`):

    python3 svg_geometry.py --dry-run <file.mlai|file.svg>...   # 0 ok, 1 findings, 2 broken
    python3 svg_geometry.py --stats <dir>...                    # corpus aggregates
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path

# ---------------------------------------------------------------------------
# Severity / rule vocabulary
# ---------------------------------------------------------------------------

HARD = "hard"          # fed back to the generator as a fixable defect
ADVISORY = "advisory"  # surfaced to the reviewer, never a solo failure

# Spec rule IDs. Kept as constants so a Finding can never cite a rule that does
# not exist in prompts/svg_design_spec.md — the linkage is what makes this a
# framework rather than a pile of lints.
SD_SPACING = "SD-SPACING"
SD_CANVAS = "SD-CANVAS"
SD_TEXT_FIT = "SD-TEXT-FIT"
SD_ANCHOR = "SD-ANCHOR"
SD_FONT = "SD-FONT"
SD_MEASURABLE = "SD-MEASURABLE"
SD_TYPE = "SD-TYPE"
SD_PALETTE = "SD-PALETTE"
SD_DENSITY = "SD-DENSITY"


@dataclass(frozen=True)
class Box:
    """An axis-aligned bounding box in user units."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def __str__(self) -> str:
        return f"({self.x1:.0f},{self.y1:.0f})-({self.x2:.0f},{self.y2:.0f})"


@dataclass(frozen=True)
class Element:
    """One measured thing on the page.

    `kind` is the local SVG tag for shapes and connectors, or "text" for a text
    line. `uncertain` marks geometry we cannot measure faithfully (rotate /
    matrix / <use>); such elements still contribute to bounds but are excluded
    from pairwise overlap tests, because a false hard finding costs a full
    generate+review cycle.
    """

    kind: str
    box: Box
    label: str = ""
    font_size: float = 0.0
    is_background: bool = False
    is_connector: bool = False
    uncertain: bool = False
    # False only when neither the element nor any ancestor set `text-anchor`.
    # Tracked because an unstated anchor makes the horizontal placement of the
    # box a guess, which makes every other finding about that text untrustworthy
    # (SD-ANCHOR).
    anchor_declared: bool = True
    # The `font-family` resolved from this element or its nearest ancestor that
    # sets one, lowercased; "" when nothing in the chain does. Every width in this
    # module comes from an Arial advance table, so a family that is not
    # metric-compatible with Arial makes the width a guess — and a *missing*
    # family means the renderer picks its own default, which was measured to be
    # a serif in headless Chrome (SD-FONT).
    font_family: str = ""
    # (x1, y1, x2, y2) endpoints for a <line>, so a crossing test can use true
    # segment-vs-rect intersection. A diagonal line's *bounding box* is the whole
    # rectangle it spans, which would false-positive on almost every diagram.
    segment: tuple[float, float, float, float] | None = None
    # True when `box` is a loose outer bound rather than the drawn extent — a
    # curved `<path>`, whose control-point hull can be far larger than the ink.
    # Such elements bound the canvas correctly (over-estimating is the safe
    # direction there) but must not be paired: measured on the corpus, pairing
    # them produced 34 of 74 SHAPE_OVERLAP findings, including a crescent whose
    # hull "overlaps" the background by 91%.
    bbox_only: bool = False
    # Vertices for a <polygon>, in user space. Kept so `region_overlap_area` can
    # test the real triangle/diamond rather than its bounding box — a diamond's
    # box is twice its area, and all four corners of that box are empty.
    points: tuple[tuple[float, float], ...] | None = None
    # A fill this faint is a zone wash — a tinted region marking "danger band" or
    # "target range" — not a drawn object. Chips and labels are *meant* to sit
    # across it, so it bounds the canvas but never pairs, exactly like the
    # background rect. 28 of 150 corpus blocks use one.
    is_wash: bool = False


@dataclass
class Geometry:
    """Everything measurable about one <svg> document."""

    texts: list[Element] = field(default_factory=list)
    shapes: list[Element] = field(default_factory=list)
    connectors: list[Element] = field(default_factory=list)
    background: Element | None = None
    declared: Box | None = None
    parse_error: str | None = None

    def all_elements(self) -> list[Element]:
        return [*self.texts, *self.shapes, *self.connectors]

    def content_bounds(self) -> Box | None:
        """Union of every measured element, background included."""
        boxes = [e.box for e in self.all_elements()]
        if self.background is not None:
            boxes.append(self.background.box)
        if not boxes:
            return None
        return Box(
            min(b.x1 for b in boxes),
            min(b.y1 for b in boxes),
            max(b.x2 for b in boxes),
            max(b.y2 for b in boxes),
        )


@dataclass(frozen=True)
class Finding:
    """One violation, citing the design-spec rule it breaks."""

    rule_id: str
    code: str
    severity: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule_id}/{self.code}: {self.message}"


@dataclass
class GeometryReport:
    findings: list[Finding] = field(default_factory=list)
    gate_ran: bool = True
    error: str | None = None

    @property
    def hard(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == HARD]

    @property
    def advisory(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ADVISORY]

    @property
    def has_hard(self) -> bool:
        return bool(self.hard)

    def summary(self, limit: int = 6) -> str:
        """Compact feedback text for the retry loop."""
        if not self.gate_ran:
            return f"geometry gate did not run: {self.error}"
        if not self.findings:
            return "OK"
        shown = [str(f) for f in (self.hard or self.findings)[:limit]]
        extra = len(self.hard or self.findings) - len(shown)
        return "; ".join(shown) + (f" (+{extra} more)" if extra > 0 else "")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def local_tag(tag: str) -> str:
    """Strip the SVG namespace: '{http://www.w3.org/2000/svg}rect' -> 'rect'."""
    return tag.rsplit("}", 1)[-1].lower()


def to_float(value, default: float = 0.0) -> float:
    """Parse an SVG length, tolerating a 'px' suffix and junk."""
    try:
        return float(str(value).replace("px", "").strip())
    except (ValueError, TypeError, AttributeError):
        return default


def parse_view_box(root: ET.Element) -> Box | None:
    raw = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if not raw:
        return None
    parts = raw.replace(",", " ").split()
    if len(parts) != 4:
        return None
    x, y, w, h = (to_float(p) for p in parts)
    if w <= 0 or h <= 0:
        return None
    return Box(x, y, x + w, y + h)


def overlap_area(a: Box, b: Box, margin: float = 0.0) -> float:
    """Area of the intersection of two boxes, each shrunk by `margin`."""
    ix1 = max(a.x1, b.x1) + margin
    iy1 = max(a.y1, b.y1) + margin
    ix2 = min(a.x2, b.x2) - margin
    iy2 = min(a.y2, b.y2) - margin
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return (ix2 - ix1) * (iy2 - iy1)


def contains(outer: Box, inner: Box, pad: float = 0.0) -> bool:
    """True if `outer`, grown by `pad`, fully contains `inner`."""
    return (
        outer.x1 - pad <= inner.x1
        and outer.y1 - pad <= inner.y1
        and outer.x2 + pad >= inner.x2
        and outer.y2 + pad >= inner.y2
    )


# ---------------------------------------------------------------------------
# Text metrics
# ---------------------------------------------------------------------------
#
# Advance widths in units per 1000em, extracted with stdlib `struct` from the
# `hmtx`/`cmap` tables of Arial 2048-upem on macOS
# (/System/Library/Fonts/Supplemental/Arial{,\ Bold}.ttf) and hardcoded here
# because the worker image ships no fonts and no font library.
#
# Arial is the right basis, not a guess: all 3178 <text> elements in the corpus
# resolve to `Arial, sans-serif` (2504 declare it, 674 inherit it, zero have no
# font in the chain), and `vibely-v2-parser/src/components/content/svg.ts` is a
# pure passthrough, so no client renderer substitutes a different family.
# Helvetica and Liberation Sans are metrically Arial-compatible, which covers
# the Linux and browser fallbacks.
#
# Why a table rather than one ratio: the 0.62 constant this replaced errs +179%
# on "iiii…" and −34% on "WWWW…". The error is not noise, it is systematic in
# the direction of the label's content, which is exactly what a text-fit check
# must not be wrong about.

_ASCII_START = 32

# ASCII 32..126, regular weight.
_ARIAL_REGULAR_ASCII = (
     278,  278,  355,  556,  556,  889,  667,  191,  333,  333,  389,  584,
     278,  333,  278,  278,  556,  556,  556,  556,  556,  556,  556,  556,
     556,  556,  278,  278,  584,  584,  584,  556, 1015,  667,  667,  722,
     722,  667,  611,  778,  722,  278,  500,  667,  556,  833,  722,  778,
     667,  778,  722,  667,  611,  722,  667,  944,  667,  667,  611,  278,
     278,  278,  469,  556,  333,  556,  556,  500,  556,  556,  278,  556,
     556,  222,  222,  500,  222,  833,  556,  556,  556,  556,  333,  500,
     278,  556,  500,  722,  500,  500,  500,  334,  260,  334,  584,
)

# ASCII 32..126, bold. A flat multiplier on the regular table was measured and
# rejected: the true bold/regular ratio ranges 0.96..1.50 per glyph (median
# 1.00, mean 1.07), so a single factor errs −15% on "iiiillll" and +6% on
# "WWWMMM". Since both tables came from the same extraction at no extra cost,
# there is no reason to approximate.
_ARIAL_BOLD_ASCII = (
     278,  333,  474,  556,  556,  889,  722,  238,  333,  333,  389,  584,
     278,  333,  278,  278,  556,  556,  556,  556,  556,  556,  556,  556,
     556,  556,  333,  333,  584,  584,  584,  611,  975,  722,  722,  722,
     722,  667,  611,  778,  722,  278,  556,  722,  611,  833,  722,  778,
     667,  778,  722,  667,  611,  722,  667,  944,  667,  667,  611,  333,
     278,  333,  584,  556,  333,  556,  611,  556,  611,  556,  333,  611,
     611,  278,  278,  556,  278,  889,  611,  611,  611,  611,  389,  556,
     333,  611,  556,  778,  556,  556,  500,  389,  280,  389,  584,
)

# Non-ASCII actually observed in generated diagrams: arrows, maths relations,
# Greek used in medical/scientific labels, and the punctuation an LLM reaches
# for (em dash, curly quotes, ellipsis, bullet).
_ARIAL_REGULAR_EXTRA = {
    0x00A0:  278,  # no-break space
    0x00B0:  400,  # °
    0x00B1:  549,  # ±
    0x00B5:  576,  # µ
    0x00D7:  584,  # ×
    0x00F7:  549,  # ÷
    0x0394:  668,  # Δ
    0x03B1:  578,  # α
    0x03B2:  575,  # β
    0x03BC:  576,  # μ
    0x2013:  556,  # – en dash
    0x2014: 1000,  # — em dash
    0x2018:  222,  # ‘
    0x2019:  222,  # ’
    0x201C:  333,  # “
    0x201D:  333,  # ”
    0x2022:  350,  # •
    0x2026: 1000,  # …
    0x2032:  188,  # ′ prime
    0x2190: 1000,  # ←
    0x2191:  500,  # ↑
    0x2192: 1000,  # →
    0x2193:  500,  # ↓
    0x2248:  549,  # ≈
    0x2260:  549,  # ≠
    0x2264:  549,  # ≤
    0x2265:  549,  # ≥
}

_ARIAL_BOLD_EXTRA = {
    0x00A0:  278,
    0x00B0:  400,
    0x00B1:  549,
    0x00B5:  576,
    0x00D7:  584,
    0x00F7:  549,
    0x0394:  719,
    0x03B1:  615,
    0x03B2:  610,
    0x03BC:  612,
    0x2013:  556,
    0x2014: 1000,
    0x2018:  278,
    0x2019:  278,
    0x201C:  500,
    0x201D:  500,
    0x2022:  350,
    0x2026: 1000,
    0x2032:  240,
    0x2190: 1000,
    0x2191:  500,
    0x2192: 1000,
    0x2193:  500,
    0x2248:  549,
    0x2260:  549,
    0x2264:  549,
    0x2265:  549,
}


def _build_table(ascii_row: tuple[int, ...], extra: dict[int, int]) -> dict[int, int]:
    table = {_ASCII_START + i: w for i, w in enumerate(ascii_row)}
    table.update(extra)
    return table


ARIAL_ADVANCE: dict[int, int] = _build_table(_ARIAL_REGULAR_ASCII, _ARIAL_REGULAR_EXTRA)
ARIAL_ADVANCE_BOLD: dict[int, int] = _build_table(_ARIAL_BOLD_ASCII, _ARIAL_BOLD_EXTRA)

# Anything off the table — CJK, emoji, rarer symbols. 600/1000em sits between
# Arial's lowercase (~556) and uppercase (~667) averages; CJK is really ~1000em,
# so this UNDER-estimates such labels. Deliberate: under-estimating width can
# only suppress a finding, never invent one, and a false hard finding costs a
# full generate+review cycle. Widen the table instead of raising this.
FALLBACK_ADVANCE = 600

# Only used for a bold glyph that is missing from the bold table but present in
# the regular one — mean measured ratio. Not applied to the table itself.
BOLD_FALLBACK_FACTOR = 1.06

# Families the table above is valid for. Helvetica and Liberation Sans are
# metrically Arial-compatible by design (identical advance widths), and
# `sans-serif` / `helvetica neue` resolve to one of them on every renderer in the
# path. Anything else — or, worse, nothing at all — means every width in this
# module is measured in a font the student will not see.
#
# This exists because it happened: the first diagrams generated against the new
# spec carried no `font-family` at all (the rule was in the old prompt as an
# unenforced bullet and did not survive the rewrite), and rendering them in
# headless Chrome showed **serif** text. Arial's advances are wrong for a serif,
# so the widths were fiction — and nothing in the gate noticed, which is exactly
# the shape of rule 18.
ARIAL_COMPATIBLE = (
    "arial", "helvetica", "helvetica neue", "liberation sans", "sans-serif",
    "arimo", "nimbus sans",
)


def is_arial_compatible(family: str) -> bool:
    """True when `family`'s first choice is metrically Arial.

    Only the first entry of the stack matters: it is what the renderer uses when
    present, and every renderer in this path has Arial or a metric clone.
    """
    first = (family or "").split(",")[0].strip().strip("'\"").lower()
    return first in ARIAL_COMPATIBLE

# Vertical metrics, from Arial's `hhea`/`OS/2` tables (upem 2048):
#   ascent 0.9053   descent 0.2119   xHeight 0.5186   capHeight 0.7163
# The ink box of a typical mixed-case label is far tighter than the font's full
# line box, so ASCENT/DESCENT below describe *drawn ink* rather than line
# spacing. Using the full 0.905/0.212 would inflate every label by ~13% of its
# font size vertically and manufacture vertical collisions in correctly spaced
# diagrams.
INK_ASCENT = 0.75    # cap height plus a little for accents/parens
INK_DESCENT = 0.22   # descenders: g j p q y
LINE_HEIGHT = INK_ASCENT + INK_DESCENT   # 0.97em — one line's ink box

# dominant-baseline shifts where `y` sits relative to the ink box. Values are
# the fraction of font-size from `y` up to the ink top. Set on 956 corpus text
# elements and previously ignored, which put every one of those boxes ~0.25em
# off vertically.
_BASELINE_SHIFT = {
    "auto": INK_ASCENT,
    "alphabetic": INK_ASCENT,
    "baseline": INK_ASCENT,
    "text-bottom": INK_ASCENT,
    "ideographic": INK_ASCENT,
    "middle": 0.55,
    "central": 0.55,
    "hanging": 0.10,
    "text-top": 0.0,
    "text-before-edge": 0.0,
}

DEFAULT_FONT_SIZE = 16.0
DEFAULT_LINE_ADVANCE = 1.2   # em, when a tspan gives no dy


def text_advance(text: str, font_size: float, *, bold: bool = False) -> float:
    """Width in user units of `text` rendered in Arial at `font_size`.

    Sums per-glyph advance widths from the measured table. Kerning is ignored:
    Arial's kern pairs shift by only a few units/1000em and always inward, so
    ignoring them over-estimates slightly, which is the safe direction for a
    fit check.
    """
    if not text or font_size <= 0:
        return 0.0
    table = ARIAL_ADVANCE_BOLD if bold else ARIAL_ADVANCE
    total = 0
    for ch in text:
        cp = ord(ch)
        width = table.get(cp)
        if width is None and bold:
            plain = ARIAL_ADVANCE.get(cp)
            width = round(plain * BOLD_FALLBACK_FACTOR) if plain is not None else None
        if width is None:
            width = FALLBACK_ADVANCE
        total += width
    return total * font_size / 1000.0


def fits_chars(width: float, font_size: float) -> int:
    """How many average characters fit in `width` — the SD-TEXT-FIT budget.

    0.55em is the measured mean advance of Arial's mixed-case alphabet. This is
    the number quoted to the model in the design spec; the gate itself always
    measures the real string.
    """
    if font_size <= 0:
        return 0
    return int(width / (0.55 * font_size))


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

# Subtrees that define reusable content rather than drawing it. Traversing
# these treats an arrowhead's local coordinates as page geometry — 159 markers
# across 87% of corpus blocks. NOT including <g>, which does draw.
NON_RENDERING = frozenset({
    "defs", "marker", "symbol", "clippath", "mask", "pattern",
    "lineargradient", "radialgradient", "filter", "metadata", "title", "desc",
    "style", "script",
})

# Transform functions we can represent exactly with an axis-aligned box.
_TRANSLATE_SCALE = ("translate", "scale")

# `rotate`, `matrix`, `skewX`, `skewY` do not map to an axis-aligned box, and
# `<use>` draws geometry defined elsewhere. Such elements still bound the
# canvas but are excluded from pairwise tests — see UNMEASURABLE_SUBTREE.
_OPAQUE_TRANSFORMS = ("rotate", "matrix", "skewx", "skewy")

_TRANSFORM_CALL = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

# Text that is only whitespace/newlines from XML pretty-printing is not a line.
_BLANK = re.compile(r"^\s*$")


@dataclass(frozen=True)
class _Ctx:
    """Inherited presentation state and cumulative transform at one node."""

    dx: float = 0.0
    dy: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    font_size: float = DEFAULT_FONT_SIZE
    font_size_declared: bool = False
    bold: bool = False
    anchor: str = "start"
    anchor_declared: bool = False
    baseline: str = "auto"
    font_family: str = ""
    uncertain: bool = False

    def point(self, x: float, y: float) -> tuple[float, float]:
        return (self.dx + x * self.sx, self.dy + y * self.sy)

    def scaled(self, v: float) -> float:
        """Scale a length by the mean axis scale (fonts scale in both axes)."""
        return v * (abs(self.sx) + abs(self.sy)) / 2.0


def _parse_transform(value: str) -> tuple[float, float, float, float, bool]:
    """Return (dx, dy, sx, sy, opaque) for a transform attribute."""
    dx = dy = 0.0
    sx = sy = 1.0
    opaque = False
    for name, raw_args in _TRANSFORM_CALL.findall(value or ""):
        fn = name.lower()
        args = [float(n) for n in _NUMBER.findall(raw_args)]
        if fn == "translate" and args:
            dx += args[0]
            dy += args[1] if len(args) > 1 else 0.0
        elif fn == "scale" and args:
            k = args[0]
            sx *= k
            sy *= args[1] if len(args) > 1 else k
        elif fn in _OPAQUE_TRANSFORMS:
            opaque = True
            # A rotate about a centre keeps the subtree roughly in place, so the
            # accumulated offset stays useful as a rough position; the element is
            # marked uncertain and never paired.
    return dx, dy, sx, sy, opaque


def _descend(ctx: _Ctx, el: ET.Element) -> _Ctx:
    """Apply an element's transform and inherited presentation attributes."""
    a = el.attrib
    dx, dy, sx, sy, opaque = _parse_transform(a.get("transform", ""))

    new_dx = ctx.dx + dx * ctx.sx
    new_dy = ctx.dy + dy * ctx.sy
    new_sx = ctx.sx * sx
    new_sy = ctx.sy * sy

    font_size = ctx.font_size
    declared = ctx.font_size_declared
    raw_fs = a.get("font-size")
    if raw_fs is not None:
        parsed = _parse_font_size(raw_fs, ctx.font_size)
        if parsed > 0:
            font_size = parsed
            declared = True

    bold = ctx.bold
    weight = (a.get("font-weight") or "").strip().lower()
    if weight:
        bold = weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600)

    anchor = ctx.anchor
    anchor_declared = ctx.anchor_declared
    raw_anchor = (a.get("text-anchor") or "").strip().lower()
    if raw_anchor in ("start", "middle", "end"):
        anchor = raw_anchor
        anchor_declared = True

    family = ctx.font_family
    raw_family = (a.get("font-family") or "").strip().lower()
    if raw_family:
        family = raw_family

    baseline = ctx.baseline
    raw_baseline = (
        a.get("dominant-baseline") or a.get("alignment-baseline") or ""
    ).strip().lower()
    if raw_baseline:
        baseline = raw_baseline

    # `<use>` instantiates geometry defined elsewhere; we cannot see its extent.
    if local_tag(el.tag) == "use":
        opaque = True

    return _Ctx(
        dx=new_dx, dy=new_dy, sx=new_sx, sy=new_sy,
        font_size=font_size, font_size_declared=declared, bold=bold,
        anchor=anchor, anchor_declared=anchor_declared, baseline=baseline,
        font_family=family, uncertain=ctx.uncertain or opaque,
    )


def _parse_font_size(raw: str, inherited: float) -> float:
    """Parse a font-size, resolving em/%/pt against the inherited size."""
    text = str(raw).strip().lower()
    if not text:
        return 0.0
    try:
        if text.endswith("em"):
            return float(text[:-2]) * inherited
        if text.endswith("%"):
            return float(text[:-1]) / 100.0 * inherited
        if text.endswith("pt"):
            return float(text[:-2]) * 4.0 / 3.0
        if text.endswith("px"):
            return float(text[:-2])
        return float(text)
    except ValueError:
        return 0.0


def _parse_length(raw: str | None, font_size: float, default: float = 0.0) -> float:
    """Parse an x/y/dx/dy value, resolving `em`/`ex` against `font_size`."""
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if not text:
        return default
    try:
        if text.endswith("em"):
            return float(text[:-2]) * font_size
        if text.endswith("ex"):
            return float(text[:-2]) * font_size * 0.5186  # Arial x-height
        if text.endswith("px"):
            return float(text[:-2])
        return float(text)
    except ValueError:
        return default


def _first_number(raw: str | None, font_size: float, default: float = 0.0) -> float:
    """First value of a possibly multi-value x/y/dx/dy list.

    SVG allows `x="10 20 30"` to position individual glyphs. Per-glyph
    positioning is not used anywhere in the corpus, and honouring only the first
    value places the line correctly for the overwhelmingly common single-value
    case.
    """
    if raw is None:
        return default
    parts = str(raw).replace(",", " ").split()
    if not parts:
        return default
    return _parse_length(parts[0], font_size, default)


@dataclass
class _Line:
    """One rendered line of text, accumulated during the cursor walk."""

    parts: list[str] = field(default_factory=list)
    width: float = 0.0
    x: float | None = None
    y: float = 0.0
    font_size: float = DEFAULT_FONT_SIZE
    anchor: str = "start"
    baseline: str = "auto"
    anchor_declared: bool = True
    font_family: str = ""
    uncertain: bool = False

    @property
    def text(self) -> str:
        # Only the ends are trimmed; the spaces `_normalise` preserved between
        # runs are rendered ink and part of the label.
        return "".join(self.parts).strip()


def _normalise(text: str) -> str:
    """Collapse XML pretty-printing whitespace the way a renderer does.

    Runs of whitespace collapse to one space, but a *leading or trailing* space
    survives: in `<text>Systolic <tspan>140</tspan> mmHg</text>` the spaces
    around the tspan separate the words, so dropping them yields the rendered
    line "Systolic140mmHg" and under-measures it by two space advances.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    lead = " " if text[:1].isspace() else ""
    trail = " " if text[-1:].isspace() else ""
    return lead + collapsed + trail


class _TextWalker:
    """Turns one <text> element into one Element per *rendered line*.

    SVG text layout is a cursor: `x`/`y` set it absolutely, `dx`/`dy` move it
    relatively, and a `<tspan>` that restates `x` (or supplies a `dy`) starts a
    new line. A tspan's tail text continues the line it interrupted. Modelling
    this is the whole fix — the previous code called `itertext()` and produced
    one box for all five lines of a caption.
    """

    def __init__(self, ctx: _Ctx, el: ET.Element) -> None:
        self.ctx = ctx
        self.el = el
        self.lines: list[_Line] = []
        self.current: _Line | None = None
        self.cursor_x = 0.0
        self.cursor_y = 0.0

    def run(self) -> list[_Line]:
        ctx = _descend(self.ctx, self.el)
        a = self.el.attrib
        self.cursor_x = _first_number(a.get("x"), ctx.font_size, 0.0) + _first_number(
            a.get("dx"), ctx.font_size, 0.0
        )
        self.cursor_y = _first_number(a.get("y"), ctx.font_size, 0.0) + _first_number(
            a.get("dy"), ctx.font_size, 0.0
        )
        self._open(ctx)
        self._emit(ctx, self.el.text)
        for child in self.el:
            self._visit(ctx, child)
        self._close()
        return [ln for ln in self.lines if ln.text]

    # -- line bookkeeping ---------------------------------------------------

    def _open(self, ctx: _Ctx) -> None:
        self.current = _Line(
            x=self.cursor_x,
            y=self.cursor_y,
            font_size=ctx.font_size,
            anchor=ctx.anchor,
            baseline=ctx.baseline,
            anchor_declared=ctx.anchor_declared,
            font_family=ctx.font_family,
            uncertain=ctx.uncertain,
        )

    def _close(self) -> None:
        if self.current is not None and self.current.text:
            self.lines.append(self.current)
        self.current = None

    def _emit(self, ctx: _Ctx, raw: str | None) -> None:
        if raw is None or _BLANK.match(raw):
            return
        text = _normalise(raw)
        if not text:
            return
        if self.current is None:
            self._open(ctx)
        line = self.current
        assert line is not None
        # A line's font-size is the largest of its runs — the tallest ink wins.
        line.font_size = max(line.font_size, ctx.font_size)
        line.uncertain = line.uncertain or ctx.uncertain
        width = text_advance(text, ctx.font_size, bold=ctx.bold)
        width = ctx.scaled(width) if (ctx.sx, ctx.sy) != (1.0, 1.0) else width
        line.parts.append(text)
        line.width += width
        self.cursor_x += width

    def _visit(self, ctx: _Ctx, node: ET.Element) -> None:
        tag = local_tag(node.tag)
        if tag in NON_RENDERING:
            return

        child_ctx = _descend(ctx, node)
        a = node.attrib

        if tag in ("tspan", "textpath", "tref", "a"):
            has_x = a.get("x") is not None
            has_dy = a.get("dy") is not None
            has_y = a.get("y") is not None

            # A restated x, or an explicit dy, starts a new rendered line. This
            # is the shape the generation prompt asks for:
            #     <tspan x="500" dy="1.25em">…</tspan>
            if has_x or has_dy or has_y:
                self._close()
                if has_x:
                    self.cursor_x = _first_number(a.get("x"), child_ctx.font_size, self.cursor_x)
                if has_y:
                    self.cursor_y = _first_number(a.get("y"), child_ctx.font_size, self.cursor_y)
                if has_dy:
                    self.cursor_y += _first_number(a.get("dy"), child_ctx.font_size, 0.0)
                elif has_x and not has_y:
                    # `x` alone on a later tspan means a new line at the default
                    # advance; the corpus always pairs it with dy, but a missing
                    # dy must not stack two lines on top of each other and
                    # manufacture a TEXT_OVERLAP.
                    if self.lines:
                        self.cursor_y += child_ctx.font_size * DEFAULT_LINE_ADVANCE
                if a.get("dx") is not None:
                    self.cursor_x += _first_number(a.get("dx"), child_ctx.font_size, 0.0)
                self._open(child_ctx)
            elif a.get("dx") is not None:
                self.cursor_x += _first_number(a.get("dx"), child_ctx.font_size, 0.0)

            self._emit(child_ctx, node.text)
            for grandchild in node:
                self._visit(child_ctx, grandchild)
            # Tail text continues the line this tspan was part of.
            self._emit(ctx, node.tail)
            return

        # Anything else inside <text> is not text layout; ignore it but keep
        # any tail text, which does render.
        self._emit(ctx, node.tail)


def _line_to_element(ctx: _Ctx, line: _Line) -> Element:
    """Place a measured line into page coordinates."""
    fs = line.font_size
    width = line.width
    x = line.x or 0.0

    if line.anchor == "middle":
        x -= width / 2.0
    elif line.anchor == "end":
        x -= width

    shift = _BASELINE_SHIFT.get(line.baseline, INK_ASCENT)
    top = line.y - shift * fs
    height = fs * LINE_HEIGHT

    px1, py1 = ctx.point(x, top)
    px2, py2 = ctx.point(x + width, top + height)
    return Element(
        kind="text",
        box=Box(min(px1, px2), min(py1, py2), max(px1, px2), max(py1, py2)),
        label=line.text,
        font_size=ctx.scaled(fs),
        uncertain=line.uncertain or ctx.uncertain,
        anchor_declared=line.anchor_declared,
        font_family=line.font_family,
    )


def _points_list(raw: str | None, ctx: _Ctx) -> list[tuple[float, float]]:
    """Transformed vertices of a `points` list (polyline/polygon)."""
    nums = [float(n) for n in _NUMBER.findall(raw or "")]
    xs, ys = nums[0::2], nums[1::2]
    n = min(len(xs), len(ys))
    return [ctx.point(xs[i], ys[i]) for i in range(n)]


def _points_box(raw: str | None, ctx: _Ctx) -> Box | None:
    """Bounding box of a `points` list (polyline/polygon)."""
    nums = [float(n) for n in _NUMBER.findall(raw or "")]
    if len(nums) < 4:
        return None
    xs, ys = nums[0::2], nums[1::2]
    n = min(len(xs), len(ys))
    pts = [ctx.point(xs[i], ys[i]) for i in range(n)]
    return Box(
        min(p[0] for p in pts), min(p[1] for p in pts),
        max(p[0] for p in pts), max(p[1] for p in pts),
    )


# Curve commands. A path built only from M/L/H/V/Z is a polygon in disguise and
# its bounding box is exact; anything here means the box is an over-estimate.
_CURVE_COMMAND = re.compile(r"[CcSsQqTtAa]")


def _path_box(d: str | None, ctx: _Ctx) -> Box | None:
    """Conservative bounding box of a path.

    Uses every coordinate pair in `d`, control points included. A bézier lies
    entirely inside the convex hull of its control points, so the hull is a
    correct outer bound — no curve maths, and it can only over-estimate, which
    for a canvas-containment check is the safe direction.

    Arc flags in an `A` command are booleans, not coordinates, so treating them
    as points would place spurious geometry near the origin. Arcs are rare in
    generated output; a command-aware scan avoids the artifact.
    """
    if not d:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for cmd, chunk in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d):
        nums = [float(n) for n in _NUMBER.findall(chunk)]
        if cmd in "Aa":
            # rx ry rot large-arc sweep x y — only the final pair is a point.
            for i in range(0, len(nums) - 6, 7):
                xs.append(nums[i + 5])
                ys.append(nums[i + 6])
            continue
        if cmd in "Hh":
            xs.extend(nums)
            continue
        if cmd in "Vv":
            ys.extend(nums)
            continue
        xs.extend(nums[0::2])
        ys.extend(nums[1::2])
    if not xs or not ys:
        return None
    # Relative commands would need a running cursor to resolve exactly. The
    # corpus uses absolute commands throughout; a mixed path still yields a box
    # that brackets the drawn geometry closely enough for a containment check,
    # and such elements only ever relax a finding.
    p1 = ctx.point(min(xs), min(ys))
    p2 = ctx.point(max(xs), max(ys))
    return Box(min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))


# A polygon this small is an arrowhead, not a shape worth pairing. Measured: of
# 22 polygons outside <defs>, 7 are under 40x40 (arrowheads) and 15 are real
# decision diamonds 120-270 units across.
ARROWHEAD_MAX_EXTENT = 40.0

# A rect covering at least this fraction of the drawing's own bounds, and
# enclosing all of it, is the background wash rather than content. Present in
# 150/150 corpus blocks because the generation prompt asks for it.
BACKGROUND_AREA_SHARE = 0.80

# How much of the drawing the candidate must actually cover. Measured on the
# corpus: the real background covers 0.95-1.00 of the content bounds, while the
# largest interior panel covers at most 0.26.
BACKGROUND_COVER_SHARE = 0.80

# Absolute floor on a wash's area, as a fraction of the smaller mandated canvas
# (SD-CANVAS: 1000x700 landscape or 900x900 radial). Measured: every corpus wash
# is at least 500000 units square; the largest first-painted interior panel that
# is not one is 184000.
BACKGROUND_MIN_AREA = 0.60 * 1000 * 700


_NO_PAINT = frozenset({"", "none", "transparent"})


def element_boxes(svg_content: str) -> Geometry:
    """Measure every rendered element in an SVG document.

    One Element per *rendered text line*, real Arial advance widths, inherited
    presentation attributes, accumulated translate/scale, connectors included in
    the bounds, and `<defs>`-like subtrees skipped. See the module docstring for
    what each of those replaced.
    """
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError as exc:
        return Geometry(parse_error=f"malformed XML: {exc}")

    geo = Geometry(declared=parse_view_box(root))
    root_ctx = _descend(_Ctx(), root)
    _walk(root, root_ctx, geo)
    _mark_background(geo)
    return geo


def _walk(el: ET.Element, ctx: _Ctx, geo: Geometry) -> None:
    for child in el:
        tag = local_tag(child.tag)
        if tag in NON_RENDERING:
            continue

        child_ctx = _descend(ctx, child)

        if tag == "text":
            for line in _TextWalker(ctx, child).run():
                geo.texts.append(_line_to_element(child_ctx, line))
            continue  # tspans are handled by the walker

        if tag == "g" or tag == "svg" or tag == "a":
            _walk(child, child_ctx, geo)
            continue

        element = _measure_shape(tag, child, child_ctx)
        if element is not None:
            if not element.is_connector and _is_wash(child):
                element = replace(element, is_wash=True)
            (geo.connectors if element.is_connector else geo.shapes).append(element)

        _walk(child, child_ctx, geo)


def _is_wash(el: ET.Element) -> bool:
    """True when the element's fill is faint enough to read as a tinted region."""
    for name in ("fill-opacity", "opacity"):
        raw = el.attrib.get(name)
        if raw is None:
            continue
        try:
            if float(raw.strip()) <= WASH_MAX_OPACITY:
                return True
        except ValueError:
            continue
    return False


def _measure_shape(tag: str, el: ET.Element, ctx: _Ctx) -> Element | None:
    a = el.attrib

    if tag == "rect":
        x = _parse_length(a.get("x"), ctx.font_size)
        y = _parse_length(a.get("y"), ctx.font_size)
        w = _parse_length(a.get("width"), ctx.font_size)
        h = _parse_length(a.get("height"), ctx.font_size)
        if w <= 0 or h <= 0:
            return None
        p1, p2 = ctx.point(x, y), ctx.point(x + w, y + h)
        box = Box(min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
        return Element("rect", box, uncertain=ctx.uncertain)

    if tag == "circle":
        cx = _parse_length(a.get("cx"), ctx.font_size)
        cy = _parse_length(a.get("cy"), ctx.font_size)
        r = _parse_length(a.get("r"), ctx.font_size)
        if r <= 0:
            return None
        p1, p2 = ctx.point(cx - r, cy - r), ctx.point(cx + r, cy + r)
        box = Box(min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
        return Element("circle", box, uncertain=ctx.uncertain)

    if tag == "ellipse":
        cx = _parse_length(a.get("cx"), ctx.font_size)
        cy = _parse_length(a.get("cy"), ctx.font_size)
        rx = _parse_length(a.get("rx"), ctx.font_size)
        ry = _parse_length(a.get("ry"), ctx.font_size)
        if rx <= 0 or ry <= 0:
            return None
        p1, p2 = ctx.point(cx - rx, cy - ry), ctx.point(cx + rx, cy + ry)
        box = Box(min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
        return Element("ellipse", box, uncertain=ctx.uncertain)

    if tag == "line":
        x1 = _parse_length(a.get("x1"), ctx.font_size)
        y1 = _parse_length(a.get("y1"), ctx.font_size)
        x2 = _parse_length(a.get("x2"), ctx.font_size)
        y2 = _parse_length(a.get("y2"), ctx.font_size)
        p1, p2 = ctx.point(x1, y1), ctx.point(x2, y2)
        box = Box(min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
        return Element(
            "line", box, is_connector=True, uncertain=ctx.uncertain,
            segment=(p1[0], p1[1], p2[0], p2[1]),
        )

    if tag == "polyline":
        box = _points_box(a.get("points"), ctx)
        return None if box is None else Element(
            "polyline", box, is_connector=True, uncertain=ctx.uncertain
        )

    if tag == "polygon":
        box = _points_box(a.get("points"), ctx)
        if box is None:
            return None
        # Small polygons are arrowheads drawn inline rather than as a marker.
        arrowhead = max(box.width, box.height) <= ARROWHEAD_MAX_EXTENT
        return Element(
            "polygon", box, is_connector=arrowhead, uncertain=ctx.uncertain,
            points=tuple(_points_list(a.get("points"), ctx)),
        )

    if tag == "path":
        d = a.get("d")
        box = _path_box(d, ctx)
        if box is None:
            return None
        # An unfilled path is a connector or an outline stroke; a filled one is
        # a shape. 108 of 156 corpus paths are fill="none".
        fill = (a.get("fill") or "").strip().lower()
        is_connector = fill in _NO_PAINT
        # A curve's control-point hull is a valid outer bound but a poor stand-in
        # for its drawn extent, so a curved path bounds the canvas without
        # joining the pairwise tests. Straight-line paths (M/L/H/V/Z only) are
        # exactly their hull, so they pair like any polygon.
        curved = bool(_CURVE_COMMAND.search(d or ""))
        return Element(
            "path", box, is_connector=is_connector, uncertain=ctx.uncertain,
            bbox_only=curved,
        )

    if tag in ("image", "foreignobject"):
        x = _parse_length(a.get("x"), ctx.font_size)
        y = _parse_length(a.get("y"), ctx.font_size)
        w = _parse_length(a.get("width"), ctx.font_size)
        h = _parse_length(a.get("height"), ctx.font_size)
        if w <= 0 or h <= 0:
            return None
        p1, p2 = ctx.point(x, y), ctx.point(x + w, y + h)
        box = Box(min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
        # foreignObject content is HTML — we cannot measure inside it.
        return Element(tag, box, uncertain=True)

    if tag == "use":
        return None  # geometry lives elsewhere; _descend already marked it

    return None


def _mark_background(geo: Geometry) -> None:
    """Identify the canvas wash and take it out of the shape list.

    Every label sits on the background by construction, so leaving it in the
    pairing set would make TEXT_SPILL fire on all 150 corpus blocks, and its box
    "overlaps" every other shape.

    Deliberately NOT keyed off the declared viewBox. The already-shipped corpus
    files carry the previous code's inflated canvases (39 declare a width over
    1300 for 1000 units of drawing), so an area test against `declared` misses
    the background on 148/150 of them. Comparing against the *content* bounds
    instead identifies it on 148/150 and does not depend on the canvas being
    sane — which matters precisely when it is not.
    """
    candidates = [s for s in geo.shapes if s.kind == "rect"]
    if not candidates:
        return

    reference = geo.content_bounds()
    if reference is None or reference.area <= 0:
        return

    largest = max(candidates, key=lambda s: s.box.area)
    if largest.box.area < BACKGROUND_AREA_SHARE * reference.area:
        return
    # It must also *cover* the drawing, not merely be as large as it — otherwise a
    # wide banner across the bottom of a tall diagram would qualify. Stated as an
    # intersection share rather than strict containment plus a tolerance: text ink
    # and end-anchored labels routinely poke tens of units outside the nominal
    # wash (30 and 49 units in the two corpus blocks that a 24-unit tolerance
    # missed), while an interior panel covers only single-digit percentages.
    covered = overlap_area(largest.box, reference)
    if covered < BACKGROUND_COVER_SHARE * reference.area:
        return
    # It must be painted *first*. SVG has no z-index — paint order is depth — so a
    # backdrop is by definition the first shape in the document, and 149 of the
    # 150 corpus backgrounds are (the 150th is preceded only by a <defs> marker,
    # which never reaches this list). This is what separates a wash from a large
    # interior panel that happens to enclose the rest of the drawing: 28 corpus
    # blocks have such a panel, and none of them is painted first.
    #
    # An area-and-coverage test alone is not enough: in a four-element diagram the
    # single largest rect covers 97% of the content bounds, so it would be lifted
    # out of the shape list and every pairwise test on that diagram would go
    # quietly dead — a rule-21 failure, a gate passing because it stopped looking.
    if geo.shapes[0] is not largest:
        return
    # And it must be canvas-sized in absolute terms. A wash is drawn edge to edge
    # at the scale the spec mandates; a first-painted panel that merely happens to
    # enclose a sparse drawing is far smaller. Deliberately measured against the
    # *nominal* canvas, not the declared one — the archived viewBoxes were
    # inflated by the code this module replaces (one declares 3245 units wide for
    # 1000 units of drawing), and keying off them is precisely the mistake that
    # made background detection fail on 148/150 blocks in the first attempt.
    if largest.box.area < BACKGROUND_MIN_AREA:
        return

    geo.shapes = [s for s in geo.shapes if s is not largest]
    geo.background = Element(
        largest.kind, largest.box, is_background=True, uncertain=largest.uncertain
    )


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

DEFAULT_MARGIN = 4.0

# A label may hang this far outside the shape it belongs to and still count as
# "inside it". Measured: 6px suppresses 45 of 100 text-vs-shape findings on the
# corpus. Accepted deliberately (risk R2) — 6px at font-size 14-16 is visually
# nothing, and TEXT_OVERFLOWS_RECT catches the genuine in-box overflow case at a
# tighter 2px. The pad only relaxes the cross-shape spill test.
DEFAULT_CONTAINMENT_PAD = 6.0

# Fraction of a label's area that must land on a foreign shape before it counts
# as spilling. Below this, it is a corner clipping a rounded rect.
DEFAULT_TEXT_SPILL = 0.25

# Fraction of the smaller shape's area two shapes must share before it counts as
# a collision rather than two boxes drawn deliberately close. Measured on the
# corpus: at 0.10, 39 blocks have a genuine shape-shape overlap; a 0-threshold
# adds 25 blocks whose shapes touch by a pixel or two.
DEFAULT_SHAPE_DEPTH = 0.10

BOUNDS_TOLERANCE = 2.0


# How much of the smaller shape must lie inside the larger before the pair reads
# as deliberate nesting (a marker on a track, a chip inside a zone band, a lobe
# within an outline) rather than a collision. Measured on the corpus: 26 of 41
# SHAPE_OVERLAP findings were nesting at or above this share, and hand-checking
# ten of them found every one intentional.
NESTING_SHARE = 0.45

# At or below this opacity a fill reads as a tinted zone rather than an object.
# Measured: corpus washes are 0.08-0.20; the faintest opacity used on a real
# drawn shape is 0.30 (a shaded organ), so 0.25 separates them cleanly.
WASH_MAX_OPACITY = 0.25

# How close the smaller shape's centre must sit to an edge of the larger one to
# read as mounted on that edge rather than colliding with it. 8 units, at the
# corpus's typical 2-3 unit stroke widths, is "on the line" and no more.
EDGE_MOUNT_TOLERANCE = 8.0

# How exactly two shapes must align to read as a joint rather than a collision.
# 1 unit: this is about coordinates an author typed to match, not near misses.
JOINT_TOLERANCE = 1.0

# Grid resolution for region sampling. 32x32 = 1024 probes per pair: the area
# error is under 3% on an ellipse, well inside the 10% depth threshold, and it is
# fully deterministic (no Monte Carlo), so two identical blocks always agree.
_REGION_SAMPLES = 32


def _point_in_element(el: Element, x: float, y: float) -> bool:
    """Is (x, y) on the element's ink? Falls back to the bounding box."""
    b = el.box
    if x < b.x1 or x > b.x2 or y < b.y1 or y > b.y2:
        return False
    if el.kind in ("circle", "ellipse"):
        rx, ry = b.width / 2.0, b.height / 2.0
        if rx <= 0 or ry <= 0:
            return False
        nx, ny = (x - b.cx) / rx, (y - b.cy) / ry
        return nx * nx + ny * ny <= 1.0
    if el.kind == "polygon" and el.points and len(el.points) >= 3:
        # Even-odd ray crossing — the rule SVG's default fill-rule uses.
        inside = False
        pts = el.points
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y):
                t = (y - yi) / (yj - yi)
                if x < xi + t * (xj - xi):
                    inside = not inside
            j = i
        return inside
    return True  # rect, text line, image: the box *is* the region


def _corner_joined(a: Element, b: Element) -> bool:
    """Are these two shapes an L-joint of a single constructed object?

    A roadblock's post and crossbar, a bracket, a frame corner: drawn as separate
    rects that share a corner exactly, so the lap where they meet is the joint
    itself, not a collision. Sharing *two* box coordinates to the unit is the
    signature — the corpus's real collisions share none, because a diagram author
    who wanted two boxes apart did not align their edges by accident.
    """
    shared = 0
    for pa, pb in (
        (a.box.x1, b.box.x1), (a.box.x2, b.box.x2),
        (a.box.y1, b.box.y1), (a.box.y2, b.box.y2),
        (a.box.x1, b.box.x2), (a.box.x2, b.box.x1),
        (a.box.y1, b.box.y2), (a.box.y2, b.box.y1),
    ):
        if abs(pa - pb) <= JOINT_TOLERANCE:
            shared += 1
    return shared >= 2


def _mounted_on_edge(small: Element, large: Element) -> bool:
    """Is `small` a marker sitting astride one of `large`'s edges?

    This is a composition idiom, not a collision: a hammer head at the tip of its
    handle, a car straddling the edge of a road, an arrow spout leaving a
    container. Rendering the eight flagged corpus diagrams confirmed every
    instance of it was deliberate, while the findings that remain are all genuine
    defects (a decision diamond eating an adjacent label, callout boxes covering
    the anatomy figure they annotate, a caption bar run through two boxes).

    Stated as "the smaller shape's centre is within EDGE_MOUNT_TOLERANCE of an
    edge and inside that edge's span", which is what separates a mounted marker
    from a box that merely overlaps near a boundary — the latter's centre is tens
    of units away. A blunter "exempt any shape thinner than N units" rule cannot
    make that split: the same corpus holds a 30-unit hammer handle (deliberate)
    and a 50-unit caption bar running through two boxes (a real defect).
    """
    c, b = small.box, large.box
    t = EDGE_MOUNT_TOLERANCE
    on_horizontal_edge = (
        (abs(c.cy - b.y1) <= t or abs(c.cy - b.y2) <= t)
        and b.x1 - t <= c.cx <= b.x2 + t
    )
    on_vertical_edge = (
        (abs(c.cx - b.x1) <= t or abs(c.cx - b.x2) <= t)
        and b.y1 - t <= c.cy <= b.y2 + t
    )
    return on_horizontal_edge or on_vertical_edge


def _is_boxy(el: Element) -> bool:
    return el.kind not in ("circle", "ellipse", "polygon")


def ink_area(el: Element) -> float:
    """Area the element actually paints, not the area of its bounding box.

    An ellipse fills pi/4 (79%) of its box and a diamond exactly half, so using
    the box as the denominator of an overlap ratio understates how deeply a
    neighbour bites into a round shape — which is the direction that hides real
    collisions. Paired with `region_overlap_area` so both sides of every ratio
    are ink.
    """
    if el.kind in ("circle", "ellipse"):
        return 0.7853981633974483 * el.box.width * el.box.height
    if el.kind == "polygon" and el.points and len(el.points) >= 3:
        pts = el.points
        acc = 0.0
        j = len(pts) - 1
        for i in range(len(pts)):
            acc += (pts[j][0] + pts[i][0]) * (pts[j][1] - pts[i][1])
            j = i
        return abs(acc) / 2.0
    return el.box.area


def region_overlap_area(a: Element, b: Element, margin: float = 0.0) -> float:
    """Area where two elements' *ink* overlaps, not where their boxes do.

    Exact for box-shaped pairs. For anything round or angular it samples a fixed
    grid over the box intersection, because the corners of an ellipse's or a
    diamond's bounding box hold no ink: on the corpus, `ellipse (210,110)-(510,450)`
    was reported as overlapping a callout at `(60,130)-(280,190)` that touches it
    only in one such empty corner.
    """
    gross = overlap_area(a.box, b.box, margin)
    if gross <= 0:
        return 0.0
    if _is_boxy(a) and _is_boxy(b):
        return gross

    x1 = max(a.box.x1, b.box.x1) + margin
    y1 = max(a.box.y1, b.box.y1) + margin
    x2 = min(a.box.x2, b.box.x2) - margin
    y2 = min(a.box.y2, b.box.y2) - margin
    n = _REGION_SAMPLES
    cell_w, cell_h = (x2 - x1) / n, (y2 - y1) / n
    hits = 0
    for i in range(n):
        px = x1 + (i + 0.5) * cell_w
        for j in range(n):
            py = y1 + (j + 0.5) * cell_h
            if _point_in_element(a, px, py) and _point_in_element(b, px, py):
                hits += 1
    return gross * hits / float(n * n)


def _pairable(el: Element) -> bool:
    """Whether an element may take part in a pairwise collision test.

    Connectors are excluded because touching the things they join is their whole
    job. `uncertain` geometry (rotate/matrix/<use>/foreignObject) is excluded
    because we cannot place it faithfully, and a false hard finding costs a full
    generate+review cycle and corrupts the retry loop's ranking.
    """
    return (
        not el.is_connector
        and not el.is_background
        and not el.uncertain
        and not el.bbox_only
        and not el.is_wash
    )


def detect_overlaps(
    svg_content: str,
    *,
    margin: float = DEFAULT_MARGIN,
    containment_pad: float = DEFAULT_CONTAINMENT_PAD,
    text_spill: float = DEFAULT_TEXT_SPILL,
    shape_depth: float = DEFAULT_SHAPE_DEPTH,
) -> GeometryReport:
    """Report layout collisions and anything that makes them unmeasurable.

    Hard findings (fed back to the generator as fixable defects):
      TEXT_OVERLAP           two labels occupy the same pixels
      TEXT_SPILL             a label lands on a shape it does not belong to
      SHAPE_OVERLAP          two shapes partially cover each other
      CONTENT_OUTSIDE_CANVAS drawn geometry falls outside the declared viewBox
      MISSING_TEXT_ANCHOR    no text-anchor anywhere in the element's ancestry

    Advisory findings (surfaced to the reviewer, never a solo failure):
      UNMEASURABLE_SUBTREE   geometry this gate cannot place (SD-MEASURABLE)

    MISSING_TEXT_ANCHOR is hard even though nothing visually overlaps: without a
    stated anchor the horizontal position of the box is a guess, so every other
    finding about that label is untrustworthy. It is checked inheritance-aware —
    an anchor on an ancestor `<g>` satisfies it — because firing on correct
    documents is the expensive failure here.
    """
    geo = element_boxes(svg_content)
    if geo.parse_error:
        return GeometryReport(gate_ran=False, error=geo.parse_error)

    findings: list[Finding] = []

    def add(code: str, rule: str, message: str, severity: str = HARD) -> None:
        findings.append(Finding(rule, code, severity, message))

    texts = [t for t in geo.texts if _pairable(t)]
    shapes = [s for s in geo.shapes if _pairable(s)]

    # 1) text vs text — the worst case for readability
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            if overlap_area(a.box, b.box, margin) > 0:
                add(
                    "TEXT_OVERLAP",
                    SD_SPACING,
                    f"text '{a.label[:32]}' {a.box} overlaps "
                    f"text '{b.label[:32]}' {b.box}",
                )

    # 2) text vs a shape it does not belong to
    for t in texts:
        for s in shapes:
            if contains(s.box, t.box, containment_pad):
                continue  # a label inside its own box is the intended case
            if overlap_area(t.box, s.box, margin) <= 0:
                continue
            area = max(1.0, t.box.area)
            if region_overlap_area(t, s) / area > text_spill:  # ink vs ink
                add(
                    "TEXT_SPILL",
                    SD_SPACING,
                    f"text '{t.label[:32]}' {t.box} overlaps {s.kind} {s.box}",
                )

    # 3) shape vs shape — a partial bite only. Two idioms are deliberate and must
    #    not be flagged: full containment, and *substantial* nesting, where the
    #    smaller shape sits mostly inside the larger (a marker centred on a
    #    20-unit track, a chip on a translucent zone band, a lobe inside an
    #    outline). Both hand-checked on the corpus; see NESTING_SHARE.
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            a, b = shapes[i], shapes[j]
            if contains(a.box, b.box) or contains(b.box, a.box):
                continue
            # `margin` gates whether the pair touches at all — a hairline
            # abutment is not a collision — but the depth ratio is measured on
            # the true intersection. Shrinking both boxes first understated a
            # 50x50 bite out of a 200x100 rect as 8.8% instead of 12.5%, putting
            # a real collision under the 10% threshold.
            if overlap_area(a.box, b.box, margin) <= 0:
                continue
            shared = region_overlap_area(a, b)
            if shared <= 0:
                continue
            small, large = sorted((a, b), key=ink_area)
            smaller = max(1.0, ink_area(small))
            if shared / smaller >= NESTING_SHARE:
                continue
            if _mounted_on_edge(small, large):
                continue
            if _corner_joined(small, large):
                continue
            if shared / smaller > shape_depth:
                # HARD, and the 90%-precision bar was cleared by rendering, not
                # by argument: all 7 instances left on the corpus were confirmed
                # real (a decision diamond eating its neighbour's label, a
                # pressure-cooker whistle covering the lid, callout boxes over
                # the anatomy figure they annotate, a caption bar run through two
                # cards). The rule got there by subtraction — 74 raw pairs minus
                # curved-path hulls, the background wash, nesting, zone washes,
                # edge-mounted markers, and corner joints, each idiom measured on
                # the corpus and named in its own helper above.
                add(
                    "SHAPE_OVERLAP",
                    SD_SPACING,
                    f"{a.kind} {a.box} overlaps {b.kind} {b.box} "
                    f"by {100 * shared / smaller:.0f}%",
                )

    # 4) anything drawn outside the declared canvas. Connectors are included
    #    here — being clipped at the edge is a real defect even for an arrow —
    #    but `uncertain` geometry is not, since its position is a guess.
    d = geo.declared
    if d is not None:
        tol = BOUNDS_TOLERANCE

        def outside(box: Box) -> bool:
            return (
                box.x1 < d.x1 - tol or box.y1 < d.y1 - tol
                or box.x2 > d.x2 + tol or box.y2 > d.y2 + tol
            )

        for el in geo.all_elements():
            if el.uncertain or not outside(el.box):
                continue
            what = (
                f"text '{el.label[:32]}'" if el.kind == "text" else el.kind
            )
            add(
                "CONTENT_OUTSIDE_CANVAS",
                SD_CANVAS,
                f"{what} {el.box} falls outside the declared canvas {d}",
            )

    # 5) SD-ANCHOR — an unstated text-anchor corrupts the measurement itself
    for t in geo.texts:
        if not t.anchor_declared:
            add(
                "MISSING_TEXT_ANCHOR",
                SD_ANCHOR,
                f"text '{t.label[:32]}' {t.box} has no text-anchor on it or any "
                "ancestor, so its horizontal position cannot be measured",
            )

    # 6) SD-FONT — the whole width basis. Hard for the same reason as SD-ANCHOR:
    #    it is not that the diagram looks wrong, it is that we cannot claim to
    #    have measured it. Reported once per block, not once per label, because
    #    the fix is a single attribute on the root <svg>.
    wrong_font = [t for t in geo.texts if not is_arial_compatible(t.font_family)]
    if wrong_font:
        families = sorted({t.font_family or "(none declared)" for t in wrong_font})
        add(
            "NON_ARIAL_FONT",
            SD_FONT,
            f"{len(wrong_font)} of {len(geo.texts)} label(s) render in "
            f"{', '.join(families)} — every width in this report is measured with "
            'Arial metrics, so add font-family="Arial, sans-serif" to the root '
            "<svg> (with no family at all the renderer picks a serif)",
        )

    # 7) SD-MEASURABLE — telemetry on how much of the drawing we cannot place.
    #    Advisory: the drawing may be perfect, we just cannot vouch for it.
    unmeasurable = [e for e in geo.all_elements() if e.uncertain]
    if unmeasurable:
        kinds = sorted({e.kind for e in unmeasurable})
        add(
            "UNMEASURABLE_SUBTREE",
            SD_MEASURABLE,
            f"{len(unmeasurable)} element(s) ({', '.join(kinds)}) use rotate/"
            "matrix/skew/<use>/foreignObject and were excluded from the overlap "
            "checks",
            ADVISORY,
        )

    return GeometryReport(findings=findings)


# ---------------------------------------------------------------------------
# Craft gates — SD-TEXT-FIT, SD-CANVAS, SD-PALETTE, SD-TYPE, SD-DENSITY
# ---------------------------------------------------------------------------
#
# One hard check and eight advisory ones. The split is deliberate and follows
# from cost, not taste: a false HARD finding burns a whole generate+review cycle
# and corrupts the retry loop's ranking, so a rule is only hard once it is both
# unambiguous and measured. Everything about *style* stays advisory — it goes to
# the reviewer as context and is scored under CRAFT/DENSITY, where a human-legible
# judgement can override it. A 3-colour process flowchart can be excellent, and a
# hard palette rule would only manufacture gratuitous colour.

# A label may reach this close to its box's inner edge before it reads as
# touching. Tighter than DEFAULT_CONTAINMENT_PAD (6.0) because this test is about
# a label in its *own* box, where the spec asks for 12px of padding — so 2px of
# slack still means the generator missed by 10.
TEXT_FIT_TOLERANCE = 2.0

# Below this share of the declared canvas, the drawing is floating in empty space.
LOW_FILL_SHARE = 0.55

# How far the content centroid may sit from the canvas centre, as a share of
# canvas size, before the composition reads as lopsided.
OFF_CENTER_SHARE = 0.10

# Fewer distinct fills than this across a diagram of any size reads as monotone.
MIN_DISTINCT_FILLS = 3

# A diagram built from this share of one single shape kind has no shape
# vocabulary — the 43%-rect-and-text corpus finding.
SHAPE_MONOTONY_SHARE = 0.85
SHAPE_MONOTONY_MIN_SHAPES = 4

# More text ink than this, relative to shape ink, means the diagram is prose in a
# box rather than a drawing.
TEXT_DOMINANCE_RATIO = 0.60

# Anything smaller is unreadable at presentation size.
MIN_FONT_SIZE = 12.0

# A rendered line wider than this share of the declared canvas is a sentence
# stretched across the frame, not a label.
#
# Measured in *width*, not characters. The prompt's old "<= 20 characters" was
# violated 208 times, but a character count is the wrong instrument: it fires on
# 110/150 blocks, and most of those are legitimate full-width captions ("PPH:
# >=500 mL after vaginal delivery ... or signs of instability") whose length is the
# point. What actually reads badly is a line spanning the frame, and 0.60 of the
# canvas is where the corpus separates: 32/150 blocks above it, 4 above 0.70.
LONG_LINE_SHARE = 0.60

_FILL_ATTR = re.compile(r'\bfill\s*=\s*"([^"]*)"', re.IGNORECASE)


def _fill_palette(svg_content: str) -> set[str]:
    """Distinct painted fill values, normalised. Excludes "none"/transparent."""
    fills = set()
    for raw in _FILL_ATTR.findall(svg_content):
        value = raw.strip().lower()
        if value in _NO_PAINT or value.startswith("url("):
            continue
        fills.add(value)
    return fills


def _segment_intersects_box(seg: tuple[float, float, float, float], box: Box) -> bool:
    """True segment-vs-rect intersection (Liang-Barsky clip).

    Deliberately not a bounding-box test: a diagonal line's bbox is the entire
    rectangle it spans, so a bbox test would report an arrow crossing every label
    in the quadrant. This is the highest false-positive risk in the whole design,
    which is also why `<path>` is skipped entirely rather than approximated.
    """
    x1, y1, x2, y2 = seg
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - box.x1), (dx, box.x2 - x1),
                 (-dy, y1 - box.y1), (dy, box.y2 - y1)):
        if p == 0:
            if q < 0:
                return False  # parallel and outside this edge
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


def _owning_rect(text: Element, shapes: list[Element]) -> Element | None:
    """The smallest true box whose extent holds the text's centre.

    "Smallest" matters: a label inside a card inside a panel belongs to the card,
    and measuring it against the panel would never report an overflow.

    `bbox_only` shapes are excluded: a curved path's control-point hull is not a
    box any label was meant to fit inside. Measured on the corpus, including them
    produced 2 of 8 findings, both against a rendered blob with no visible edge
    (module_08/lesson_03 block 3).
    """
    best = None
    for s in shapes:
        if not _is_boxy(s) or s.is_background or s.is_wash or s.uncertain:
            continue
        if s.bbox_only:
            continue
        b = s.box
        if not (b.x1 <= text.box.cx <= b.x2 and b.y1 <= text.box.cy <= b.y2):
            continue
        if best is None or b.area < best.box.area:
            best = s
    return best


def craft_findings(svg_content: str, geo: Geometry | None = None) -> list[Finding]:
    """Design-quality findings beyond collision: fit, fill, palette, vocabulary.

    Returns [] when the document cannot be parsed — the caller already reports
    that through `detect_overlaps`, and reporting it twice would double-count a
    single failure.
    """
    if geo is None:
        geo = element_boxes(svg_content)
    if geo.parse_error:
        return []

    findings: list[Finding] = []

    def add(code: str, rule: str, message: str, severity: str = ADVISORY) -> None:
        findings.append(Finding(rule, code, severity, message))

    texts = [t for t in geo.texts if not t.uncertain]
    shapes = [s for s in geo.shapes if not s.uncertain]

    # 1) SD-TEXT-FIT (HARD) — a label wider than the box drawn around it. The one
    #    hard craft check: unambiguous, visible to any reader, and precisely the
    #    defect the "compute the width before writing the label" rule prevents.
    #    This check could not ship before the measurement fix — run against the
    #    old flat 0.62 advance ratio it reports 45 blocks / 81 instances against
    #    the true 7 / 9, a 9x false-positive rate.
    for t in texts:
        rect = _owning_rect(t, shapes)
        if rect is None:
            continue
        # The test is "the label is WIDER than its box", not "the label pokes out
        # of its box". That distinction is what makes this precise enough to be
        # HARD: a narrow label poking past the edge of a wide container panel is
        # usually deliberate — an axis annotation set just outside the plot area —
        # and renders correctly, whereas a label wider than its box cannot be
        # fixed by moving it. Measured on the corpus and checked by rendering all
        # 8: the overhang form scored 4/8 (two curved-path hulls, two legend
        # labels beside an 880px panel, all four fine on screen); this form scores
        # 4/4, clearing the 90% promotion bar.
        deficit = t.box.width - rect.box.width
        if deficit > TEXT_FIT_TOLERANCE:
            add(
                "TEXT_OVERFLOWS_RECT",
                SD_TEXT_FIT,
                f"label '{t.label[:40]}' is {t.box.width:.0f}px wide but the "
                f"{rect.kind} around it is only {rect.box.width:.0f}px — shorten "
                f"it, split it across <tspan> lines, or widen the box",
                HARD,
            )

    # 2) SD-CANVAS — emptiness and lopsidedness. Advisory on purpose: both are
    #    symptoms the autofit fix drives toward zero by construction, so they earn
    #    their place as regression tripwires rather than as retry triggers.
    content = geo.content_bounds()
    if geo.declared is not None and content is not None and geo.declared.area > 0:
        drawn = [e for e in geo.all_elements() if not e.is_background]
        if drawn:
            used = Box(
                min(e.box.x1 for e in drawn), min(e.box.y1 for e in drawn),
                max(e.box.x2 for e in drawn), max(e.box.y2 for e in drawn),
            )
            fill = used.area / geo.declared.area
            if fill < LOW_FILL_SHARE:
                add(
                    "LOW_CANVAS_FILL",
                    SD_CANVAS,
                    f"the drawing uses {100 * fill:.0f}% of the declared canvas "
                    f"{geo.declared} — spread it out to fill the frame",
                )
            dx = abs(used.cx - geo.declared.cx) / max(1.0, geo.declared.width)
            dy = abs(used.cy - geo.declared.cy) / max(1.0, geo.declared.height)
            if max(dx, dy) > OFF_CENTER_SHARE:
                add(
                    "OFF_CENTER",
                    SD_CANVAS,
                    f"content centre {used.cx:.0f},{used.cy:.0f} is offset from the "
                    f"canvas centre {geo.declared.cx:.0f},{geo.declared.cy:.0f}",
                )

    # 3) SD-PALETTE / SD-TYPE — is there a visual vocabulary at all?
    fills = _fill_palette(svg_content)
    if len(fills) < MIN_DISTINCT_FILLS:
        add(
            "PALETTE_MONOTONY",
            SD_PALETTE,
            f"only {len(fills)} distinct fill colour(s) — use the palette's roles "
            "to distinguish what the shapes mean",
        )

    drawn_shapes = [s for s in shapes if not s.is_background and not s.is_connector]
    if len(drawn_shapes) >= SHAPE_MONOTONY_MIN_SHAPES:
        kinds: dict[str, int] = {}
        for s in drawn_shapes:
            kinds[s.kind] = kinds.get(s.kind, 0) + 1
        top_kind, top_count = max(kinds.items(), key=lambda kv: kv[1])
        share = top_count / len(drawn_shapes)
        if share >= SHAPE_MONOTONY_SHARE:
            add(
                "SHAPE_MONOTONY",
                SD_TYPE,
                f"{top_count} of {len(drawn_shapes)} shapes are <{top_kind}> — pick a "
                "diagram type whose form carries the idea instead of uniform boxes",
            )

    # 4) SD-DENSITY — text ink against shape ink.
    text_ink = sum(t.box.area for t in texts)
    shape_ink = sum(ink_area(s) for s in drawn_shapes)
    if shape_ink > 0 and text_ink / shape_ink > TEXT_DOMINANCE_RATIO:
        add(
            "TEXT_DOMINANCE",
            SD_DENSITY,
            f"text covers {100 * text_ink / shape_ink:.0f}% as much area as the "
            "shapes — this is prose in a frame, not a drawing",
        )

    # 5) SD-TEXT-FIT (advisory) — unreadable sizes and runaway lines.
    tiny = [t for t in texts if 0 < t.font_size < MIN_FONT_SIZE]
    if tiny:
        add(
            "TINY_FONT",
            SD_TEXT_FIT,
            f"{len(tiny)} label(s) below {MIN_FONT_SIZE:.0f}px, smallest "
            f"{min(t.font_size for t in tiny):.0f}px",
        )
    if geo.declared is not None and geo.declared.width > 0:
        limit = LONG_LINE_SHARE * geo.declared.width
        long_lines = [t for t in texts if t.box.width > limit]
        if long_lines:
            worst = max(long_lines, key=lambda t: t.box.width)
            add(
                "LONG_LINE",
                SD_TEXT_FIT,
                f"{len(long_lines)} line(s) span more than {LONG_LINE_SHARE:.0%} of "
                f"the canvas width, worst {worst.box.width:.0f}px: "
                f"'{worst.label[:48]}' — break it across <tspan> lines",
            )

    # 6) SD-SPACING (advisory) — an arrow drawn through a label. <line> only, by
    #    true segment intersection; see _segment_intersects_box.
    crossings = 0
    for c in geo.connectors:
        if c.uncertain or c.segment is None:
            continue
        for t in texts:
            if _segment_intersects_box(c.segment, t.box):
                crossings += 1
    if crossings:
        add(
            "CONNECTOR_CROSSES_TEXT",
            SD_SPACING,
            f"{crossings} connector/label crossing(s) — route arrows around labels",
        )

    return findings


# Matches the opening <svg ...> tag so a viewBox rewrite can be scoped to it.
# A bare global `re.sub(r'viewBox="[^"]*"', ..., count=1)` hits whichever
# viewBox comes first in document order — and 2 corpus blocks carry a second
# viewBox="0 0 10 10" on a <marker>.
#
# CASE-SENSITIVE on purpose. SVG is XML, so the root element is always the
# lowercase `<svg>`; the MLAI wrapper around it is the capitalised `<Svg>`.
# Matching case-insensitively swallows the wrapper and every block in the
# corpus then fails to parse.
SVG_OPEN_TAG = re.compile(r"<svg\b[^>]*>")
VIEW_BOX_ATTR = re.compile(r'\bviewBox\s*=\s*"[^"]*"', re.IGNORECASE)

# The generation prompt mandates a 40px inner margin, so the visual breathing
# room is already inside the declared canvas. 50px of extra padding — what the
# previous code used — pushed every diagram off-centre for no benefit.
DEFAULT_PADDING = 16.0

# How much wider than declared the canvas may grow before overflow is treated as
# a layout defect instead of something to accommodate. A diagram that needs 60%
# more width is mis-laid-out; silently expanding it is exactly what produced the
# 27%-fill canvases.
DEFAULT_MAX_GROWTH = 1.6


def autofit_viewbox(
    svg_content: str,
    *,
    padding: float = DEFAULT_PADDING,
    max_growth: float = DEFAULT_MAX_GROWTH,
) -> tuple[str, list[Finding]]:
    """Honour the declared canvas; expand only for real, modest overflow.

    Three outcomes:

      content fits            -> returned byte-identical, no findings
      modest overflow         -> canvas expanded to cover it, no findings
      gross overflow          -> canvas untouched, CONTENT_OUTSIDE_CANVAS (hard)

    The last case is the important one. Recomputing the canvas from scratch —
    what this replaced — turns a layout mistake into a silently rescued diagram
    with 73% empty space, and hides the defect from the retry loop that could
    have fixed it. Measured on the corpus: only 8/150 blocks have genuine content
    outside `0 0 1000 700`, worst by 75px, so 142/150 come back untouched.
    """
    geo = element_boxes(svg_content)
    if geo.parse_error:
        return svg_content, [
            Finding(SD_MEASURABLE, "SVG_UNPARSEABLE", HARD, geo.parse_error)
        ]

    content = geo.content_bounds()
    if content is None:
        return svg_content, []  # nothing measurable — leave it alone

    declared = geo.declared
    if declared is None:
        # No canvas declared at all: there is nothing to honour, so fit to
        # content. `_validate_svg` rejects a missing viewBox upstream, but this
        # function must not depend on having been called after it.
        fitted = Box(
            content.x1 - padding, content.y1 - padding,
            content.x2 + padding, content.y2 + padding,
        )
        return _write_view_box(svg_content, fitted), []

    if contains(declared, content, BOUNDS_TOLERANCE):
        return svg_content, []

    union = Box(
        min(declared.x1, content.x1 - padding),
        min(declared.y1, content.y1 - padding),
        max(declared.x2, content.x2 + padding),
        max(declared.y2, content.y2 + padding),
    )

    grew_too_much = (
        union.width > max_growth * declared.width
        or union.height > max_growth * declared.height
    )
    if grew_too_much:
        return svg_content, [
            Finding(
                SD_CANVAS,
                "CONTENT_OUTSIDE_CANVAS",
                HARD,
                f"content {content} needs a canvas {union.width:.0f}x"
                f"{union.height:.0f} against a declared {declared.width:.0f}x"
                f"{declared.height:.0f} — reposition the elements to fit rather "
                "than enlarging the canvas",
            )
        ]

    return _write_view_box(svg_content, union), []


def _write_view_box(svg_content: str, box: Box) -> str:
    """Replace the viewBox on the root <svg> tag only."""
    match = SVG_OPEN_TAG.search(svg_content)
    if not match:
        return svg_content
    new_vb = f'viewBox="{box.x1:.0f} {box.y1:.0f} {box.width:.0f} {box.height:.0f}"'
    open_tag = match.group(0)
    if VIEW_BOX_ATTR.search(open_tag):
        new_tag = VIEW_BOX_ATTR.sub(new_vb, open_tag, count=1)
    else:
        new_tag = open_tag[:-1].rstrip() + " " + new_vb + open_tag[-1]
    return svg_content[: match.start()] + new_tag + svg_content[match.end() :]


# ---------------------------------------------------------------------------
# Corpus helpers — used by the CLI and by svg_geometry.test.py
# ---------------------------------------------------------------------------

# Case-sensitive, for the reason given on SVG_OPEN_TAG: `<Svg>` is the MLAI
# wrapper element, `<svg>` is the document we want to measure.
SVG_BLOCK = re.compile(r"<svg\b[\s\S]*?</svg>")


def extract_svg_blocks(text: str) -> list[str]:
    """Every <svg>...</svg> document in a .mlai (or .svg) file, in order."""
    return SVG_BLOCK.findall(text)


def iter_corpus(paths: list[Path]):
    """Yield (path, index, svg_text) for every SVG block under `paths`."""
    files: list[Path] = []
    for raw in paths:
        if raw.is_dir():
            files.extend(sorted(raw.rglob("*.mlai")))
            files.extend(sorted(raw.rglob("*.svg")))
        elif raw.is_file():
            files.append(raw)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        blocks = [text] if path.suffix == ".svg" else extract_svg_blocks(text)
        for i, block in enumerate(blocks):
            yield path, i, block


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_BROKEN = 2


def _cmd_dry_run(paths: list[Path]) -> int:
    total = hard = broken = 0
    for path, idx, block in iter_corpus(paths):
        total += 1
        report = detect_overlaps(block)
        if not report.gate_ran:
            broken += 1
            print(f"{path}[{idx}]: BROKEN {report.error}", file=sys.stderr)
            continue
        craft = craft_findings(block)
        for f in [*report.findings, *craft]:
            print(f"{path}[{idx}]: {f.severity} {f}")
        if report.has_hard or any(f.severity == HARD for f in craft):
            hard += 1
    print(f"\n{total} block(s): {hard} with hard findings, {broken} unparseable")
    if broken:
        return EXIT_BROKEN
    return EXIT_FINDINGS if hard else EXIT_OK


def _cmd_stats(paths: list[Path]) -> int:
    """Corpus aggregates — the numbers svg_geometry.test.py pins."""
    total = flagged = broken = 0
    hard_flagged = 0
    wide = 0
    widths: list[float] = []
    codes: dict[str, int] = {}
    worst = (0.0, "")

    for path, idx, block in iter_corpus(paths):
        total += 1
        report = detect_overlaps(block)
        if not report.gate_ran:
            broken += 1
            continue
        all_findings = [*report.findings, *craft_findings(block)]
        if all_findings:
            flagged += 1
        if any(f.severity == HARD for f in all_findings):
            hard_flagged += 1
        for f in all_findings:
            codes[f.code] = codes.get(f.code, 0) + 1

        refit, _ = autofit_viewbox(block)
        root_tag = SVG_OPEN_TAG.search(refit)
        vb = VIEW_BOX_ATTR.search(root_tag.group(0)) if root_tag else None
        if vb:
            parts = vb.group(0).split('"')[1].replace(",", " ").split()
            if len(parts) == 4:
                w = to_float(parts[2])
                widths.append(w)
                if w > 1300:
                    wide += 1
                if w > worst[0]:
                    worst = (w, f"{path}[{idx}]")

    widths.sort()
    median = widths[len(widths) // 2] if widths else 0.0
    print(f"blocks scanned      : {total}")
    print(f"unparseable         : {broken}")
    print(f"any finding         : {flagged}  ({flagged / max(1, total):.0%})")
    print(
        f"hard findings       : {hard_flagged}  "
        f"({hard_flagged / max(1, total):.0%})   <- what blocks a lesson"
    )
    print(f"refit width > 1300  : {wide}")
    print(f"refit width median  : {median:.0f}")
    print(f"refit width max     : {worst[0]:.0f}  {worst[1]}")
    print("findings by code    :")
    for code, n in sorted(codes.items(), key=lambda kv: -kv[1]):
        print(f"  {code:24s} {n}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("paths", nargs="+", help=".mlai/.svg files or directories")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report findings per block")
    mode.add_argument("--stats", action="store_true", help="print corpus aggregates")
    args = ap.parse_args(argv)

    paths = [Path(p).expanduser() for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    for p in missing:
        print(f"not found: {p}", file=sys.stderr)
    if missing:
        return EXIT_BROKEN

    return _cmd_stats(paths) if args.stats else _cmd_dry_run(paths)


if __name__ == "__main__":
    sys.exit(main())
