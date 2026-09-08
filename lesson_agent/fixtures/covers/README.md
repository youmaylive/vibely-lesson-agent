# Cover fixtures — real model output, downsampled

Four PNGs, one per vendor, from the bake-off that chose `OPENROUTER_IMAGE_MODEL`. They exist so
`thumbnail_agent.test.py` can assert the pixel reader and the pixel statistics against **bytes a
diffusion model actually produced**, offline, with no key and no network — which is the only thing
that proves `png_scanlines` reads PNGs it was not written for. It was written for Chrome's.

| fixture | model | original | fixture | stride |
|---|---|---|---|---|
| `flux2pro.png` | `black-forest-labs/flux.2-pro` | 1824×1024, 3.10 MB | 365×205, 166 KB | 5 |
| `gemini3pro.png` | `google/gemini-3-pro-image` | 2752×1536, 4.81 MB | 394×220, 175 KB | 7 |
| `gptimage2.png` | `openai/gpt-image-2` | 1536×864, 1.69 MB | 384×216, 169 KB | 4 |
| `riverflow25.png` | `sourceful/riverflow-v2.5-pro` | 2560×1440, 5.83 MB | 427×240, 194 KB | 6 |

All four are 8-bit non-interlaced **RGB** (3 channels) and read `readable=True`. The originals are
not in the repo — 15.4 MB for four pictures, against 721 KB here.

## The transform, and why it is a stride rather than a crop

Every pixel of every *n*-th row, every *n*-th pixel. `regenerate.py` is the exact code.

A crop would have been simpler and wrong: the statistics these fixtures pin are **whole-canvas
means** (`mean_saturation`, `hue_families`, `ground_luminance`), and a crop of a cover is a crop of
one region of it — a corner of the flux cover is nearly all ground. Measured, both directions:
saturation moves by at most **0.004** across all four fixtures, and `hue_families` and
`ground_luminance` are identical on all four.

| fixture | saturation orig → fixture | hue families | ground luminance |
|---|---|---|---|
| `flux2pro` | 0.459 → 0.456 | 4 → 4 | 0.006 → 0.006 |
| `gemini3pro` | 0.572 → 0.573 | 4 → 4 | 0.011 → 0.011 |
| `gptimage2` | 0.854 → 0.854 | 5 → 5 | 0.001 → 0.001 |
| `riverflow25` | 0.910 → 0.906 | 3 → 3 | 0.002 → 0.002 |

## Two things these fixtures deliberately do NOT pin

**`TH-SIZE` (≥ 1200×630).** Every fixture fails it by construction. The size and aspect thresholds
are tested with the synthetic `_cover()` helper instead, which can be any dimensions for nothing.
Asserting a floor against a file chosen to be small would be a test of the fixture, not the gate.

**`contrast_ratio`.** It is not stable under sampling density, so a fixture cannot pin the original's
figure — and that turned out to be a fact about the *metric*, not about the downsample.
`_measure_png` takes every 4th pixel by default and calls a luminance bin a band only if it holds
`MIN_BAND_SHARE` (0.001) of the samples; at fewer samples that share is fewer pixels, so sparser and
more extreme bins start qualifying. Measured on the **originals** at increasing `step`:

| original | step=4 | step=8 | step=12 | step=18 | step=24 | fixture |
|---|---|---|---|---|---|---|
| `flux2pro` | 12.39 | 12.48 | 10.54 | 12.39 | 11.96 | **12.39** |
| `gemini3pro` | 11.38 | 11.38 | 11.38 | 11.38 | 16.77 | **17.02** |
| `gptimage2` | 14.53 | 14.53 | 14.53 | 14.47 | 15.45 | **14.53** |
| `riverflow25` | 13.90 | 13.90 | 13.90 | 14.00 | 14.40 | **14.40** |

Each fixture lands where the original lands at the equivalent effective stride (fixture stride ×
the built-in step), so the fixture is faithful — the number simply is not a stable property of a
cover. That is a second, independent reason `TH-CONTRAST` is advisory and not a hard gate, alongside
the one in `prompts/course_thumbnail_spec.md`: it never fired once on 37 real covers.

The figures the spec quotes for calibration (12.4 / 11.4 / 14.5 / 13.9) are the **originals at the
default step**, and the suite re-measures them only in the loudly-skipped section that runs when
`/tmp/bakeoff` still exists on the machine.
