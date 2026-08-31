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
    # ADVISORY. 7 instances in 5 of 150 blocks — the pairs where a shape covers a
    # contiguous run at a label's extremity while covering too little of its *area*
    # for TEXT_SPILL's 0.25 threshold to see it. The rule exists because a centred
    # band label with a glyph at each end read as "ll Membrane — ion channels clos"
    # at a share of 0.061. Note what END_CLIP_INK_FLOOR buys: the end-clip geometry
    # alone fires 9 times here, 7 of them one latch diagram's labels beside curved
    # <ellipse> shapes whose bounding boxes overlap while their ink does not.
    # Requiring real ink is what keeps this at 7 rather than 16.
    "TEXT_END_CLIPPED": 7,
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
    # 98% of the archive. This is the baseline the SD-DEPTH work exists to move,
    # recorded as a number so "the diagrams look richer now" can be checked rather
    # than believed: not one of 150 shipped diagrams has a single gradient fill.
    "FLAT_FILL_ONLY": 147,
    "CONNECTOR_CROSSES_TEXT": 44,
    "STUBBY_ARROW": 16,
    "TEXT_DOMINANCE": 6,
    "TINY_FONT": 5,
    "TEXT_OVERFLOWS_RECT": 4,      # HARD; all 4 confirmed by rendering
    # Zero, and asserted for the same reason NON_ARIAL_FONT is: the rule fires on
    # fresh output (the probe's third diagram had no namespace) and has no false
    # positives on 150 real ones.
    "MISSING_XMLNS": 0,
    # SD-STRUCTURE, measured 2026-08-26 on the same 150 blocks.
    #
    # 150/150 is the expected number, not a defect in the rule: the archive
    # predates SD-STRUCTURE, so no diagram in it has ever declared an archetype.
    # This is spec-compliance telemetry in the same sense as MISSING_TEXT_ANCHOR's
    # 223 — the number to watch is whether FRESH output declares one. If a real
    # generation still logs ARCHETYPE_NOT_DECLARED after the spec landed, the
    # prompt did not take and the rule should be demoted rather than retried
    # against (it is HARD, so a systematic miss costs all 4 attempts per diagram).
    "ARCHETYPE_NOT_DECLARED": 150,
    "ARCHETYPE_UNKNOWN": 0,
    # 12 runs across 6 of 150 blocks (4%). The low incidence is the useful part:
    # in-diagram prose is NOT a corpus norm this has to tolerate, it is a defect
    # the raised-card idiom introduced. ~9 of the 12 are genuinely prose.
    "PROSE_BLOCK": 6,
    # 91% of the archive. Fires almost everywhere today, so it carries little
    # discriminating information and is honestly a regression tripwire, in the same
    # standing as LOW_CANVAS_FILL. Watch it fall, not its absolute value.
    "LABEL_TOO_WORDY": 136,
    # Zero, and that is exactly what FLAT_FILL_ONLY's 147 predicts: the archive has
    # no gradients at all, so it cannot have stroked one. The rule is here to guard
    # the diagrams SD-DEPTH now asks for — the first three generated under it
    # already contained one, and it made half of a two-curve comparison invisible.
    "GRADIENT_STROKE_INVISIBLE": 0,
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
# TEXT_END_CLIPPED — words lost at a label's extremity
# ---------------------------------------------------------------------------

# The exact shape that provoked the rule: a centred band label with a glyph
# sitting at each end. The label box is (380,290)-(620,303), so 240px over 35
# characters — ~6.8px per character, and the 14px circles bury two of them.
CLIP_LABEL = "Cell Membrane — ion channels closed"
CLIP_TEXT = f'<text x="500" y="300" font-size="14" text-anchor="middle">{CLIP_LABEL}</text>'


@case("end-clip: a glyph over a label's end is flagged although TEXT_SPILL cannot see it")
def _() -> None:
    # Measured on the real diagram, not reasoned: the covered ink is 8.7% of the
    # label's area against DEFAULT_TEXT_SPILL = 0.25, so the gate reported clean
    # while the student read "ll Membrane — ion channels clos". Area share is the
    # wrong instrument; where the cover sits is the whole defect.
    for side, cx in (("left", 388), ("right", 612)):
        doc = svg(CLIP_TEXT + f'<circle cx="{cx}" cy="300" r="14" fill="#4a90d9"/>')
        report = G.detect_overlaps(doc)
        eq(codes(report), ["TEXT_END_CLIPPED"], f"a glyph on the {side} end")
        finding = report.findings[0]
        eq(finding.severity, G.ADVISORY, "advisory until the corpus can settle it")
        eq(finding.rule_id, G.SD_SPACING, "rule cited")
        true(side in finding.message, f"the message must name the {side} end: {finding.message}")
    true(not report.has_hard, "an advisory finding must not fail the diagram")


@case("end-clip: a shape biting the MIDDLE of a label is not an end clip")
def _() -> None:
    # Not rejected by the ink floor — this one covers 10.7% of the label, MORE
    # than the true left/right cases above. It is rejected because the covered
    # run is nowhere near an extremity, which is the only thing this rule is
    # about. A mid-label collision is TEXT_SPILL's business, at its own
    # threshold.
    doc = svg(CLIP_TEXT + '<circle cx="500" cy="300" r="14" fill="#4a90d9"/>')
    report = G.detect_overlaps(doc)
    eq(codes(report), [], "a middle bite is a different defect")


@case("end-clip: a sub-character graze at the end is a hairline, not a lost word")
def _() -> None:
    # END_CLIP_MIN_CHARS in isolation. Label box (462,288)-(538,304): 76px over
    # 8 characters, so one character is 9.56px. Both fixtures clear the ink floor
    # (9.8% and 12.0%), so the ONLY difference is whether a whole character is
    # buried — which is the difference between an ugly touch and a missing word.
    text = '<text x="500" y="300" font-size="16" text-anchor="middle">Membrane</text>'
    graze = svg(text + '<rect x="529.6" y="290" width="60" height="20" fill="#4a90d9"/>')
    eq(codes(G.detect_overlaps(graze)), [], "0.9 of a character must stay silent")
    whole = svg(text + '<rect x="527.7" y="290" width="60" height="20" fill="#4a90d9"/>')
    eq(codes(G.detect_overlaps(whole)), ["TEXT_END_CLIPPED"], "1.1 characters is a word")


@case("end-clip: a curved shape whose BOX overlaps but whose ink does not")
def _() -> None:
    # The false-positive cluster that decided END_CLIP_INK_FLOOR, and the reason
    # this case does not merely assert silence: the end-clip *geometry* passes
    # here (15px of box overlap at the label's left edge, over two characters
    # wide), so `_end_clipped` is asked with a forged share to prove the ink
    # floor is what rejects it. Seven of the nine corpus instances are this
    # shape — one latch diagram's labels beside <ellipse> outlines, ink shares
    # 0.000-0.048. Same curved-hull artifact that made TEXT_OVERFLOWS_RECT 50%
    # precise until it was restated (rule 25).
    doc = svg(CLIP_TEXT + '<ellipse cx="350" cy="240" rx="45" ry="70" fill="none" stroke="#333"/>')
    eq(codes(G.detect_overlaps(doc)), [], "a curve's bounding box is not its ink")
    geo = G.element_boxes(doc)
    t, s = geo.texts[0], geo.shapes[0]
    real = G.region_overlap_area(t, s) / max(1.0, t.box.area)
    true(real < G.END_CLIP_INK_FLOOR, f"the ink share must be below the floor, got {real:.3f}")
    true(
        G._end_clipped(t, s, G.END_CLIP_INK_FLOOR + 0.01),
        "the geometry alone accepts this pair — only the ink floor rejects it, so "
        "the floor is load-bearing rather than decorative",
    )


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


# ---------------------------------------------------------------------------
# SD-DEPTH — gradients, elevation, namespace
# ---------------------------------------------------------------------------

GRADS = (
    "<defs>"
    '<linearGradient id="gPrimary" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#5b8fc7"/><stop offset="1" stop-color="#3d6b99"/>'
    "</linearGradient>"
    '<radialGradient id="gSheen" cx="0.5" cy="0.3" r="0.75">'
    '<stop offset="0" stop-color="#ffffff" stop-opacity="0.45"/>'
    '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
    "</radialGradient>"
    "</defs>"
)


def toned_card(x: float, y: float, w: float, label: str) -> str:
    """The spec's three-rect raised card: shadow, gradient fill, sheen."""
    return (
        f'<rect x="{x}" y="{y + 6}" width="{w}" height="60" rx="14" fill="#22303f" opacity="0.10"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="60" rx="14" fill="url(#gPrimary)"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="60" rx="14" fill="url(#gSheen)"/>'
        f'<text x="{x + w / 2}" y="{y + 34}" text-anchor="middle" font-size="16">{label}</text>'
    )


def palette(svg_text: str) -> set[str]:
    if not hasattr(G, "_fill_palette"):
        raise Pending("svg_geometry has no _fill_palette() yet")
    return G._fill_palette(svg_text)


@case("depth: a gradient fill resolves to its stop colours")
def _() -> None:
    # The whole point of the change. Before this, `url(...)` was skipped outright,
    # so a toned diagram counted 0-2 fills.
    doc = svg(GRADS + '<rect x="60" y="100" width="200" height="60" fill="url(#gPrimary)"/>')
    eq(palette(doc), {"#5b8fc7", "#3d6b99"}, "resolved gradient stops")


@case("depth: a gradient id is matched case-sensitively")
def _() -> None:
    # SVG ids are case-sensitive, so lowercasing the fill value before looking the
    # id up would resolve `url(#gPrimary)` against a gradient named `gprimary`.
    # Self-caught before it ran; pinned so it cannot come back.
    wrong = svg(
        '<defs><linearGradient id="gprimary"><stop stop-color="#111111"/>'
        "</linearGradient></defs>"
        '<rect x="60" y="100" width="200" height="60" fill="url(#gPrimary)"/>'
    )
    eq(palette(wrong), set(), "matched a differently-cased id")
    right = svg(
        '<defs><linearGradient id="gPrimary"><stop stop-color="#111111"/>'
        "</linearGradient></defs>"
        '<rect x="60" y="100" width="200" height="60" fill="url(#gPrimary)"/>'
    )
    eq(palette(right), {"#111111"}, "missed an exactly-cased id")


@case("depth: a gradient inherits stops through href")
def _() -> None:
    # `<linearGradient id="b" href="#a"/>` is the idiom for "same ramp, other
    # direction". Both spellings, and both forms — with a body and self-closing,
    # because the definition regex only sees the first.
    for href in ('href="#a"', 'xlink:href="#a"'):
        doc = svg(
            '<defs><linearGradient id="a"><stop stop-color="#aabbcc"/>'
            "<stop stop-color=\"#112233\"/></linearGradient>"
            f'<linearGradient id="b" x1="0" y1="0" x2="1" y2="0" {href}/></defs>'
            '<rect x="60" y="100" width="200" height="60" fill="url(#b)"/>'
        )
        eq(palette(doc), {"#aabbcc", "#112233"}, f"inherited stops via {href}")


@case("depth: a fill referencing an undefined gradient contributes nothing")
def _() -> None:
    # Not a colour we can invent. A typo'd or pattern reference is unknown paint,
    # and guessing at it would be worse than counting nothing.
    doc = svg('<rect x="60" y="100" width="200" height="60" fill="url(#nope)"/>')
    eq(palette(doc), set(), "invented a colour for an undefined reference")


@case("depth: a toned diagram is NOT PALETTE_MONOTONY")
def _() -> None:
    # Rule 24's trap, pre-empted. PALETTE_MONOTONY reaches the LLM reviewer as a
    # "measured fact" and is scored under CRAFT — so a palette check that cannot
    # see through `url(#g)` would make the cheap check tell the expensive judge to
    # mark down the exact tonal work the spec now demands.
    body = GRADS + "".join(toned_card(60 + 220 * i, 100, 180, f"Step {i}") for i in range(4))
    seen = craft_codes(svg(body))
    true("PALETTE_MONOTONY" not in seen, f"flagged a gradient-toned diagram: {seen}")


@case("depth: flat fills on 4+ shapes are FLAT_FILL_ONLY, advisory")
def _() -> None:
    body = "".join(card(60 + 220 * i, 100, 180, f"Step {i}") for i in range(4))
    doc = svg(body)
    true("FLAT_FILL_ONLY" in craft_codes(doc), "expected FLAT_FILL_ONLY")
    eq(craft_severity(doc, "FLAT_FILL_ONLY"), G.ADVISORY, "FLAT_FILL_ONLY severity")
    for f in G.craft_findings(doc):
        if f.code == "FLAT_FILL_ONLY":
            eq(f.rule_id, G.SD_DEPTH, "FLAT_FILL_ONLY rule")


@case("depth: one gradient fill clears FLAT_FILL_ONLY")
def _() -> None:
    body = (
        GRADS
        + toned_card(60, 100, 180, "Toned")
        + "".join(card(300 + 220 * i, 100, 180, f"Step {i}") for i in range(3))
    )
    true("FLAT_FILL_ONLY" not in craft_codes(svg(body)), "flagged a diagram with a gradient")


@case("depth: a three-shape diagram needs no tonal work")
def _() -> None:
    # Below FLAT_FILL_MIN_SHAPES. A three-box comparison is legitimately flat, and
    # firing here would make the advisory noise on the simplest correct diagrams.
    body = "".join(card(60 + 220 * i, 100, 180, f"Step {i}") for i in range(3))
    true("FLAT_FILL_ONLY" not in craft_codes(svg(body)), "flagged a 3-shape diagram")


@case("depth: a missing xmlns is reported, a present one is not")
def _() -> None:
    # `svg()` always writes the namespace, so this one builds the root by hand.
    body = "".join(card(60 + 220 * i, 100, 180, f"Step {i}") for i in range(4))
    bare = f'<svg viewBox="0 0 1000 700" font-family="Arial, sans-serif">{body}</svg>'
    true("MISSING_XMLNS" in craft_codes(bare), "missed a document with no namespace")
    true("MISSING_XMLNS" not in craft_codes(svg(body)), "flagged a namespaced document")


@case("depth: a namespace on an inner node does not make the document standalone")
def _() -> None:
    body = '<g xmlns="http://www.w3.org/2000/svg">' + card(60, 100, 180, "Inner") + "</g>"
    bare = f'<svg viewBox="0 0 1000 700" font-family="Arial, sans-serif">{body}</svg>'
    true("MISSING_XMLNS" in craft_codes(bare), "an inner xmlns satisfied the root check")


# ---------------------------------------------------------------------------
# SD-SPACING — stubby arrows
# ---------------------------------------------------------------------------


@case("craft: a 30px arrow at stroke-width 3 is STUBBY_ARROW")
def _() -> None:
    # The probe diagram's actual defect. It was first written up as "two floating
    # arrowheads with no connector line" from looking at the render; the source says
    # they are real 30px lines at stroke-width 3, so a zero-length rule would never
    # have fired. Rule 25: measure the thing.
    doc = svg(
        card(60, 100, 180, "A")
        + '<line x1="400" y1="300" x2="430" y2="300" stroke="#3d6b99" stroke-width="3" '
        'marker-end="url(#arrow)"/>'
    )
    true("STUBBY_ARROW" in craft_codes(doc), "expected STUBBY_ARROW")
    eq(craft_severity(doc, "STUBBY_ARROW"), G.ADVISORY, "STUBBY_ARROW severity")


@case("craft: a full-length arrow is not stubby")
def _() -> None:
    doc = svg(
        card(60, 100, 180, "A")
        + '<line x1="300" y1="300" x2="700" y2="300" stroke="#3d6b99" stroke-width="3" '
        'marker-end="url(#arrow)"/>'
    )
    true("STUBBY_ARROW" not in craft_codes(doc), "flagged a 400px arrow")


@case("craft: the ratio is against the line's own stroke-width")
def _() -> None:
    # Scale-invariant on purpose: the default markerUnits="strokeWidth" grows the
    # head with the stroke, so what matters is length/stroke-width, not px. A 20px
    # hairline is a fine short connector; the same 20px at stroke-width 6 is a head.
    hairline = '<line x1="300" y1="300" x2="320" y2="300" stroke="#666" marker-end="url(#a)"/>'
    fat = (
        '<line x1="300" y1="300" x2="320" y2="300" stroke="#666" stroke-width="6" '
        'marker-end="url(#a)"/>'
    )
    base = card(60, 100, 180, "A")
    true("STUBBY_ARROW" not in craft_codes(svg(base + hairline)), "flagged a 20px hairline")
    true("STUBBY_ARROW" in craft_codes(svg(base + fat)), "missed 20px at stroke-width 6")


@case("craft: a short line with no marker is not an arrow at all")
def _() -> None:
    doc = svg(
        card(60, 100, 180, "A")
        + '<line x1="400" y1="300" x2="430" y2="300" stroke="#666" stroke-width="3"/>'
    )
    true("STUBBY_ARROW" not in craft_codes(doc), "flagged a markerless tick")


# ---------------------------------------------------------------------------
# SD-MOTION
# ---------------------------------------------------------------------------


def motion_codes(svg_text: str) -> list[str]:
    if not hasattr(G, "motion_findings"):
        raise Pending("svg_geometry has no motion_findings() yet")
    return [f.code for f in G.motion_findings(svg_text)]


REVEAL = (
    '<g opacity="0">'
    '<animate attributeName="opacity" values="0;1" dur="0.5s" begin="{begin}"{freeze}/>'
    '<rect x="{x}" y="100" width="180" height="60" rx="14" fill="#3d6b99"/>'
    "</g>"
)


@case("motion: a document with no SMIL has no motion findings")
def _() -> None:
    # ...as long as it is small enough that there is nothing to stage. A *big*
    # static diagram is NO_BUILD_UP, below.
    eq(motion_codes(svg(card(60, 100, 180, "Static"))), [], "findings on a static document")


@case("motion: a large diagram with no build-up is flagged")
def _() -> None:
    # The gap this closes: `motion_findings` used to return [] the moment there was
    # no SMIL, so a wholly static diagram was the one case it could say nothing
    # about — and the spec's build-up idiom was enforced by nothing (rule 26).
    # Measured regression that prompted it: the three diagrams generated right
    # after SD-STRUCTURE landed carried 3, 1 and 5 animations against 9, 8 and 9
    # before it, and every gate was silent.
    doc = svg("".join(f'<rect x="{60 + i * 90}" y="120" width="80" height="60" fill="#3d6b99"/>'
                      for i in range(8)))
    found = [f for f in G.motion_findings(doc) if f.code == "NO_BUILD_UP"]
    eq(len(found), 1, "a static 8-shape diagram was not flagged")
    eq(found[0].severity, G.ADVISORY, "NO_BUILD_UP severity")
    eq(found[0].rule_id, G.SD_MOTION, "NO_BUILD_UP rule")


@case("motion: three staged reveals clear the floor")
def _() -> None:
    # The satisfiable direction. A gate that cannot be met is as bad as one that
    # never fires, and this one has to be reachable with the spec's own idiom.
    body = "".join(REVEAL.format(begin=f"{0.4 * i:.1f}s", freeze=' fill="freeze"', x=60 + i * 200)
                   for i in range(3))
    eq(motion_codes(svg(body)), [], f"a 3-step build-up was flagged: {motion_codes(svg(body))}")


@case("motion: an ambient loop is not a build step")
def _() -> None:
    # `repeatCount="indefinite"` is emphasis, not sequencing — the spec allows
    # exactly one per diagram. Counting it toward the floor would let a single
    # pulsing dot satisfy "builds itself in teaching order".
    pulse = ('<circle cx="600" cy="300" r="10" fill="#c1453b">'
             '<animate attributeName="r" values="10;14;10" dur="2.2s" begin="0s" '
             'repeatCount="indefinite"/></circle>')
    doc = svg(pulse + "".join(
        f'<rect x="{60 + i * 90}" y="120" width="80" height="60" fill="#3d6b99"/>' for i in range(8)))
    true("NO_BUILD_UP" in motion_codes(doc), "an ambient pulse satisfied the build-up floor")


@case("motion: a frozen reveal is clean")
def _() -> None:
    doc = svg(REVEAL.format(begin="0.8s", freeze=' fill="freeze"', x=60))
    eq(motion_codes(doc), [], "flagged a correct reveal")


@case("motion: a reveal with no freeze is HARD")
def _() -> None:
    # The one hard motion rule, and hard for SD-ANCHOR's reason: not that it looks
    # wrong, but that it provably does not render. SMIL reverts to the start value
    # when the animation ends, so an opacity-0 reveal animates in and then vanishes
    # permanently.
    doc = svg(REVEAL.format(begin="0.8s", freeze="", x=60))
    codes_seen = motion_codes(doc)
    true("REVEAL_WITHOUT_FREEZE" in codes_seen, f"missed a stranded reveal: {codes_seen}")
    found = [f for f in G.motion_findings(doc) if f.code == "REVEAL_WITHOUT_FREEZE"]
    eq(found[0].severity, G.HARD, "REVEAL_WITHOUT_FREEZE severity")
    eq(found[0].rule_id, G.SD_MOTION, "REVEAL_WITHOUT_FREEZE rule")


@case("motion: the start state can come from the parent, not the values list")
def _() -> None:
    # `<g opacity="0"><animate attributeName="opacity" .../></g>` with no `values`
    # is still a reveal — the hidden start state is on the parent.
    doc = svg(
        '<g opacity="0"><animate attributeName="opacity" dur="0.5s" begin="0.8s"/>'
        '<rect x="60" y="100" width="180" height="60" fill="#3d6b99"/></g>'
    )
    true("REVEAL_WITHOUT_FREEZE" in motion_codes(doc), "missed a parent-hidden reveal")


@case("motion: an indefinite loop needs no freeze")
def _() -> None:
    # It never ends, so it never reverts. The ambient pulse the spec allows.
    doc = svg(
        '<circle cx="600" cy="300" r="10" fill="#c1453b">'
        '<animate attributeName="opacity" values="0;1;0" dur="2.2s" begin="0s" '
        'repeatCount="indefinite"/></circle>'
    )
    eq(motion_codes(doc), [], "flagged an ambient loop")


@case("motion: a non-opacity animation is not a reveal")
def _() -> None:
    # `values="0;1"` on `r` starts small, not absent — dropping the freeze there is
    # a design choice, not a disappearing element. Only the opacity family strands.
    doc = svg(
        '<circle cx="600" cy="300" r="0" fill="#c1453b">'
        '<animate attributeName="r" values="0;12" dur="0.6s" begin="0.4s"/></circle>'
    )
    true("REVEAL_WITHOUT_FREEZE" not in motion_codes(doc), "treated an r animation as a reveal")


@case("motion: a build past 4s is SLOW_REVEAL, advisory")
def _() -> None:
    doc = svg(
        REVEAL.format(begin="0.4s", freeze=' fill="freeze"', x=60)
        + REVEAL.format(begin="4.2s", freeze=' fill="freeze"', x=300)
    )
    codes_seen = motion_codes(doc)
    true("SLOW_REVEAL" in codes_seen, f"missed a slow build: {codes_seen}")
    found = [f for f in G.motion_findings(doc) if f.code == "SLOW_REVEAL"]
    eq(found[0].severity, G.ADVISORY, "SLOW_REVEAL severity")
    true("4.7" in found[0].message, f"end time not reported: {found[0].message}")


@case("motion: a build inside the budget is not flagged")
def _() -> None:
    doc = svg(
        REVEAL.format(begin="0.4s", freeze=' fill="freeze"', x=60)
        + REVEAL.format(begin="2.8s", freeze=' fill="freeze"', x=300)
    )
    eq(motion_codes(doc), [], "flagged a 3.3s build")


@case("motion: an indefinite loop does not count toward the build time")
def _() -> None:
    # A 2.2s pulse beginning at 3s ends at 5.2s on paper, but it never ends — the
    # diagram was fully assembled at 0.9s. Counting it would report every animated
    # diagram as slow.
    doc = svg(
        REVEAL.format(begin="0.4s", freeze=' fill="freeze"', x=60)
        + '<circle cx="600" cy="300" r="10" fill="#c1453b">'
        '<animate attributeName="r" values="10;14;10" dur="2.2s" begin="3s" '
        'repeatCount="indefinite"/></circle>'
    )
    eq(motion_codes(doc), [], "an ambient loop counted as build time")


@case("motion: the clock parser reads offsets and refuses everything else")
def _() -> None:
    if not hasattr(G, "_clock_seconds"):
        raise Pending("svg_geometry has no _clock_seconds() yet")
    eq(G._clock_seconds("0s"), 0.0, "0s")
    eq(G._clock_seconds("1.5s"), 1.5, "a decimal must not be mistaken for a syncbase")
    eq(G._clock_seconds("900ms"), 0.9, "milliseconds")
    eq(G._clock_seconds("0.4"), 0.4, "a bare number is seconds")
    # The six non-offset forms of SMIL's `begin`. None of them can be placed on a
    # timeline here, and the parser gate rejects them outright — but a checker that
    # half-parsed "00:03" as 0 would call a 3-second reveal instant.
    for raw in ("a.end+2s", "btn.click", "l.repeat(2)", "accessKey(s)", "indefinite", "00:03"):
        eq(G._clock_seconds(raw), None, f"accepted {raw!r} as an offset")


@case("motion: SMIL nested two groups deep is still found")
def _() -> None:
    doc = svg(
        '<g transform="translate(20,20)"><g opacity="0">'
        '<animate attributeName="opacity" values="0;1" dur="0.5s" begin="0.8s"/>'
        '<rect x="60" y="100" width="180" height="60" fill="#3d6b99"/></g></g>'
    )
    true("REVEAL_WITHOUT_FREEZE" in motion_codes(doc), "missed a nested reveal")


@case("motion: malformed input yields no motion findings, not a crash")
def _() -> None:
    eq(motion_codes("<svg><animate"), [], "motion findings on unparseable input")


@case("motion: SMIL elements draw nothing and do not move the bounds")
def _() -> None:
    # `animateMotion`'s `path` attribute is the sharp case: it carries a `d`-shaped
    # value that is a trajectory, not a stroke. Descending into it would add
    # phantom geometry — and `path` is not even a geometry attribute of the parent.
    plain = svg('<rect x="60" y="100" width="180" height="60" fill="#3d6b99"/>')
    animated = svg(
        '<rect x="60" y="100" width="180" height="60" fill="#3d6b99">'
        '<animateMotion path="M 0 0 L 900 600" dur="2s" begin="0s" fill="freeze"/>'
        "</rect>"
    )
    before = G.element_boxes(plain)
    after = G.element_boxes(animated)
    eq(len(after.connectors), 0, "the animateMotion trajectory was measured as a stroke")
    eq(
        [s.box.as_tuple() for s in after.shapes],
        [s.box.as_tuple() for s in before.shapes],
        "an animateMotion child changed its parent's measured box",
    )


def staged_share(svg_text: str) -> tuple[int, int]:
    if not hasattr(G, "staged_ink"):
        raise Pending("svg_geometry has no staged_ink() yet")
    return G.staged_ink(svg_text)


# One teaching step done the way the spec asks: the shape, its label and its
# connector inside a single opacity-0 group. 3 drawn elements, all staged.
def step(i: int, begin: str) -> str:
    y = 120 + i * 90
    return (
        f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" '
        f'begin="{begin}" fill="freeze"/>'
        f'<rect x="60" y="{y}" width="200" height="60" rx="12" fill="#3d6b99"/>'
        f'<text x="160" y="{y + 34}" text-anchor="middle" font-size="15">step {i}</text>'
        f'<path d="M270 {y + 30} L420 {y + 30}" fill="none" stroke="#3d6b99"/>'
        "</g>"
    )


@case("motion: a group reveal stages its whole subtree")
def _() -> None:
    # The credit has to flow DOWN — the <g> is what carries the <animate>, but it is
    # the rect, the text and the path inside it that the learner sees appear.
    staged, total = staged_share(svg(step(0, "0.4s")))
    eq(total, 3, "the three drawn elements in one step were not all counted")
    eq(staged, 3, "a group reveal did not stage the shapes inside it")


@case("motion: a draw-on connector stages itself")
def _() -> None:
    doc = svg(
        '<path d="M120 200 L420 200" pathLength="100" fill="none" stroke="#3d6b99" '
        'stroke-dasharray="100" stroke-dashoffset="100">'
        '<animate attributeName="stroke-dashoffset" values="100;0" dur="0.8s" '
        'begin="0.3s" fill="freeze"/></path>'
    )
    eq(staged_share(doc), (1, 1), "stroke-dashoffset was not counted as staging")


@case("motion: an ambient pulse stages nothing")
def _() -> None:
    # Same shape, same <animate> tag, different intent. `r` on a loop is emphasis;
    # crediting it would let one pulsing dot claim the whole diagram is staged.
    doc = svg(
        '<circle cx="600" cy="300" r="10" fill="#c1453b">'
        '<animate attributeName="r" values="10;14;10" dur="2.2s" begin="0s" '
        'repeatCount="indefinite"/></circle>'
    )
    eq(staged_share(doc), (0, 1), "an indefinite pulse was counted as a staged reveal")


@case("motion: decoration on a complete frame is STATIC_STRUCTURE")
def _() -> None:
    # The exact shape found by rendering the real output and scrubbing the SMIL
    # timeline to t=0: eight staged reveals, and the title, both panels and the
    # footer already on screen before any of them fires. The reveal COUNT is healthy,
    # which is why a count alone could not see this.
    frame = "".join(
        f'<rect x="60" y="{60 + i * 60}" width="880" height="40" fill="#e5e9ed"/>'
        f'<text x="500" y="{88 + i * 60}" text-anchor="middle" font-size="15">panel {i}</text>'
        for i in range(6)
    )
    chips = "".join(
        f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" '
        f'begin="{0.3 + i * 0.5}s" fill="freeze"/>'
        f'<circle cx="{200 + i * 80}" cy="450" r="14" fill="#3d6b99"/></g>'
        for i in range(3)
    )
    doc = svg(frame + chips)
    staged, total = staged_share(doc)
    eq((staged, total), (3, 15), "the staged/total split is not what the fixture draws")
    codes = motion_codes(doc)
    true("STATIC_STRUCTURE" in codes, f"20% staged was not flagged: {codes}")
    true("NO_BUILD_UP" not in codes, "three reveals should clear the count floor")


@case("motion: staging the structure clears the share floor")
def _() -> None:
    # A gate that cannot be satisfied is as bad as one that never fires — and this
    # bar is one the generator has already cleared unaided (61% and 59% on two real
    # diagrams), not an aspiration.
    doc = svg(
        '<rect x="0" y="0" width="1000" height="700" fill="#f8f9fa"/>'
        '<text x="500" y="52" text-anchor="middle" font-size="22">Title</text>'
        + "".join(step(i, f"{0.3 + i * 0.5}s") for i in range(4))
    )
    staged, total = staged_share(doc)
    true(staged / total >= G.MOTION_FLOOR_STAGED_SHARE,
         f"the four-step fixture stages only {staged}/{total}")
    eq([c for c in motion_codes(doc) if c in {"STATIC_STRUCTURE", "NO_BUILD_UP"}], [],
       "a properly staged build was flagged")


@case("motion: the two build findings never fire together — the HARD one wins")
def _() -> None:
    # Retry feedback is repeated per finding, so the same complaint twice is a real
    # token cost (rule 32's fourth lesson). One animation on a large diagram trips both
    # the count and the share; only one message goes back, and it must be the hard one,
    # because that is the one the fix loop acts on (rule 24).
    doc = svg(
        "".join(f'<rect x="{60 + i * 80}" y="120" width="70" height="50" fill="#3d6b99"/>'
                for i in range(12))
        + '<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" '
          'begin="0.3s" fill="freeze"/><circle cx="500" cy="400" r="12" fill="#c1453b"/></g>'
    )
    codes = motion_codes(doc)
    true("STATIC_STRUCTURE" in codes, f"1 of 13 staged was not flagged: {codes}")
    true("NO_BUILD_UP" not in codes, "both build findings fired at once")


@case("motion: STATIC_STRUCTURE is HARD, so the fix loop sees it")
def _() -> None:
    # Your decision for this run. It matters mechanically, not just as a label:
    # `_geometry_check` in svg_agent.py routes only HARD findings into the fixable set,
    # so as ADVISORY this went to the reviewer's score and never to a retry.
    doc = svg(
        "".join(f'<rect x="{60 + i * 70}" y="{120 + (i % 3) * 90}" width="60" '
                f'height="50" fill="#3d6b99"/>' for i in range(12))
        + '<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" '
          'begin="0.3s" fill="freeze"/><circle cx="500" cy="600" r="12" fill="#c1453b"/></g>'
    )
    static = [f for f in G.motion_findings(doc) if f.code == "STATIC_STRUCTURE"]
    eq(len(static), 1, "STATIC_STRUCTURE did not fire on a 1-of-13 fixture")
    eq(static[0].severity, G.HARD, "STATIC_STRUCTURE severity")
    eq(static[0].rule_id, G.SD_MOTION, "rule id")
    # The count rule stays advisory — "cut a step" and "stage the structure" are not the
    # same instruction, and only the second is mechanically complete.
    others = [f for f in G.motion_findings(doc) if f.code == "NO_BUILD_UP"]
    true(all(f.severity == G.ADVISORY for f in others), "NO_BUILD_UP went hard too")


@case("motion: a diagram with NO animation at all is hard, not advisory")
def _() -> None:
    # The hole the severity flip opened, and the reason the suppression had to change
    # direction. Zero animations trips the count gate; under the old order that
    # suppressed the share finding, so the *worst* case would have been the one case
    # producing no hard finding at all.
    doc = svg(
        "".join(f'<rect x="{60 + i * 70}" y="{120 + (i % 3) * 90}" width="60" '
                f'height="50" fill="#3d6b99"/>' for i in range(14))
    )
    findings = G.motion_findings(doc)
    codes = [f.code for f in findings]
    true("STATIC_STRUCTURE" in codes, f"a wholly static diagram was not flagged: {codes}")
    true(any(f.severity == G.HARD for f in findings), "and it was not hard")
    eq(staged_share(doc), (0, 14), "the fixture stages nothing")


@case("motion: too small to share-check still gets the advisory count")
def _() -> None:
    # The one case the hard rule stays silent on, by design: below
    # MOTION_SHARE_MIN_DRAWN the ratio is noise. NO_BUILD_UP survives there, which is
    # why the suppression is one-directional rather than a merge of the two rules.
    doc = svg(
        "".join(f'<rect x="{60 + i * 80}" y="120" width="70" height="50" fill="#3d6b99"/>'
                for i in range(7))
    )
    staged, total = staged_share(doc)
    true(total < G.MOTION_SHARE_MIN_DRAWN, f"fixture drew {total}, wanted under the floor")
    codes = motion_codes(doc)
    true("NO_BUILD_UP" in codes, f"7 static shapes got no build finding: {codes}")
    true("STATIC_STRUCTURE" not in codes, "a 7-element diagram was share-checked")


@case("motion: a small diagram is not asked about its staged share")
def _() -> None:
    # Below MOTION_SHARE_MIN_DRAWN the ratio is noise: 2 of 6 is 33%, and there is
    # no build order to get wrong in six shapes.
    doc = svg(
        "".join(f'<rect x="{60 + i * 80}" y="120" width="70" height="50" fill="#3d6b99"/>'
                for i in range(6))
        + "".join(
            f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" '
            f'begin="{0.3 + i * 0.4}s" fill="freeze"/>'
            f'<circle cx="{300 + i * 60}" cy="400" r="12" fill="#c1453b"/></g>'
            for i in range(3)
        )
    )
    staged, total = staged_share(doc)
    true(total < G.MOTION_SHARE_MIN_DRAWN, f"fixture drew {total}, expected under the floor")
    true("STATIC_STRUCTURE" not in motion_codes(doc), "a 9-element diagram was share-checked")


@case("motion: staged_ink survives malformed input")
def _() -> None:
    eq(staged_share("<svg><g opacity=\"0\""), (0, 0), "staged_ink raised on bad XML")


@case("motion: <defs> content is not counted as drawn ink")
def _() -> None:
    # A gradient's <stop>s and a <marker>'s arrowhead <path> are definitions. Counting
    # the marker path as unstaged ink would push every diagram's share down for
    # drawing arrowheads at all.
    defs = (
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10">'
        '<path d="M0 0 L10 5 L0 10 z" fill="#3d6b99"/></marker>'
        '<linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
    )
    eq(staged_share(svg(defs + step(0, "0.3s"))), staged_share(svg(step(0, "0.3s"))),
       "<defs> content was counted as drawn ink")


@case("motion: the spec states the share the checker measures")
def _() -> None:
    # Rule 26: a number the gate enforces and the spec does not state is a rule the
    # generator cannot follow. "at least half" must survive a reword of the spec.
    spec_path = Path(__file__).resolve().parent / "prompts" / "svg_design_spec.md"
    if not spec_path.exists():
        raise Pending("prompts/svg_design_spec.md does not exist yet")
    text = spec_path.read_text(encoding="utf-8")
    section = text.split("## SD-MOTION", 1)
    eq(len(section), 2, "no SD-MOTION section in the spec")
    body = section[1].split("\n## ", 1)[0]
    true("half the drawn elements" in body,
         "the spec does not state the staged-share floor the checker enforces")
    true("STATIC_STRUCTURE" in body, "SD-MOTION does not list its own finding code")


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


@case("corpus: which craft findings are hard is a deliberate list")
def _() -> None:
    # A false HARD finding costs a full generate+review cycle and corrupts the
    # retry loop's ranking, so promotion past the 90%-precision bar is deliberate
    # and this pins which codes have cleared it.
    #
    # The two clear it on different grounds, and the difference is the point.
    # TEXT_OVERFLOWS_RECT was promoted by *rendering* 8 instances and confirming
    # 4/4 on the narrowed form (rule 25). ARCHETYPE_NOT_DECLARED needs no such
    # measurement because it is definitional — the declaration is either there and
    # names a known form or it is not — and both fixes its message names are one
    # line of markup. Precision-by-construction is a valid route past the bar;
    # precision-by-assumption is not.
    hard_codes = set()
    for _, _, block in corpus():
        for f in G.craft_findings(block):
            if f.severity == G.HARD:
                hard_codes.add(f.code)
    eq(sorted(hard_codes), ["ARCHETYPE_NOT_DECLARED", "TEXT_OVERFLOWS_RECT"],
       "hard craft codes")


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
# Crossing bands and coincident overlays (the two exemptions)
# ---------------------------------------------------------------------------

# A transmembrane protein through a membrane band: mutual perpendicular
# containment. The lap IS the drawing. Neither of the older exemptions can reach
# it — the pump is 27% inside the band (under NESTING_SHARE's 45%) and its centre
# is 65 units from the nearest band edge (past EDGE_MOUNT_TOLERANCE's 8).
BAND = '<rect x="70" y="330" width="860" height="70" fill="#cfd8e3"/>'
PUMP = '<rect x="434" y="222" width="132" height="264" rx="14" fill="#3d6b99"/>'


@case("crossing: a band and the thing crossing it is not a collision")
def _() -> None:
    true("SHAPE_OVERLAP" not in codes(G.detect_overlaps(svg(BAND + PUMP))),
         "a transmembrane shape was reported as overlapping its own membrane")


@case("crossing: order does not matter")
def _() -> None:
    eq(codes(G.detect_overlaps(svg(PUMP + BAND))),
       codes(G.detect_overlaps(svg(BAND + PUMP))),
       "the exemption depends on document order")


@case("crossing: a diagonal straddle is still a collision")
def _() -> None:
    # The exemption is deliberately strict: BOTH spans must be full containments.
    # This pair overlaps by a corner in each axis, which is a real collision.
    #
    # The coordinates are not arbitrary. The first version of this fixture put the
    # two 300x300 rects at 100,100 and 250,250 and passed for the wrong reason —
    # 250,250 is exactly the smaller shape's centre, so `_mounted_on_edge`
    # exempted it and `_crossing_bands` was never consulted. A case that fails for
    # the wrong reason has stopped testing what its name says.
    a = '<rect x="100" y="100" width="300" height="300" fill="#3d6b99"/>'
    b = '<rect x="300" y="300" width="300" height="300" fill="#c1453b"/>'
    true("SHAPE_OVERLAP" in codes(G.detect_overlaps(svg(a + b))),
         "a diagonal straddle was exempted as a crossing")


@case("crossing: a band overlapped without being spanned is a collision")
def _() -> None:
    # A wide band and a box that dips into it. The band spans the box in x, but
    # the box does not span the band in y — so it is not a "+" and not exempt.
    # This is the near-miss the exemption has to distinguish from the pump.
    a = '<rect x="70" y="300" width="860" height="120" fill="#3d6b99"/>'
    b = '<rect x="100" y="360" width="300" height="200" fill="#c1453b"/>'
    true("SHAPE_OVERLAP" in codes(G.detect_overlaps(svg(a + b))),
         "a partial dip into a band was exempted as a crossing")


# The full SD-DEPTH raised-card idiom: offset shadow, gradient card, sheen at the
# identical box.
DEPTH_CARD = (
    '<rect x="206" y="206" width="300" height="140" rx="14" fill="#22303f" opacity="0.10"/>'
    '<rect x="200" y="200" width="300" height="140" rx="14" fill="url(#gPrimary)"/>'
    '<rect x="200" y="200" width="300" height="140" rx="14" fill="url(#gSheen)"/>'
)


@case("coincident: the depth idiom measures as ONE shape, not three")
def _() -> None:
    # Measured, and it corrects what this fixture first assumed: only TWO of the
    # three rects ever reach the pairing stage, because the elevation shadow is
    # translucent enough to be a wash already (opacity 0.10 vs WASH_MAX_OPACITY
    # 0.25). The sheen is the layer that needed the new dedup — it is opaque, at
    # the identical box, and doubled every finding the card took part in.
    shapes = G.element_boxes(svg(DEPTH_CARD)).shapes
    eq(len(shapes), 3, "the walker should still see all three rects")
    eq(sum(1 for s in shapes if s.is_wash), 1, "the elevation shadow is not a wash")
    pairable = [s for s in shapes if G._pairable(s)]
    eq(len(pairable), 2, "shadow excluded, card and sheen remain")
    eq(len(G.drop_coincident_overlays(pairable)), 1, "sheen not collapsed into the card")


@case("coincident: the FIRST box is the one kept")
def _() -> None:
    # Order-stable, so a reported box belongs to the card rather than to its
    # highlight — and two runs over one diagram agree.
    a = '<rect x="100" y="100" width="200" height="80" fill="#3d6b99"/>'
    b = '<rect x="100" y="100" width="200" height="80" fill="url(#gSheen)"/>'
    shapes = [s for s in G.element_boxes(svg(a + b)).shapes if G._pairable(s)]
    kept = G.drop_coincident_overlays(shapes)
    eq(len(kept), 1, "coincident pair not collapsed")
    true(kept[0] is shapes[0], "the second box was kept, not the first")


@case("coincident: a shape offset by more than the tolerance is kept")
def _() -> None:
    # 6px is 6x COINCIDENT_TOLERANCE. Two opaque cards that near-miss must both
    # survive — a dedup that swallowed them would hide real collisions.
    a = '<rect x="100" y="100" width="200" height="80" fill="#3d6b99"/>'
    b = '<rect x="106" y="106" width="200" height="80" fill="#c1453b"/>'
    shapes = [s for s in G.element_boxes(svg(a + b)).shapes if G._pairable(s)]
    eq(len(G.drop_coincident_overlays(shapes)), 2, "a near-miss pair was collapsed")


@case("coincident: the dedup does not hide a real collision")
def _() -> None:
    # The whole risk of a dedup: it must remove duplicate REPORTS, never a shape
    # whose overlap with a third object is genuine.
    doc = svg(DEPTH_CARD + '<rect x="420" y="260" width="300" height="140" fill="#c1453b"/>')
    eq(codes(G.detect_overlaps(doc)).count("SHAPE_OVERLAP"), 1,
       "the card/intruder collision should be reported exactly once")


# ---------------------------------------------------------------------------
# SD-STRUCTURE
# ---------------------------------------------------------------------------

PLAIN = '<rect x="60" y="120" width="200" height="100" rx="12" fill="#3d6b99"/>'


def decl(name: str, body: str = PLAIN) -> str:
    return svg(f"<!-- archetype: {name} -->{body}")


@case("structure: a declared archetype is clean")
def _() -> None:
    got = craft_codes(decl("comparison-columns"))
    true("ARCHETYPE_NOT_DECLARED" not in got and "ARCHETYPE_UNKNOWN" not in got,
         f"a correctly declared archetype was flagged: {got}")


@case("structure: every archetype name in the spec is accepted")
def _() -> None:
    # A hyphen in the name is the case that matters. The first version of the
    # declaration regex used `[^->]`, which excludes '-' — so it matched NONE of
    # the ten names and would have reported ARCHETYPE_NOT_DECLARED on a perfectly
    # declared diagram. A gate that cannot be satisfied is as bad as one that
    # never fires, and only running it finds this.
    for name in sorted(G.ARCHETYPES):
        got = craft_codes(decl(name))
        true("ARCHETYPE_NOT_DECLARED" not in got, f"'{name}' read as undeclared")
        true("ARCHETYPE_UNKNOWN" not in got, f"'{name}' read as unknown")


@case("structure: a missing declaration is HARD")
def _() -> None:
    true("ARCHETYPE_NOT_DECLARED" in craft_codes(svg(PLAIN)), "no finding without a declaration")
    eq(craft_severity(svg(PLAIN), "ARCHETYPE_NOT_DECLARED"), G.HARD,
       "ARCHETYPE_NOT_DECLARED severity")


@case("structure: an unknown archetype name is HARD")
def _() -> None:
    # The diagram that provoked this rule was a labelled bathtub. Naming the
    # object instead of the explanatory form is the exact failure.
    got = craft_codes(decl("bathtub"))
    true("ARCHETYPE_UNKNOWN" in got, f"an invented archetype passed: {got}")
    true("ARCHETYPE_NOT_DECLARED" not in got, "both archetype codes fired at once")
    eq(craft_severity(decl("bathtub"), "ARCHETYPE_UNKNOWN"), G.HARD, "severity")


@case("structure: the declaration tolerates case and whitespace")
def _() -> None:
    for raw in ("<!--archetype:cycle-->", "<!--  ARCHETYPE :  Cycle  -->"):
        got = craft_codes(svg(raw + PLAIN))
        true("ARCHETYPE_NOT_DECLARED" not in got and "ARCHETYPE_UNKNOWN" not in got,
             f"{raw!r} was not accepted: {got}")


@case("structure: the archetype list agrees with the spec's SD-TYPE table")
def _() -> None:
    # Rule 23's shape: the names live in two files — this module and the prompt
    # the generator reads. If they drift, the gate rejects a name the spec told
    # the model to use, which is unsatisfiable from inside the loop.
    spec = Path(__file__).resolve().parent / "prompts" / "svg_design_spec.md"
    if not spec.exists():
        raise Skip(f"design spec not found at {spec}")
    text = spec.read_text(encoding="utf-8")
    for name in sorted(G.ARCHETYPES):
        true(f"`{name}`" in text, f"archetype '{name}' is not named in the spec")
    # ...and the other direction: a type in the spec's table that the gate would
    # reject. Scoped to the SD-TYPE section, because "a backticked name at the
    # start of a `|` row" is not unique to it — SD-PALETTE's role table has the
    # same shape, and an unscoped match reported that the spec "offers `ink`".
    section = text.split("## SD-TYPE", 1)
    eq(len(section), 2, "no SD-TYPE section in the spec")
    table = re.findall(r"^\| `([a-z-]+)` \|", section[1].split("\n## ", 1)[0], re.MULTILINE)
    eq(len(table), len(G.ARCHETYPES), "the SD-TYPE table and ARCHETYPES differ in length")
    for name in table:
        true(name in G.ARCHETYPES, f"the spec offers '{name}' but the gate rejects it")


# ---------------------------------------------------------------------------
# SD-DEPTH: a gradient stroke that paints nothing
#
# Every expectation below was checked against a real Chrome render of the same
# three lines before it was written down (rule 25). A/B/C are that render: the
# horizontal path stroked with a vertical ramp came out BLANK, the flat-stroked
# copy of it drew, and the sloped one drew.
# ---------------------------------------------------------------------------

VGRAD = ('<defs><linearGradient id="gPrimary" x1="0" y1="0" x2="0" y2="1">'
         '<stop offset="0" stop-color="#5b8fc7"/>'
         '<stop offset="1" stop-color="#3d6b99"/></linearGradient></defs>')
HGRAD = ('<defs><linearGradient id="gFlat">'  # no coords: SVG defaults to horizontal
         '<stop offset="0" stop-color="#5b8fc7"/>'
         '<stop offset="1" stop-color="#3d6b99"/></linearGradient></defs>')


@case("depth: a horizontal line stroked with a vertical gradient is HARD")
def _() -> None:
    # Rendered blank. This is the defect that shipped: the "real neuron holds at
    # -70 mV" line — half of a two-curve comparison — was simply not on the page,
    # and every other gate said the diagram was clean.
    doc = svg(VGRAD + '<path d="M120 470 L920 470" fill="none" stroke="url(#gPrimary)" stroke-width="5"/>')
    hard = [f.code for f in G.craft_findings(doc) if f.severity == G.HARD]
    true("GRADIENT_STROKE_INVISIBLE" in hard, f"not flagged: {hard}")


@case("depth: the same line with a flat stroke is clean")
def _() -> None:
    # Rendered normally, and it is the fix the retry message names — so a gate
    # that flagged it too would be unsatisfiable.
    doc = svg(VGRAD + '<path d="M120 470 L920 470" fill="none" stroke="#3d6b99" stroke-width="5"/>')
    eq(G.degenerate_gradient_strokes(doc), [], "a flat stroke was flagged")


@case("depth: a sloped line with a vertical gradient is clean")
def _() -> None:
    # Rendered normally: the box has height, so the ramp has somewhere to run.
    # The rule is about extent along the ramp's axis, not about gradient strokes
    # being forbidden geometry.
    doc = svg(VGRAD + '<path d="M20 210 L380 250" fill="none" stroke="url(#gPrimary)"/>')
    eq(G.degenerate_gradient_strokes(doc), [], "a sloped line was flagged")


@case("depth: a vertical line dies on a HORIZONTAL ramp, and that is the default")
def _() -> None:
    # The mirror case, and the reason `_gradient_axes` implements SVG's defaults
    # rather than assuming vertical: `<linearGradient id="g">` with no coordinates
    # at all is x1=0% x2=100%, i.e. horizontal. A `<line>` drawn straight down and
    # stroked with it is invisible for the same reason.
    doc = svg(HGRAD + '<line x1="450" y1="120" x2="450" y2="600" stroke="url(#gFlat)"/>')
    eq([a for _, _, a in G.degenerate_gradient_strokes(doc)], ["x"], "axis not reported as x")
    # ...and the same line stroked with the VERTICAL ramp is fine.
    ok = svg(VGRAD + '<line x1="450" y1="120" x2="450" y2="600" stroke="url(#gPrimary)"/>')
    eq(G.degenerate_gradient_strokes(ok), [], "a vertical line on a vertical ramp was flagged")


@case("depth: shapes with area are never flagged")
def _() -> None:
    # rect/circle/ellipse always have extent in both axes, so a gradient stroke on
    # them paints. They are absent from _STROKEABLE rather than filtered late.
    doc = svg(VGRAD
              + '<rect x="60" y="120" width="200" height="100" fill="none" stroke="url(#gPrimary)"/>'
              + '<circle cx="500" cy="300" r="40" fill="none" stroke="url(#gPrimary)"/>')
    eq(G.degenerate_gradient_strokes(doc), [], "a shape with area was flagged")


@case("depth: a radial or userSpaceOnUse ramp does not depend on the box")
def _() -> None:
    # Neither collapses on a flat bbox, so neither is a defect — and treating them
    # as one would flag the sheen idiom the spec mandates.
    radial = ('<defs><radialGradient id="gR"><stop offset="0" stop-color="#fff"/>'
              '<stop offset="1" stop-color="#3d6b99"/></radialGradient></defs>')
    user = ('<defs><linearGradient id="gU" gradientUnits="userSpaceOnUse" '
            'x1="0" y1="0" x2="0" y2="700"><stop offset="0" stop-color="#5b8fc7"/>'
            '<stop offset="1" stop-color="#3d6b99"/></linearGradient></defs>')
    line = '<path d="M120 470 L920 470" fill="none" stroke="url(#%s)"/>'
    eq(G.degenerate_gradient_strokes(svg(radial + line % "gR")), [], "a radial ramp was flagged")
    eq(G.degenerate_gradient_strokes(svg(user + line % "gU")), [], "userSpaceOnUse was flagged")


@case("depth: an undefined gradient reference is not this rule's business")
def _() -> None:
    # A dangling `url(#typo)` is a different defect and the render is
    # implementation-defined. Silence here keeps this finding's message true:
    # it says the ramp is degenerate, and about a missing gradient it knows
    # nothing (rule 24 — the message must name a fix that works).
    doc = svg('<path d="M120 470 L920 470" fill="none" stroke="url(#nosuch)"/>')
    eq(G.degenerate_gradient_strokes(doc), [], "a dangling reference was flagged")


@case("depth: a gradient FILL on a flat line is not flagged")
def _() -> None:
    # `fill` on a zero-height path paints nothing anyway (there is no interior),
    # and the spec's whole SD-DEPTH push is gradient fills. Flagging the fill
    # attribute here would fight the rule it sits under.
    doc = svg(VGRAD + '<path d="M120 470 L920 470" fill="url(#gPrimary)" stroke="#3d6b99"/>')
    eq(G.degenerate_gradient_strokes(doc), [], "a gradient fill was flagged")


@case("depth: the fix text tells you to REMOVE the gradient, not add one")
def _() -> None:
    # SD-DEPTH now carries one advisory that says "add gradients" and one hard code
    # that means "this gradient deleted your line". A single entry naming only the
    # advisory fix would send a model whose line is invisible *because* of a
    # gradient to add more of them — rule 24's unfixable-feedback trap, arrived at
    # from a new direction.
    src = Path(__file__).resolve().parent / "svg_agent.py"
    if not src.exists():
        raise Skip(f"svg_agent.py not found at {src}")
    body = src.read_text(encoding="utf-8").split("SD_DEPTH: (", 1)
    eq(len(body), 2, "no SD_DEPTH fix text in svg_agent.py")
    fix = body[1].split("),", 1)[0].lower()
    true("stroke" in fix, "the SD_DEPTH fix text never mentions strokes")
    true("flat" in fix, "the SD_DEPTH fix text does not name the flat-hex fix")


@case("structure: every hard rule has its own fix text")
def _() -> None:
    # `_geometry_feedback` looks the fix up with `.get(..., generic)`, so a hard
    # rule added without an entry degrades silently to "Fix the geometry this
    # describes" — precision lost with no signal, which is the shape of rule 27's
    # computed-then-discarded defect. svg_agent cannot be imported (it builds a
    # Bedrock client at import time), so this reads the source.
    src = Path(__file__).resolve().parent / "svg_agent.py"
    if not src.exists():
        raise Skip(f"svg_agent.py not found at {src}")
    text = src.read_text(encoding="utf-8")
    body = text.split("_FIX_BY_RULE = {", 1)
    eq(len(body), 2, "no _FIX_BY_RULE map in svg_agent.py")
    keys = set(re.findall(r"^\s{4}(SD_[A-Z_]+):", body[1], re.MULTILINE))
    for rule in ("SD_STRUCTURE", "SD_SPACING", "SD_TEXT_FIT", "SD_ANCHOR", "SD_FONT",
                 "SD_CANVAS", "SD_MEASURABLE", "SD_MOTION", "SD_DEPTH"):
        true(rule in keys, f"{rule} can produce a HARD finding with no fix text")


def stack(lines: list[str], x: float = 100, y: float = 120,
          size: float = 14, step: float = 20) -> str:
    """A left-aligned run of <text> lines — the shape of hand-wrapped prose."""
    return "".join(
        f'<text x="{x}" y="{y + i * step}" text-anchor="start" font-size="{size}">{t}</text>'
        for i, t in enumerate(lines)
    )


PARAGRAPH = [
    "You can hold the level",
    "constant forever if the",
    "faucet runs at exactly",
    "the rate the drain empties",
]


@case("prose: a wrapped paragraph is flagged")
def _() -> None:
    got = craft_codes(decl("quantity-plot", stack(PARAGRAPH)))
    true("PROSE_BLOCK" in got, f"a 4-line paragraph was not flagged: {got}")


@case("prose: PROSE_BLOCK is advisory")
def _() -> None:
    # ~71% precision on the 12 corpus instances (the rest are short-phrase
    # legends), against rule 25's 90% bar for a hard finding. A hard finding that
    # fires on a legend would spend attempts moving correct labels.
    eq(craft_severity(decl("quantity-plot", stack(PARAGRAPH)), "PROSE_BLOCK"),
       G.ADVISORY, "PROSE_BLOCK severity")


@case("prose: an element-level word cap cannot see it")
def _() -> None:
    # The whole reason this rule measures arrangement instead of length: every
    # line of that paragraph is 4-5 words, comfortably under LABEL_WORD_CAP.
    for line in PARAGRAPH:
        true(len(line.split()) <= G.LABEL_WORD_CAP,
             f"fixture line is already over the word cap: {line!r}")


@case("prose: two lines are not a paragraph")
def _() -> None:
    true("PROSE_BLOCK" not in craft_codes(decl("cycle", stack(PARAGRAPH[:2]))),
         "two lines were read as prose")


@case("prose: three short lines are under the word floor")
def _() -> None:
    got = craft_codes(decl("cycle", stack(["one two", "three four", "five six"])))
    true("PROSE_BLOCK" not in got, f"6 words were read as prose: {got}")


@case("prose: widely spaced labels are separate labels")
def _() -> None:
    # 60px apart at 14px is 4.3x the font size, past PROSE_LINE_SPACING_MAX. A
    # column of labels down the left of a comparison grid must not read as prose.
    got = craft_codes(decl("comparison-columns", stack(PARAGRAPH, step=60)))
    true("PROSE_BLOCK" not in got, f"a spaced label column was read as prose: {got}")


@case("prose: a key/value table is not prose")
def _() -> None:
    # Measured, not anticipated: the first prototype flagged exactly this — the
    # probe diagram's own axis panel — and a data table is the most
    # information-dense thing a diagram can carry, i.e. the opposite of the defect.
    got = craft_codes(decl("quantity-plot", stack([
        "sodium_inside = 10", "sodium_outside = 140", "ratio = 14", "resting = -70 mV",
    ])))
    true("PROSE_BLOCK" not in got, f"a value table was read as prose: {got}")


@case("prose: a bullet list is not prose")
def _() -> None:
    # 2 of the 14 instances the first prototype reported on the corpus.
    got = craft_codes(decl("part-whole", stack([
        "• Heartburn", "• Constipation", "• Varicose veins",
        "• Leg cramps at night",
    ])))
    true("PROSE_BLOCK" not in got, f"a bullet list was read as prose: {got}")


@case("prose: a numbered list is not prose")
def _() -> None:
    got = craft_codes(decl("decision-tree", stack([
        "1. open the valve", "2. wait for level", "3. close the valve", "4. read the gauge",
    ])))
    true("PROSE_BLOCK" not in got, f"a numbered list was read as prose: {got}")


@case("prose: two columns of prose are two findings")
def _() -> None:
    doc = decl("comparison-columns", stack(PARAGRAPH, x=100) + stack(PARAGRAPH, x=520))
    runs = G.prose_runs([t for t in G.element_boxes(doc).texts if not t.uncertain])
    eq(len(runs), 2, "prose runs in separate columns were merged or dropped")


@case("prose: one run is reported once, not once per nested sub-run")
def _() -> None:
    doc = decl("cycle", stack(PARAGRAPH + ["and it stays there"]))
    runs = G.prose_runs([t for t in G.element_boxes(doc).texts if not t.uncertain])
    eq(len(runs), 1, "a single 5-line paragraph produced more than one run")
    eq(len(runs[0]), 5, "the run is not maximal")


@case("structure: a 6-word label is fine and a 7-word one is flagged")
def _() -> None:
    six = decl("cycle", stack(["one two three four five six"]))
    true("LABEL_TOO_WORDY" not in craft_codes(six), "a 6-word label was flagged")
    seven = decl("cycle", stack(["one two three four five six seven"]))
    true("LABEL_TOO_WORDY" in craft_codes(seven), "a 7-word label was not flagged")
    eq(craft_severity(seven, "LABEL_TOO_WORDY"), G.ADVISORY, "LABEL_TOO_WORDY severity")


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
