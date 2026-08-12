#!/usr/bin/env python3
"""
Executable expectations for svg_geometry.py.

Project rule 18: a rule about generated content is worth nothing until it is
executed. Last time, two rules written into a prompt from confident reasoning
were both wrong and only rendering caught it. So every expectation about SVG
geometry lives here as a case that runs, not as prose in a docstring.

Stdlib only, no pytest, no network, no credentials — it must run identically on
a Mac and inside the worker image. A gate that works locally but not in the
container is not a gate (rule 22).

    python3 svg_geometry.test.py                 # everything
    python3 svg_geometry.test.py metrics text    # only cases matching a substring
    python3 svg_geometry.test.py --list

    # in the worker image, before pushing (rule 22):
    docker run --rm --entrypoint python3 memebu-worker:latest \
      /app/vibely-lesson-agent/lesson_agent/svg_geometry.test.py

Corpus regression cases need the real generated lessons. They are read from
$SVG_CORPUS_ROOT (default ~/mlai-backups) and SKIP loudly when it is absent —
a skipped corpus must never read as a pass.

XFAIL
─────
A case marked `xfail=` is a known-wrong behaviour of the current
implementation, recorded on purpose so the before-picture is in the repo and the
fix is provable rather than asserted. An XFAIL does not fail the run; an XPASS
(a marked case that unexpectedly passes) prints a reminder to drop the marker.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import svg_geometry as G  # noqa: E402

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

CASES: list[tuple[str, object, str | None]] = []


def case(name: str, xfail: str | None = None):
    """Register a test case. `xfail` is a reason string for a known failure."""

    def wrap(fn):
        CASES.append((name, fn, xfail))
        return fn

    return wrap


class Skip(Exception):
    """Raised to skip a case whose inputs are unavailable (corpus absent).

    A Skip is the dangerous kind of not-running: the case would have been
    meaningful and silently did not execute. It triggers the CORPUS_SKIPPED
    banner.
    """


class Pending(Skip):
    """Raised when the API a case targets does not exist yet.

    Distinct from Skip because it is expected during Phase 0 and says nothing
    about coverage of the code that *does* exist — so it must not fire the
    CORPUS_SKIPPED banner and make a real corpus gap invisible in the noise.
    """


def eq(actual, expected, what: str) -> None:
    if actual != expected:
        raise AssertionError(f"{what}: expected {expected!r}, got {actual!r}")


def close(actual: float, expected: float, tol: float, what: str) -> None:
    if abs(actual - expected) > tol:
        raise AssertionError(f"{what}: expected {expected} ±{tol}, got {actual:.3f}")


def true(cond, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def codes(report: G.GeometryReport) -> list[str]:
    return [f.code for f in report.findings]


def svg(body: str, view_box: str = "0 0 1000 700", extra: str = "") -> str:
    # The root carries `font-family` because real generated output must (SD-FONT):
    # every width in the module comes from an Arial advance table, so a document
    # with no family declared is measured in a font the student never sees. Leaving
    # it off here would make every synthetic case carry a NON_ARIAL_FONT finding and
    # drown the case each one is actually testing. `--font` cases override it.
    if "font-family" not in extra:
        extra = f'font-family="Arial, sans-serif" {extra}'
    return (
        f'<svg viewBox="{view_box}" xmlns="http://www.w3.org/2000/svg" {extra}>'
        f"{body}</svg>"
    )


def view_box_of(svg_text: str) -> tuple[float, float, float, float]:
    """The root <svg>'s viewBox, as parsed by the same code the gate uses."""
    tag = G.SVG_OPEN_TAG.search(svg_text)
    true(tag is not None, "no <svg> tag found")
    attr = G.VIEW_BOX_ATTR.search(tag.group(0))
    true(attr is not None, "no viewBox on the root <svg>")
    parts = attr.group(0).split('"')[1].replace(",", " ").split()
    eq(len(parts), 4, "viewBox component count")
    return tuple(G.to_float(p) for p in parts)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

CORPUS_ROOT = Path(os.environ.get("SVG_CORPUS_ROOT", str(Path.home() / "mlai-backups")))
_corpus_cache: list[tuple[Path, int, str]] | None = None


def corpus() -> list[tuple[Path, int, str]]:
    """Every SVG block in the corpus, or Skip if the corpus is not present."""
    global _corpus_cache
    if _corpus_cache is None:
        if not CORPUS_ROOT.exists():
            raise Skip(f"corpus not found at {CORPUS_ROOT} (set SVG_CORPUS_ROOT)")
        _corpus_cache = list(G.iter_corpus([CORPUS_ROOT]))
        if not _corpus_cache:
            raise Skip(f"no SVG blocks under {CORPUS_ROOT}")
    return _corpus_cache


def corpus_block(suffix: str, index: int = 0) -> str:
    """One named block, e.g. corpus_block("module_03/lesson_03.mlai", 0)."""
    for path, idx, block in corpus():
        if idx == index and str(path).replace("\\", "/").endswith(suffix):
            return block
    raise Skip(f"corpus block not found: {suffix}[{index}]")


FIXTURE_DIR = Path(__file__).resolve().parent / "testdata"

# Real generated blocks, checked into the repo so the load-bearing regression
# cases run in the worker image too. `~/mlai-backups` is absent there and in CI,
# and 11 cases skipping is not 11 cases passing — but nor is a synthetic fixture a
# substitute for output the generator actually produced.
FIXTURES = {
    "oversized-canvas.svg": "the 3245px canvas — worst case of the autofit bug",
    "label-wider-than-box.svg": "two labels swallowed by their cards (SD-TEXT-FIT)",
    "label-overflow-panel.svg": "a caption wider than its box, over a panel",
    "connector-bounds.svg": "a diagram whose <line> geometry defines the bounds",
    "all-rects.svg": "9 of 9 shapes are <rect> (SD-TYPE)",
}


def fixture(name: str) -> str:
    """A checked-in real block. Unlike `corpus()`, this never skips."""
    path = FIXTURE_DIR / name
    if not path.exists():
        raise Skip(f"fixture missing: {path}")
    return path.read_text(encoding="utf-8")


# Measured on 2026-08-12 against the 150 blocks in ~/mlai-backups, using the
# geometry that shipped in svg_agent.py. This is the before-picture. Every
# number here is a defect, not a target — see svg_geometry.py's docstring for
# which defect produces which.
BASELINE = {
    "blocks": 150,
    "unparseable": 0,
    "flagged": 114,          # 76% — of which 88 contain multi-tspan text
    "refit_width_over_1300": 41,
    "refit_width_max": 3245,  # module_03/lesson_03.mlai[0]: 27% fill, 73% empty
}

# What Phase 1 achieved on the same corpus, measured. Any drift trips this file.
#
# The refit numbers are measured on *simulated fresh output* (see
# `fresh_corpus_stats`), not on the corpus files as they sit on disk. Those files
# already carry the old code's damaged canvas — `module_03/lesson_03.mlai[0]`
# declares `-1122 -50 3245 800` for 1000x700 of drawing — and the new
# keep-declared autofit faithfully preserves a declared canvas, damaged or not.
# Measured against the files as-is, 39 still read >1300 no matter how correct the
# code is; the number describes the archive, not the gate. Restoring a plausible
# `0 0 1000 700` first is what asks the question the plan meant to ask: "given
# what the generator emits, does autofit still blow the canvas up?" Answer: no.
TARGET = {
    "blocks": 150,
    "unparseable": 0,
    "flagged_max": 55,            # from 114 — the multi-tspan phantom is gone
    "refit_width_over_1300": 0,   # from 41, on fresh canvases
    "refit_width_max": 1100,      # from 3245, on fresh canvases
    "hard_flagged_max": 47,       # blocks with at least one HARD finding
}

# Per-code instance counts after Phase 1, so a regression in one check cannot
# hide behind an improvement in another. MISSING_TEXT_ANCHOR dominates by design:
# it is spec compliance telemetry (SD-ANCHOR), not a collision.
TARGET_CODES = {
    "MISSING_TEXT_ANCHOR": 223,
    # Zero, and that is the assertion: all 150 archived blocks declare
    # `font-family="Arial, sans-serif"` because the OLD prompt mandated it in a
    # bullet that did not survive the spec rewrite. So the rule that caught the
    # regression in fresh output has no false positives on 150 real diagrams.
    "NON_ARIAL_FONT": 0,
    "TEXT_SPILL": 27,
    "UNMEASURABLE_SUBTREE": 11,
    "SHAPE_OVERLAP": 7,
    "TEXT_OVERLAP": 6,
}

# Phase 3 craft gates, measured on the same 150 blocks. Only TEXT_OVERFLOWS_RECT is
# HARD; everything else is advisory and reaches the reviewer as context.
#
# The two SD-CANVAS codes are measured on *fresh* canvases (see `fresh_canvas`),
# because on the archived files they are dominated by the old autofit's damage
# rather than by the drawings: LOW_CANVAS_FILL reads 47 blocks as-is and 1 on a
# restored canvas, OFF_CENTER 4 and 2. That collapse is itself the evidence that
# both were artifacts of the bug Phase 1 fixed, which is why they stay advisory —
# regression tripwires, not retry triggers.
TARGET_CRAFT = {
    "SHAPE_MONOTONY": 77,          # 51% of blocks are 100% rectangles: the SD-TYPE case
    "CONNECTOR_CROSSES_TEXT": 44,
    "TEXT_DOMINANCE": 6,
    "TINY_FONT": 5,
    "TEXT_OVERFLOWS_RECT": 4,      # HARD; all 4 confirmed by rendering
}
TARGET_CRAFT_FRESH = {
    "LONG_LINE": 32,
    "OFF_CENTER": 2,
    "LOW_CANVAS_FILL": 1,
}


# ---------------------------------------------------------------------------
# Text metrics (Phase 1)
# ---------------------------------------------------------------------------

_NO_METRICS = "svg_geometry has no text_advance() — the metrics table is missing"


def advance(s: str, fs: float, bold: bool = False) -> float:
    if not hasattr(G, "text_advance"):
        raise Pending(_NO_METRICS)
    return G.text_advance(s, fs, bold=bold)


@case("metrics: real sentence at 16px")
def _() -> None:
    # Sum of Arial advance widths for this string is 14508/1000em.
    # The shipped 0.62 ratio gives 287.7px for the same string — +24%.
    close(advance("Deep tendon reflexes dampened", 16), 232.1, 0.5, "sentence @16")


@case("metrics: narrow glyphs are not average")
def _() -> None:
    # 'i' is 222/1000em, not 620. The ratio errs +179% here.
    close(advance("i" * 10, 16), 35.5, 0.2, "'i'x10 @16")


@case("metrics: wide glyphs are not average")
def _() -> None:
    # 'W' is 944/1000em. The ratio errs -34% here.
    close(advance("W" * 10, 16), 151.0, 0.2, "'W'x10 @16")


@case("metrics: scales linearly with font-size")
def _() -> None:
    close(advance("Hello", 32), 2 * advance("Hello", 16), 0.01, "16 vs 32")


@case("metrics: bold is measured per glyph, not by a flat factor")
def _() -> None:
    # The plan specified a flat BOLD_FACTOR = 1.06. Measuring Arial Bold's real
    # hmtx table refuted it: the per-glyph ratio spans 0.961-1.502 with a median
    # of exactly 1.000. A flat 1.06 would understate "iiiillll" by 15.3% and
    # overstate "WWWMMM" by 6.0%. `svg_geometry` ships both real tables and keeps 1.06 only as a
    # per-glyph fallback for codepoints absent from them. "Sodium" measures
    # 47.460 -> 51.338 (x1.0817); a flat 1.06 would have said 50.308.
    plain = advance("Sodium", 14)
    close(plain, 47.460, 0.01, "plain advance")
    close(advance("Sodium", 14, bold=True), 51.338, 0.01, "bold advance")

    # The two extremes that rule out a single factor.
    narrow = advance("iiiillll", 14)
    close(advance("iiiillll", 14, bold=True) / narrow, 1.2523, 0.001, "narrow ratio")
    wide = advance("WWWMMM", 14)
    close(advance("WWWMMM", 14, bold=True) / wide, 1.0000, 0.001, "wide ratio")


@case("metrics: em dash is a full em")
def _() -> None:
    close(advance("—", 16), 16.0, 0.05, "em dash @16")


@case("metrics: unknown glyph falls back, never zero")
def _() -> None:
    # CJK, emoji and anything else off the table use FALLBACK_ADVANCE=600.
    close(advance("漢", 16), 9.6, 0.05, "CJK @16")
    true(advance("\U0001f600", 16) > 0, "emoji must not measure as zero-width")


@case("metrics: empty string measures zero")
def _() -> None:
    eq(advance("", 16), 0.0, "empty string")


# ---------------------------------------------------------------------------
# The central bug: multi-line labels
# ---------------------------------------------------------------------------

MULTILINE = svg(
    """
    <rect x="0" y="0" width="1000" height="700" fill="#f8f9fa"/>
    <text x="500" y="600" font-size="16" text-anchor="middle" font-family="Arial">
      <tspan x="500" dy="0">Uterine atony is the cause in seven of ten cases</tspan>
      <tspan x="500" dy="1.25em">Massage the fundus and give oxytocin ten units</tspan>
      <tspan x="500" dy="1.25em">Reassess tone after two minutes, not before</tspan>
      <tspan x="500" dy="1.25em">Escalate to bimanual compression if still soft</tspan>
      <tspan x="500" dy="1.25em">Call for blood early; do not wait for shock</tspan>
    </text>
    """
)



@case("multiline: one Element per rendered line")
def _() -> None:
    geo = G.element_boxes(MULTILINE)
    eq(len(geo.texts), 5, "text line count")


@case("multiline: no phantom overflow flag")
def _() -> None:
    # The drawing occupies 0..1000. Today the checker believes one label spans
    # x = -1072..2072 and flags the block; that is the whole bug.
    report = G.detect_overlaps(MULTILINE)
    true(report.gate_ran, "gate must run")
    eq(codes(report), [], "findings on a clean 5-line caption")


@case("multiline: viewBox is left byte-identical")
def _() -> None:
    fitted, findings = G.autofit_viewbox(MULTILINE)
    eq(fitted, MULTILINE, "viewBox must not be rewritten when content fits")
    eq([f.code for f in findings], [], "findings")


@case("multiline: each line stays inside the canvas")
def _() -> None:
    geo = G.element_boxes(MULTILINE)
    for t in geo.texts:
        true(t.box.x1 > 0, f"line '{t.label[:24]}' starts at x={t.box.x1:.0f}, inside 0")
        true(t.box.x2 < 1000, f"line '{t.label[:24]}' ends at x={t.box.x2:.0f}, inside 1000")


@case("multiline: lines advance down the page by dy")
def _() -> None:
    geo = G.element_boxes(MULTILINE)
    tops = [t.box.y1 for t in geo.texts]
    eq(tops, sorted(tops), "lines must be ordered top to bottom")
    close(tops[1] - tops[0], 16 * 1.25, 0.5, "line spacing")


@case("multiline: tspan tail text continues the same line")
def _() -> None:
    # `<text>A<tspan>B</tspan>C</text>` is one line reading "ABC", not three.
    # Passes today only because itertext() joins everything (defect 1); the
    # Phase 1 cursor walk must keep it passing for the right reason.
    one = svg(
        '<text x="100" y="100" font-size="16" text-anchor="start">'
        'Systolic <tspan font-weight="bold">140</tspan> mmHg</text>'
    )
    geo = G.element_boxes(one)
    eq(len(geo.texts), 1, "line count")
    eq(geo.texts[0].label, "Systolic 140 mmHg", "joined label")


# ---------------------------------------------------------------------------
# Traversal: what must and must not be measured
# ---------------------------------------------------------------------------



@case("traversal: <defs> and <marker> are not page content")
def _() -> None:
    # NOTE: passes VACUOUSLY today — the marker's <path> is skipped because no
    # path is ever measured (defect 3), not because <defs> is pruned. It stays
    # unmarked because it must hold once connectors are measured.
    # 159 markers across 87% of corpus blocks. Harmless today only because
    # paths are ignored; a live phantom the moment connectors are measured.
    doc = svg(
        """
        <defs>
          <marker id="a" viewBox="0 0 10 10" refX="5" refY="5"
                  markerWidth="6" markerHeight="6">
            <path d="M 0 0 L 10 5 L 0 10 z"/>
          </marker>
        </defs>
        <rect x="100" y="100" width="200" height="100"/>
        <text x="110" y="150" font-size="14" text-anchor="start">Label</text>
        """
    )
    geo = G.element_boxes(doc)
    eq(len(geo.shapes), 1, "shapes outside <defs>")
    eq(len(geo.connectors), 0, "the marker's path must not be measured")


@case("traversal: a marker's own viewBox is never rewritten")
def _() -> None:
    # 2 corpus blocks carry viewBox="0 0 10 10" on a <marker>. A bare global
    # re.sub(..., count=1) is one document-order accident away from corrupting it.
    doc = svg(
        '<defs><marker id="a" viewBox="0 0 10 10">'
        '<path d="M0 0 L10 5 L0 10 z"/></marker></defs>'
        '<rect x="-40" y="10" width="200" height="100"/>'
        '<text x="20" y="60" font-size="14" text-anchor="start">Hi</text>'
    )
    fitted, _ = G.autofit_viewbox(doc)
    true('viewBox="0 0 10 10"' in fitted, "the marker viewBox must survive untouched")


@case("traversal: <g transform=translate> offsets its children")
def _() -> None:
    doc = svg(
        '<g transform="translate(300, 200)">'
        '<rect x="10" y="20" width="100" height="50"/></g>'
    )
    geo = G.element_boxes(doc)
    eq(len(geo.shapes), 1, "shape count")
    box = geo.shapes[0].box
    close(box.x1, 310, 0.01, "translated x1")
    close(box.y1, 220, 0.01, "translated y1")


@case("traversal: nested translates accumulate")
def _() -> None:
    doc = svg(
        '<g transform="translate(100,100)"><g transform="translate(50,25)">'
        '<rect x="0" y="0" width="10" height="10"/></g></g>'
    )
    geo = G.element_boxes(doc)
    close(geo.shapes[0].box.x1, 150, 0.01, "accumulated x1")
    close(geo.shapes[0].box.y1, 125, 0.01, "accumulated y1")


@case("traversal: rotate marks the subtree uncertain, not wrong")
def _() -> None:
    # 3 instances in the corpus. Such geometry still bounds the canvas but is
    # excluded from pairing — a false hard finding costs a generate+review cycle.
    doc = svg(
        '<g transform="rotate(-90 100 300)">'
        '<text x="100" y="300" font-size="14" text-anchor="middle">Pressure</text></g>'
    )
    geo = G.element_boxes(doc)
    eq(len(geo.texts), 1, "text still measured")
    true(geo.texts[0].uncertain, "rotated text must be flagged uncertain")
    report = G.detect_overlaps(doc)
    true("UNMEASURABLE_SUBTREE" in codes(report), "advisory finding expected")
    eq([f.severity for f in report.findings if f.code == "UNMEASURABLE_SUBTREE"],
       [G.ADVISORY], "UNMEASURABLE_SUBTREE must stay advisory")


# ---------------------------------------------------------------------------
# Presentation-attribute inheritance
# ---------------------------------------------------------------------------



@case("inherit: font-size comes from the ancestor <g>")
def _() -> None:
    # 57 corpus <text> elements carry no font-size and silently default to 16;
    # 7 blocks set it on a <g>. At 12px the box is 13.8 tall, not 19.2.
    doc = svg('<g font-size="12"><text x="10" y="100" text-anchor="start">Na+</text></g>')
    geo = G.element_boxes(doc)
    eq(len(geo.texts), 1, "text count")
    close(geo.texts[0].font_size, 12.0, 0.01, "inherited font-size")
    # The box is Arial's *ink* extent (INK_ASCENT 0.75 + INK_DESCENT 0.22 = 0.97
    # em), not the 1.15em line box the plan assumed. Measured from the corpus
    # font's hhea table: ascent 0.9053 + descent 0.2119 = 1.117em of line box, of
    # which the glyphs actually paint 0.97. Using the line box would inflate every
    # label ~13% vertically and manufacture collisions between adjacent rows of
    # text — the exact failure mode this rewrite exists to remove.
    close(geo.texts[0].box.height, 12 * 0.97, 0.01, "ink box height at 12px")


@case("inherit: text-anchor comes from the ancestor <g>")
def _() -> None:
    doc = svg(
        '<g text-anchor="middle"><text x="500" y="100" font-size="16">Centered</text></g>'
    )
    geo = G.element_boxes(doc)
    box = geo.texts[0].box
    close(box.cx, 500, 1.0, "middle-anchored text must center on x")


@case("inherit: inherited anchor is not a MISSING_TEXT_ANCHOR")
def _() -> None:
    # Passes VACUOUSLY today: MISSING_TEXT_ANCHOR does not exist yet, so nothing
    # can false-positive. It is the guard that keeps Phase 3 honest.
    # The false-positive guard. MISSING_TEXT_ANCHOR is hard, because an
    # unstated anchor corrupts the measurement and makes every other finding on
    # the block untrustworthy — so it must be inheritance-aware or it fires on
    # correct documents.
    doc = svg(
        '<g text-anchor="middle">'
        '<text x="500" y="100" font-size="16">A</text>'
        '<text x="500" y="140" font-size="16">B</text></g>'
    )
    report = G.detect_overlaps(doc)
    true("MISSING_TEXT_ANCHOR" not in codes(report), "inherited anchor must satisfy SD-ANCHOR")


@case("inherit: a genuinely absent anchor is reported")
def _() -> None:
    doc = svg('<text x="500" y="100" font-size="16">No anchor anywhere</text>')
    report = G.detect_overlaps(doc)
    true("MISSING_TEXT_ANCHOR" in codes(report), "absent anchor must violate SD-ANCHOR")


@case("font: a document with no font-family is a hard SD-FONT finding")
def _() -> None:
    # Caught by rendering, not by reasoning (rule 18). The first two diagrams
    # generated against the new spec declared no family at all — the old prompt's
    # `font-family="Arial, sans-serif"` bullet did not survive the rewrite — and
    # headless Chrome rendered them in a SERIF. Every width in this module is an
    # Arial advance, so those measurements described a font nobody would see, and
    # nothing in the gate noticed.
    doc = (
        '<svg viewBox="0 0 1000 700" xmlns="http://www.w3.org/2000/svg">'
        '<text x="500" y="100" font-size="16" text-anchor="middle">A</text>'
        '<text x="500" y="140" font-size="16" text-anchor="middle">B</text></svg>'
    )
    report = G.detect_overlaps(doc)
    true("NON_ARIAL_FONT" in codes(report), "an undeclared font-family must violate SD-FONT")
    hard = [f.code for f in report.hard]
    true("NON_ARIAL_FONT" in hard, "SD-FONT is hard: it invalidates every other width")


@case("font: a metric-compatible family on the root satisfies SD-FONT")
def _() -> None:
    # The false-positive guard, in both the inheritance and the substitution
    # direction: the family is declared once on the root (as the spec requires,
    # not per element), and Helvetica/Liberation Sans share Arial's advances so
    # the table is still valid for them.
    for family in ("Arial, sans-serif", "Helvetica, Arial, sans-serif",
                   "Liberation Sans", "sans-serif"):
        doc = svg(
            '<text x="500" y="100" font-size="16" text-anchor="middle">A</text>'
            '<text x="500" y="140" font-size="16" text-anchor="middle">B</text>',
            extra=f'font-family="{family}"',
        )
        report = G.detect_overlaps(doc)
        true("NON_ARIAL_FONT" not in codes(report), f"{family} must satisfy SD-FONT")


@case("font: a family the metrics do not describe is reported")
def _() -> None:
    # A serif is the case that actually shipped, and it is not a near-miss: Times
    # is ~10% narrower than Arial at the same size, which is more than the 2px
    # TEXT_OVERFLOWS_RECT threshold on any label of normal length.
    doc = svg(
        '<text x="500" y="100" font-size="16" text-anchor="middle">A</text>'
        '<text x="500" y="140" font-size="16" text-anchor="middle">B</text>',
        extra='font-family="Georgia, serif"',
    )
    report = G.detect_overlaps(doc)
    true("NON_ARIAL_FONT" in codes(report), "a serif family must violate SD-FONT")


@case("font: an inherited family satisfies the rule for its children")
def _() -> None:
    doc = (
        '<svg viewBox="0 0 1000 700" xmlns="http://www.w3.org/2000/svg">'
        '<g font-family="Arial, sans-serif">'
        '<text x="500" y="100" font-size="16" text-anchor="middle">A</text>'
        '<text x="500" y="140" font-size="16" text-anchor="middle">B</text>'
        "</g></svg>"
    )
    report = G.detect_overlaps(doc)
    true("NON_ARIAL_FONT" not in codes(report), "a family on an ancestor <g> must count")


@case("inherit: dominant-baseline shifts the box")
def _() -> None:
    # Set on 956 corpus text elements and currently ignored, so every one of
    # those boxes sits ~0.25em off.
    plain = G.element_boxes(
        svg('<text x="10" y="100" font-size="20" text-anchor="start">X</text>')
    ).texts[0]
    middle = G.element_boxes(
        svg('<text x="10" y="100" font-size="20" text-anchor="start"'
            ' dominant-baseline="middle">X</text>')
    ).texts[0]
    true(
        middle.box.y1 > plain.box.y1,
        "a middle baseline must sit lower than an alphabetic one",
    )
    close(middle.box.y1, 100 - 0.55 * 20, 2.0, "middle-baseline top")


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------



@case("connectors: a <line> contributes to the bounds")
def _() -> None:
    # 908 <line> + 340 <path> are invisible to the shipped gate, which is why
    # its "guarantees nothing is clipped" claim is false: 4/150 blocks clip
    # connector geometry, worst by 190px (module_07/lesson_04.mlai:149).
    doc = svg('<line x1="10" y1="20" x2="400" y2="300" stroke="#333"/>')
    geo = G.element_boxes(doc)
    eq(len(geo.connectors), 1, "connector count")
    eq(geo.connectors[0].box.as_tuple(), (10.0, 20.0, 400.0, 300.0), "line bbox")


@case("connectors: a <path> bbox bounds its control points")
def _() -> None:
    # A bézier lies inside its control hull, so the hull is a correct
    # conservative bound — no curve maths required.
    doc = svg('<path d="M 100 100 C 150 20 250 20 300 100" fill="none" stroke="#333"/>')
    geo = G.element_boxes(doc)
    eq(len(geo.connectors), 1, "connector count")
    box = geo.connectors[0].box
    close(box.x1, 100, 0.01, "path x1")
    close(box.y1, 20, 0.01, "path y1")
    close(box.x2, 300, 0.01, "path x2")


@case("connectors: excluded from shape pairing")
def _() -> None:
    # Passes VACUOUSLY today (connectors are invisible to the gate). Once they
    # are measured, this is what stops every arrow being a SHAPE_OVERLAP.
    # A connector's whole job is to touch the things it joins. Pairing it like
    # a shape would flag every correct diagram.
    doc = svg(
        '<rect x="100" y="100" width="150" height="80"/>'
        '<rect x="400" y="100" width="150" height="80"/>'
        '<line x1="250" y1="140" x2="400" y2="140" stroke="#333"/>'
        '<text x="175" y="145" font-size="14" text-anchor="middle">A</text>'
        '<text x="475" y="145" font-size="14" text-anchor="middle">B</text>'
    )
    report = G.detect_overlaps(doc)
    eq(codes(report), [], "an arrow touching two boxes is correct, not a collision")


# ---------------------------------------------------------------------------
# Background rect
# ---------------------------------------------------------------------------

BG_DOC = svg(
    '<rect x="0" y="0" width="1000" height="700" fill="#f8f9fa"/>'
    '<rect x="100" y="100" width="200" height="100" fill="#4a90d9"/>'
    '<rect x="500" y="100" width="200" height="100" fill="#4a90d9"/>'
    '<text x="200" y="155" font-size="14" text-anchor="middle">Left</text>'
    '<text x="600" y="155" font-size="14" text-anchor="middle">Right</text>'
)



@case("background: identified as the canvas fill")
def _() -> None:
    # Present in 150/150 corpus blocks — the prompt asks for it.
    geo = G.element_boxes(BG_DOC)
    true(geo.background is not None, "background rect must be identified")
    eq(geo.background.box.as_tuple(), (0.0, 0.0, 1000.0, 700.0), "background box")


@case("background: excluded from pairing and spill tests")
def _() -> None:
    # Passes today because `contains()` already exempts a label inside the
    # background rect. Kept unmarked so Phase 1 cannot regress it.
    # Every label sits on the background by construction; pairing against it
    # would make TEXT_SPILL fire on all 150 blocks.
    report = G.detect_overlaps(BG_DOC)
    eq(codes(report), [], "a clean two-box diagram must produce no findings")


# ---------------------------------------------------------------------------
# autofit_viewbox: keep-declared, expand-on-overflow, clamp
# ---------------------------------------------------------------------------



@case("autofit: content that fits is left untouched")
def _() -> None:
    # Every corpus block declares an authoritative canvas; recomputing from
    # scratch is what produced the 3245px viewBox. Only 8/150 blocks have real
    # content outside 0 0 1000 700, so 142/150 must come back byte-identical.
    fitted, findings = G.autofit_viewbox(BG_DOC)
    eq(fitted, BG_DOC, "svg must be returned unchanged")
    eq([f.code for f in findings], [], "findings")


@case("autofit: modest overflow expands the canvas")
def _() -> None:
    # Passes today for the wrong reason: everything is refitted, so of course
    # this one grows. The assertion still holds after keep-declared lands.
    doc = svg(
        '<rect x="0" y="0" width="1000" height="700" fill="#eee"/>'
        '<rect x="960" y="100" width="120" height="80"/>'  # 80px past the edge
        '<text x="1020" y="145" font-size="14" text-anchor="middle">Out</text>'
    )
    fitted, findings = G.autofit_viewbox(doc, padding=16.0)
    x, y, w, h = view_box_of(fitted)
    true(w > 1000, "canvas must grow to cover the overflow")
    true(w < 1600, f"growth must stay modest, got {w}")
    eq([f.code for f in findings], [], "a modest expansion is not a finding")


@case("autofit: gross overflow is a finding, not a rescue")
def _() -> None:
    # A diagram needing a 60%-wider canvas is mis-laid-out. Expanding silently
    # is exactly the 27%-fill failure mode, so the canvas is left alone and the
    # defect is fed back to the generator.
    doc = svg(
        '<rect x="0" y="0" width="1000" height="700" fill="#eee"/>'
        '<rect x="1800" y="100" width="120" height="80"/>'
        '<text x="1860" y="145" font-size="14" text-anchor="middle">Way out</text>'
    )
    fitted, findings = G.autofit_viewbox(doc)
    eq(view_box_of(fitted), (0.0, 0.0, 1000.0, 700.0), "canvas must not be expanded")
    true("CONTENT_OUTSIDE_CANVAS" in [f.code for f in findings], "hard finding expected")
    eq([f.severity for f in findings if f.code == "CONTENT_OUTSIDE_CANVAS"],
       [G.HARD], "gross overflow must be hard")


@case("autofit: a missing viewBox is added, not silently skipped")
def _() -> None:
    doc = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect x="10" y="10" width="100" height="50"/>'
        '<text x="20" y="40" font-size="14" text-anchor="start">Hi</text></svg>'
    )
    fitted, _ = G.autofit_viewbox(doc)
    x, y, w, h = view_box_of(fitted)
    true(w > 0 and h > 0, "a viewBox must be written when none was declared")


# ---------------------------------------------------------------------------
# Overlap thresholds
# ---------------------------------------------------------------------------


@case("overlap: two labels on top of each other are flagged")
def _() -> None:
    doc = svg(
        '<text x="100" y="100" font-size="16" text-anchor="start">Anterior wall</text>'
        '<text x="105" y="103" font-size="16" text-anchor="start">Posterior wall</text>'
    )
    report = G.detect_overlaps(doc)
    true("TEXT_OVERLAP" in codes(report), "colliding labels must be flagged")


@case("overlap: a label inside its own box is not a collision")
def _() -> None:
    doc = svg(
        '<rect x="100" y="100" width="300" height="80" fill="#4a90d9"/>'
        '<text x="250" y="145" font-size="16" text-anchor="middle">Contraction</text>'
    )
    report = G.detect_overlaps(doc)
    eq(codes(report), [], "the intended case must be silent")


@case("overlap: a few px of overhang is tolerated")
def _() -> None:
    # R2: the 6px pad suppresses 45 text-shape findings corpus-wide (100 -> 55).
    # Accepted because 6px at fs 14-16 is invisible, and TEXT_OVERFLOWS_RECT
    # catches the in-box case at a tighter 2px.
    doc = svg(
        '<rect x="100" y="100" width="120" height="40" fill="#4a90d9"/>'
        '<text x="160" y="125" font-size="14" text-anchor="middle">Oxytocin IV</text>'
    )
    report = G.detect_overlaps(doc, containment_pad=6.0)
    eq(codes(report), [], "a 5px overhang must not be a finding")


@case("overlap: fully nested shapes are legitimate")
def _() -> None:
    doc = svg(
        '<rect x="100" y="100" width="400" height="200" fill="#fff" stroke="#333"/>'
        '<rect x="140" y="140" width="120" height="60" fill="#4a90d9"/>'
        '<text x="200" y="175" font-size="14" text-anchor="middle">Inner</text>'
    )
    report = G.detect_overlaps(doc)
    eq(codes(report), [], "nesting is a normal grouping idiom")


@case("overlap: partially overlapping shapes are flagged")
def _() -> None:
    doc = svg(
        '<rect x="100" y="100" width="200" height="100" fill="#4a90d9"/>'
        '<rect x="250" y="150" width="200" height="100" fill="#e05c5c"/>'
        '<text x="150" y="130" font-size="12" text-anchor="start">A</text>'
        '<text x="400" y="230" font-size="12" text-anchor="start">B</text>'
    )
    report = G.detect_overlaps(doc)
    true("SHAPE_OVERLAP" in codes(report), "half-overlapping boxes must be flagged")


# ---------------------------------------------------------------------------
# Fail-loud behaviour (rule 21)
# ---------------------------------------------------------------------------


@case("fail-loud: malformed XML sets gate_ran=False, never PASS")
def _() -> None:
    # A gate that cannot run must not pass silently — this is exactly how the
    # Mermaid bug shipped in the first place.
    report = G.detect_overlaps('<svg viewBox="0 0 10 10"><rect x="1"</svg>')
    eq(report.gate_ran, False, "gate_ran")
    true(report.error, "an error message is required")
    eq(report.findings, [], "a broken gate reports no findings")
    eq(report.has_hard, False, "a broken gate must not claim a hard failure")


@case("fail-loud: an unparseable svg is not silently refitted")
def _() -> None:
    broken = '<svg viewBox="0 0 10 10"><rect x="1"</svg>'
    fitted, findings = G.autofit_viewbox(broken)
    eq(fitted, broken, "unparseable input must be returned untouched")
    true("SVG_UNPARSEABLE" in [f.code for f in findings], "the failure must be reported")


@case("fail-loud: an empty svg is handled, not crashed")
def _() -> None:
    report = G.detect_overlaps(svg(""))
    true(report.gate_ran, "an empty but well-formed svg parses fine")
    eq(report.findings, [], "nothing drawn, nothing to report")


@case("fail-loud: every finding cites a real spec rule")
def _() -> None:
    # The linkage that makes this a framework: a Finding may not cite a rule
    # that does not exist in prompts/svg_design_spec.md.
    known = {v for k, v in vars(G).items() if k.startswith("SD_") and isinstance(v, str)}
    true(known, "no SD_* rule constants found")
    docs = [
        svg('<text x="100" y="100" font-size="16">No anchor</text>'),
        svg('<rect x="1800" y="100" width="120" height="80"/>'
            '<text x="1860" y="145" font-size="14" text-anchor="middle">Out</text>'),
        MULTILINE,
        BG_DOC,
    ]
    for doc in docs:
        report = G.detect_overlaps(doc)
        for f in report.findings:
            true(f.rule_id in known, f"unknown rule id {f.rule_id!r} on {f.code}")
            true(f.severity in (G.HARD, G.ADVISORY), f"bad severity {f.severity!r}")
            true(bool(f.message.strip()), f"{f.code} has an empty message")


@case("fail-loud: measurement is deterministic")
def _() -> None:
    # module_06/lesson_05.mlai carries the same block twice (lines 54 and 507);
    # identical input must give identical findings, or the retry loop's ranking
    # becomes a coin flip.
    a = G.detect_overlaps(BG_DOC)
    b = G.detect_overlaps(BG_DOC)
    eq([str(f) for f in a.findings], [str(f) for f in b.findings], "repeat run")


# ---------------------------------------------------------------------------
# Corpus regression — the real net
# ---------------------------------------------------------------------------


def refit_width(block: str) -> float:
    fitted, _ = G.autofit_viewbox(block)
    try:
        return view_box_of(fitted)[2]
    except AssertionError:
        return 0.0


_VIEW_BOX_ATTR = re.compile(r'viewBox="[^"]*"')


def fresh_canvas(block: str) -> str:
    """Restore the canvas the generator declares, undoing the old code's damage.

    41 archived blocks have an inflated `viewBox` written into them by the
    geometry this module replaced. `autofit_viewbox` is keep-declared by design,
    so it preserves that damage — correctly. To ask "does autofit blow up *fresh*
    output?" the declared canvas has to be the one the prompt asks for.
    """
    return _VIEW_BOX_ATTR.sub('viewBox="0 0 1000 700"', block, count=1)


def corpus_stats() -> dict[str, float]:
    blocks = corpus()
    stats = {"blocks": len(blocks), "unparseable": 0, "flagged": 0,
             "hard_flagged": 0,
             "refit_width_over_1300": 0, "refit_width_max": 0.0}
    for _, _, block in blocks:
        report = G.detect_overlaps(block)
        if not report.gate_ran:
            stats["unparseable"] += 1
            continue
        if report.findings:
            stats["flagged"] += 1
        if report.has_hard:
            stats["hard_flagged"] += 1
        w = refit_width(block)
        if w > 1300:
            stats["refit_width_over_1300"] += 1
        stats["refit_width_max"] = max(stats["refit_width_max"], w)
    return stats


def fresh_corpus_stats() -> dict[str, float]:
    """Canvas metrics on simulated fresh output — see `fresh_canvas`."""
    stats = {"refit_width_over_1300": 0, "refit_width_max": 0.0}
    for _, _, block in corpus():
        w = refit_width(fresh_canvas(block))
        if w > 1300:
            stats["refit_width_over_1300"] += 1
        stats["refit_width_max"] = max(stats["refit_width_max"], w)
    return stats


def corpus_code_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, _, block in corpus():
        for finding in G.detect_overlaps(block).findings:
            counts[finding.code] = counts.get(finding.code, 0) + 1
    return counts


@case("corpus: every block parses")
def _() -> None:
    stats = corpus_stats()
    eq(stats["blocks"], BASELINE["blocks"], "block count")
    eq(stats["unparseable"], 0, "unparseable blocks")


@case("corpus: the baseline defects are gone")
def _() -> None:
    # The before-picture is kept in BASELINE and asserted *negatively*: these are
    # the numbers the old geometry produced, and none of them may come back.
    stats = corpus_stats()
    true(
        stats["flagged"] < BASELINE["flagged"],
        f"flag rate must beat the {BASELINE['flagged']}/150 baseline, "
        f"got {stats['flagged']}",
    )
    fresh = fresh_corpus_stats()
    true(
        fresh["refit_width_over_1300"] < BASELINE["refit_width_over_1300"],
        f"oversized canvases must beat the baseline {BASELINE['refit_width_over_1300']}, "
        f"got {fresh['refit_width_over_1300']}",
    )


@case("corpus: per-code instance counts hold")
def _() -> None:
    # Totals alone would let one check regress while another improves.
    counts = corpus_code_counts()
    for code, expected in TARGET_CODES.items():
        eq(counts.get(code, 0), expected, f"{code} instances")
    unexpected = sorted(set(counts) - set(TARGET_CODES))
    eq(unexpected, [], "codes fired that this file does not pin")


@case("corpus: hard findings are a minority")
def _() -> None:
    # What actually fails a diagram in the retry loop. 47 of 150 blocks, and 30
    # of those 47 carry nothing but MISSING_TEXT_ANCHOR — spec compliance the
    # generator fixes by adding an attribute, not a layout defect. Collisions
    # alone account for 15 blocks (10%).
    stats = corpus_stats()
    true(
        stats["hard_flagged"] <= TARGET["hard_flagged_max"],
        f"{stats['hard_flagged']}/150 blocks carry a hard finding, "
        f"want <= {TARGET['hard_flagged_max']}",
    )


@case("corpus: flag rate is credible")
def _() -> None:
    # 76% of generated diagrams cannot all be broken. A gate that fails three
    # quarters of its input is measuring itself, not the drawings.
    stats = corpus_stats()
    true(
        stats["flagged"] <= TARGET["flagged_max"],
        f"{stats['flagged']}/{stats['blocks']} flagged, want <= {TARGET['flagged_max']}",
    )


@case("corpus: no oversized canvases")
def _() -> None:
    stats = fresh_corpus_stats()
    eq(stats["refit_width_over_1300"], TARGET["refit_width_over_1300"], "canvases >1300")
    true(
        stats["refit_width_max"] <= TARGET["refit_width_max"],
        f"widest canvas {stats['refit_width_max']:.0f}, "
        f"want <= {TARGET['refit_width_max']}",
    )


@case("corpus: the 3245px block refits sanely")
def _() -> None:
    # The worst case of the old bug. Measured on a restored canvas for the reason
    # given at TARGET: the archived file has `-1122 -50 3245 800` baked into it,
    # and keep-declared autofit is *supposed* to leave a declared canvas alone.
    block = fresh_canvas(corpus_block("module_03/lesson_03.mlai", 0))
    fitted, _ = G.autofit_viewbox(block)
    x, y, w, h = view_box_of(fitted)
    true(w <= 1200, f"refit width {w:.0f}, want <= 1200")
    true(x >= -60, f"refit origin x {x:.0f}, want >= -60")


@case("corpus: identical blocks give identical findings")
def _() -> None:
    blocks = [b for _, _, b in corpus()]
    seen: dict[str, list[str]] = {}
    for block in blocks:
        key = block.strip()
        report = G.detect_overlaps(block)
        got = [str(f) for f in report.findings]
        if key in seen:
            eq(got, seen[key], "duplicate block findings")
        seen[key] = got


# ---------------------------------------------------------------------------
# Craft gates (Phase 3)
# ---------------------------------------------------------------------------


def craft_codes(svg_text: str) -> list[str]:
    if not hasattr(G, "craft_findings"):
        raise Pending("svg_geometry has no craft_findings() yet")
    return [f.code for f in G.craft_findings(svg_text)]


def craft_severity(svg_text: str, code: str) -> str | None:
    for f in G.craft_findings(svg_text):
        if f.code == code:
            return f.severity
    return None


CARD = (
    '<rect x="{x}" y="{y}" width="{w}" height="60" fill="#4A90D9"/>'
    '<text x="{cx}" y="{cy}" text-anchor="middle" font-size="16">{label}</text>'
)


def card(x: float, y: float, w: float, label: str) -> str:
    return CARD.format(x=x, y=y, w=w, cx=x + w / 2, cy=y + 34, label=label)


@case("craft: a label wider than its box is HARD")
def _() -> None:
    # 'Twenty-eight characters here' at 16px is ~215px wide in a 120px box.
    doc = svg(card(100, 100, 120, "Twenty-eight characters here"))
    true("TEXT_OVERFLOWS_RECT" in craft_codes(doc), "expected a fit finding")
    eq(craft_severity(doc, "TEXT_OVERFLOWS_RECT"), G.HARD, "fit severity")


@case("craft: a label that fits its box is not flagged")
def _() -> None:
    doc = svg(card(100, 100, 300, "Short label"))
    true("TEXT_OVERFLOWS_RECT" not in craft_codes(doc), "false positive on a fitting label")


@case("craft: a narrow label beside a wide panel is not a fit failure")
def _() -> None:
    # The precision case. A label poking past the edge of a wide container is a
    # deliberate idiom (an axis annotation outside the plot area) and renders
    # correctly — the overhang form of this test scored 4/8 on the corpus because
    # of exactly this shape. Only "wider than its box" is flagged.
    doc = svg(
        '<rect x="60" y="100" width="880" height="200" fill="#f8f9fa"/>'
        '<text x="60" y="290" text-anchor="start" font-size="14">Plotted every 4 hrs</text>'
    )
    true("TEXT_OVERFLOWS_RECT" not in craft_codes(doc), "flagged a label beside a panel")


@case("craft: a curved path's hull is never a label's box")
def _() -> None:
    # A control-point hull is not an edge anything was meant to fit inside; two of
    # eight corpus findings came from a blob with no visible border.
    doc = svg(
        '<path d="M 300 270 Q 330 250 360 270 L 360 330 Q 330 350 300 330 Z" fill="#4A90D9"/>'
        '<text x="330" y="300" text-anchor="middle" font-size="16">Wide-open mouth,</text>'
    )
    true("TEXT_OVERFLOWS_RECT" not in craft_codes(doc), "flagged against a curve hull")


@case("craft: the innermost box owns the label")
def _() -> None:
    # A card inside a panel: measuring against the panel would never report an
    # overflow, so the smallest containing box has to win.
    doc = svg(
        '<rect x="40" y="40" width="920" height="600" fill="#f8f9fa"/>'
        + card(100, 100, 120, "Twenty-eight characters here")
    )
    true("TEXT_OVERFLOWS_RECT" in craft_codes(doc), "outer panel masked the overflow")


@case("craft: all-rect diagrams are flagged SHAPE_MONOTONY")
def _() -> None:
    body = "".join(card(60 + 200 * i, 100, 160, f"Item {i}") for i in range(5))
    codes_seen = craft_codes(svg(body))
    true("SHAPE_MONOTONY" in codes_seen, "expected SHAPE_MONOTONY")
    eq(craft_severity(svg(body), "SHAPE_MONOTONY"), G.ADVISORY, "monotony severity")


@case("craft: a mixed shape vocabulary is not flagged")
def _() -> None:
    body = (
        card(60, 100, 160, "One")
        + '<circle cx="400" cy="130" r="50" fill="#50C878"/>'
        + '<ellipse cx="600" cy="130" rx="60" ry="40" fill="#F5A623"/>'
        + '<polygon points="800,90 860,130 800,170 740,130" fill="#FF6B6B"/>'
        + '<text x="800" y="230" text-anchor="middle" font-size="16">Decision</text>'
    )
    true("SHAPE_MONOTONY" not in craft_codes(svg(body)), "flagged a mixed vocabulary")


@case("craft: a diagonal arrow does not cross every label in its quadrant")
def _() -> None:
    # The highest false-positive risk in the design. A diagonal line's bounding box
    # is the whole rectangle it spans, so a bbox test reports a crossing against a
    # label sitting well clear of the line itself.
    doc = svg(
        '<line x1="100" y1="100" x2="900" y2="600" stroke="#666"/>'
        '<text x="820" y="140" text-anchor="middle" font-size="16">Clear of it</text>'
        '<text x="150" y="560" text-anchor="middle" font-size="16">Also clear</text>'
    )
    true("CONNECTOR_CROSSES_TEXT" not in craft_codes(doc), "diagonal bbox false positive")


@case("craft: an arrow through a label IS a crossing")
def _() -> None:
    doc = svg(
        '<line x1="100" y1="300" x2="900" y2="300" stroke="#666"/>'
        '<text x="500" y="304" text-anchor="middle" font-size="16">Straddled</text>'
    )
    true("CONNECTOR_CROSSES_TEXT" in craft_codes(doc), "missed a real crossing")


@case("craft: a line running parallel just above a label misses it")
def _() -> None:
    doc = svg(
        '<line x1="100" y1="200" x2="900" y2="200" stroke="#666"/>'
        '<text x="500" y="304" text-anchor="middle" font-size="16">Below the line</text>'
    )
    true("CONNECTOR_CROSSES_TEXT" not in craft_codes(doc), "parallel line false positive")


@case("craft: tiny fonts are reported")
def _() -> None:
    doc = svg(
        card(60, 100, 200, "Fine")
        + '<text x="400" y="300" text-anchor="middle" font-size="9">Too small</text>'
    )
    true("TINY_FONT" in craft_codes(doc), "expected TINY_FONT")


@case("craft: a full-width line is LONG_LINE, a short one is not")
def _() -> None:
    # Measured, not eyeballed. This line is 721px at 16px, past the 600px limit on
    # a 1000px canvas; the 85-character version of it is 590px and correctly does
    # NOT fire, despite being longer than any sane character cap. That gap is the
    # whole reason this rule counts pixels instead of characters.
    long_text = (
        "This sentence is stretched clear across the entire visible width of the "
        "diagram frame, well past the limit"
    )
    doc = svg(
        card(60, 100, 300, "Fine")
        + f'<text x="500" y="600" text-anchor="middle" font-size="16">{long_text}</text>'
    )
    true("LONG_LINE" in craft_codes(doc), "expected LONG_LINE")
    short = svg(card(60, 100, 300, "Fine") + card(400, 100, 300, "Also fine"))
    true("LONG_LINE" not in craft_codes(short), "LONG_LINE on a short label")


@case("craft: the palette check counts painted fills only")
def _() -> None:
    mono = svg(card(60, 100, 200, "A") + card(300, 100, 200, "B"))
    true("PALETTE_MONOTONY" in craft_codes(mono), "expected PALETTE_MONOTONY")
    rich = svg(
        '<rect x="0" y="0" width="1000" height="700" fill="#f8f9fa"/>'
        + card(60, 100, 200, "A")
        + '<rect x="300" y="100" width="200" height="60" fill="#50C878"/>'
        '<text x="400" y="134" text-anchor="middle" font-size="16">B</text>'
        '<rect x="600" y="100" width="200" height="60" fill="#FF6B6B"/>'
        '<text x="700" y="134" text-anchor="middle" font-size="16">C</text>'
    )
    true("PALETTE_MONOTONY" not in craft_codes(rich), "false positive on 4 fills")


@case("craft: malformed input yields no craft findings, not a crash")
def _() -> None:
    eq(craft_codes("<svg><rect"), [], "craft findings on unparseable input")


@case("craft: findings cite rule IDs that exist in the spec")
def _() -> None:
    spec_path = Path(__file__).resolve().parent / "prompts" / "svg_design_spec.md"
    if not spec_path.exists():
        raise Pending("prompts/svg_design_spec.md does not exist yet")
    spec = spec_path.read_text(encoding="utf-8")
    doc = svg(card(100, 100, 120, "Twenty-eight characters here"))
    rules = {f.rule_id for f in G.craft_findings(doc)}
    rules |= {f.rule_id for f in G.detect_overlaps(doc).findings}
    true(bool(rules), "no rules cited at all")
    for rule in sorted(rules):
        true(rule in spec, f"{rule} is cited by a finding but absent from the spec")


@case("craft: every spec rule ID is reachable from code")
def _() -> None:
    # The other direction: a rule in the spec with no constant behind it cannot be
    # cited, so a finding could never point at it. That is how "<= 20 characters"
    # survived 208 violations.
    spec_path = Path(__file__).resolve().parent / "prompts" / "svg_design_spec.md"
    if not spec_path.exists():
        raise Pending("prompts/svg_design_spec.md does not exist yet")
    spec = spec_path.read_text(encoding="utf-8")
    declared = {v for k, v in vars(G).items() if k.startswith("SD_") and isinstance(v, str)}
    documented = set(re.findall(r"\bSD-[A-Z-]+\b", spec))
    missing = sorted(documented - declared - {"SD-GROUNDING"})
    eq(missing, [], "spec rules with no constant in svg_geometry")


@case("corpus: craft finding counts hold")
def _() -> None:
    counts: dict[str, int] = {}
    fresh_counts: dict[str, int] = {}
    for _, _, block in corpus():
        for f in G.craft_findings(block):
            counts[f.code] = counts.get(f.code, 0) + 1
        for f in G.craft_findings(fresh_canvas(block)):
            fresh_counts[f.code] = fresh_counts.get(f.code, 0) + 1
    for code, want in TARGET_CRAFT.items():
        eq(counts.get(code, 0), want, f"craft {code} instances")
    for code, want in TARGET_CRAFT_FRESH.items():
        eq(fresh_counts.get(code, 0), want, f"craft {code} instances (fresh canvas)")


@case("corpus: only TEXT_OVERFLOWS_RECT is a hard craft finding")
def _() -> None:
    # A false HARD finding costs a full generate+review cycle and corrupts the
    # retry loop's ranking, so promotion past the 90%-precision bar is deliberate
    # and this pins which codes have cleared it.
    hard_codes = set()
    for _, _, block in corpus():
        for f in G.craft_findings(block):
            if f.severity == G.HARD:
                hard_codes.add(f.code)
    eq(sorted(hard_codes), ["TEXT_OVERFLOWS_RECT"], "hard craft codes")


@case("corpus: the canvas advisories collapse on a correct canvas")
def _() -> None:
    # Evidence that LOW_CANVAS_FILL and OFF_CENTER measured the old autofit bug
    # rather than the drawings: 47 -> 1 and 4 -> 2 once the declared canvas is the
    # one the prompt asks for. This is why they are advisory tripwires, not gates.
    as_is = fresh = 0
    for _, _, block in corpus():
        as_is += sum(1 for f in G.craft_findings(block) if f.code == "LOW_CANVAS_FILL")
        fresh += sum(
            1 for f in G.craft_findings(fresh_canvas(block)) if f.code == "LOW_CANVAS_FILL"
        )
    true(as_is >= 40, f"expected the archive to look empty, got {as_is}")
    true(fresh <= 3, f"fresh canvases should fill the frame, got {fresh}")


# ---------------------------------------------------------------------------
# Checked-in fixtures — these run everywhere, corpus or not
# ---------------------------------------------------------------------------


@case("fixture: every checked-in fixture parses and is real generated output")
def _() -> None:
    for name in FIXTURES:
        block = fixture(name)
        report = G.detect_overlaps(block)
        true(report.gate_ran, f"{name} did not parse: {report.error}")
        geo = G.element_boxes(block)
        true(len(geo.texts) >= 2, f"{name} has {len(geo.texts)} text lines")


@case("fixture: the 3245px canvas refits sanely")
def _() -> None:
    fitted, _ = G.autofit_viewbox(fresh_canvas(fixture("oversized-canvas.svg")))
    x, y, w, h = view_box_of(fitted)
    true(w <= 1200, f"refit width {w:.0f}, want <= 1200")
    true(x >= -60, f"refit origin x {x:.0f}, want >= -60")


@case("fixture: a multi-tspan block keeps its declared canvas byte-identical")
def _() -> None:
    # The central bug: a 5-line centred caption used to be measured as one box
    # five line-widths wide, which is what inflated the canvas.
    for name in ("label-wider-than-box.svg", "all-rects.svg"):
        block = fresh_canvas(fixture(name))
        fitted, findings = G.autofit_viewbox(block)
        eq(fitted, block, f"{name} canvas was rewritten")
        eq(findings, [], f"{name} produced autofit findings")


@case("fixture: labels wider than their boxes are found")
def _() -> None:
    for name in ("label-wider-than-box.svg", "label-overflow-panel.svg"):
        codes_seen = [f.code for f in G.craft_findings(fixture(name))]
        true("TEXT_OVERFLOWS_RECT" in codes_seen, f"{name}: no fit finding")


@case("fixture: an all-rect diagram is flagged, and only advisorily")
def _() -> None:
    findings = G.craft_findings(fixture("all-rects.svg"))
    monotony = [f for f in findings if f.code == "SHAPE_MONOTONY"]
    eq(len(monotony), 1, "SHAPE_MONOTONY count")
    eq(monotony[0].severity, G.ADVISORY, "SHAPE_MONOTONY severity")
    eq(monotony[0].rule_id, G.SD_TYPE, "SHAPE_MONOTONY rule")


@case("fixture: connector geometry stays inside the fitted canvas")
def _() -> None:
    block = fixture("connector-bounds.svg")
    fitted, _ = G.autofit_viewbox(block)
    x, y, w, h = view_box_of(fitted)
    geo = G.element_boxes(block)
    for c in geo.connectors:
        if c.uncertain:
            continue
        true(c.box.x1 >= x - 1, f"connector {c.box} clipped left of {x:.0f}")
        true(c.box.x2 <= x + w + 1, f"connector {c.box} clipped right of {x + w:.0f}")


@case("fixture: findings are deterministic across repeated runs")
def _() -> None:
    for name in FIXTURES:
        block = fixture(name)
        first = [str(f) for f in G.detect_overlaps(block).findings]
        first += [str(f) for f in G.craft_findings(block)]
        for _ in range(2):
            again = [str(f) for f in G.detect_overlaps(block).findings]
            again += [str(f) for f in G.craft_findings(block)]
            eq(again, first, f"{name} findings differ between runs")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run(filters: list[str]) -> int:
    selected = [
        (name, fn, xf)
        for name, fn, xf in CASES
        if not filters or any(f.lower() in name.lower() for f in filters)
    ]

    passed = failed = skipped = xfailed = xpassed = pending = 0
    failures: list[tuple[str, str]] = []
    skips: list[tuple[str, str]] = []

    for name, fn, xf in selected:
        try:
            fn()
        except Pending as exc:
            pending += 1
            print(f"  pend  {name}  ({exc})")
            continue
        except Skip as exc:
            skipped += 1
            skips.append((name, str(exc)))
            print(f"  SKIP  {name}  ({exc})")
            continue
        except AssertionError as exc:
            if xf:
                xfailed += 1
                print(f"  xfail {name}  ({exc})")
            else:
                failed += 1
                failures.append((name, str(exc)))
                print(f"  FAIL  {name}\n        {exc}")
            continue
        except Exception:
            detail = traceback.format_exc(limit=3).strip().splitlines()[-1]
            if xf:
                xfailed += 1
                print(f"  xfail {name}  ({detail})")
            else:
                failed += 1
                failures.append((name, detail))
                print(f"  ERROR {name}\n        {detail}")
            continue

        if xf:
            xpassed += 1
            print(f"  XPASS {name}  <- fixed; drop the xfail marker")
        else:
            passed += 1
            print(f"  ok    {name}")

    print(
        f"\n{passed} passed, {failed} failed, {xfailed} xfail, "
        f"{xpassed} xpass, {pending} pending, {skipped} skipped"
    )

    if skips:
        print(
            "\n!! CORPUS_SKIPPED — regression cases did not run. A skip is not a pass.\n"
            f"   Set SVG_CORPUS_ROOT to a directory of generated .mlai files "
            f"(tried {CORPUS_ROOT})."
        )
    if xpassed:
        print(
            f"\n{xpassed} case(s) now pass that were marked xfail. "
            "Remove the marker so the behaviour stays locked in."
        )
    if failures:
        print("\nFailures:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, _, xf in CASES:
            print(f"{'xfail' if xf else '     '} {name}")
        return 0
    return run([a for a in argv if not a.startswith("-")])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
