"""Rebuild the cover fixtures from full-size model output. Stdlib only.

    uv run --no-project python fixtures/covers/regenerate.py <name>=<png> [...]

e.g.  regenerate.py flux2pro=/tmp/bakeoff/black-forest-labs_flux.2-pro.png

Run from `lesson_agent/`. It prints the before/after statistics for every file and writes
nothing if a source PNG is one the reader cannot decode — a fixture whose own decode is
`readable=False` would make the suite assert on zeros.

This exists so the fixtures are reproducible rather than four opaque blobs someone once
committed, and so adding a fifth vendor is a one-line invocation. The transform and the
reason it is a stride and not a crop are in README.md beside this file; the numbers it
prints are the ones that table quotes, so a change to `_measure_png` shows up as a diff
here.
"""

import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import thumbnail_agent as ta  # noqa: E402

# Wide enough that `_measure_png`'s own step=4 still has a few thousand samples to work
# with, small enough that four of them are under a megabyte in the repo and in the worker
# image. Not tuned: 400 was the first value tried and the saturation drift it produced
# (≤0.004) was already inside what the suite needs.
TARGET_W = 400

OUT = Path(__file__).resolve().parent


def write_png(path: Path, width: int, height: int, channels: int, rows) -> None:
    """8-bit non-interlaced PNG, one filter-0 scanline per row. The inverse of
    `png_scanlines`, which is the only reader that has to accept it."""
    colour_type = {1: 0, 3: 2, 4: 6}[channels]

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def downsample(src: Path, dst: Path) -> tuple[int, int]:
    width, height, channels, rows = ta.png_scanlines(src)
    if rows is None:
        raise SystemExit(
            f"{src} does not decode ({width}x{height}) — a fixture the reader cannot read "
            "would have the suite assert on zeros. Convert it or drop the vendor."
        )
    stride = max(1, round(width / TARGET_W))
    kept = [
        bytes(
            b
            for x in range(0, width, stride)
            for b in row[x * channels : (x + 1) * channels]
        )
        for y, row in enumerate(rows)
        if y % stride == 0
    ]
    write_png(dst, len(kept[0]) // channels, len(kept), channels, kept)
    return stride, channels


def main(argv: list[str]) -> int:
    if not argv or any("=" not in a for a in argv):
        print(__doc__, file=sys.stderr)
        return 2

    print(
        f"{'fixture':<14}{'stride':>7}{'ch':>4}{'dims':>14}{'KB':>7}"
        f"{'sat':>17}{'hues':>8}{'ground':>14}"
    )
    for arg in argv:
        name, _, source = arg.partition("=")
        src, dst = Path(source), OUT / f"{name}.png"
        stride, channels = downsample(src, dst)
        before, after = ta._measure_png(src), ta._measure_png(dst)
        dims = f"{after['width']}x{after['height']}"
        print(
            f"{name:<14}{stride:>7}{channels:>4}{dims:>14}"
            f"{dst.stat().st_size / 1024:7.0f}"
            f"{before['mean_saturation']:9.3f}→{after['mean_saturation']:<7.3f}"
            f"{before['hue_families']:>4}→{after['hue_families']:<3}"
            f"{before['ground_luminance']:8.3f}→{after['ground_luminance']:<5.3f}"
        )
    print(
        "\nNow update README.md's tables, and remember `contrast_ratio` is NOT stride-"
        "stable — see the section there before pinning any figure it prints."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
