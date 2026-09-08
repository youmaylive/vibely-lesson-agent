"""Thumbnail agent — one course in, one PNG cover out.

Its only job. It does not upload, does not touch the database, is not a worker
phase and has no place in the validation loop: it reads a `course_spine.json`,
has an image model paint a cover, and writes a 16:9 PNG.

    python thumbnail_agent.py <course_spine.json> --out thumb.png

Where the design brief comes from
--------------------------------
Not from here. `_DESIGN` is assembled from two files on disk:

* `config.THUMBNAIL_SKILL` — the third-party `youtube-thumbnail-design` skill,
  vendored verbatim (see PROVENANCE.md beside it). Roughly half of it is unusable
  here, so `load_skill()` whitelists the design sections by heading and strips every
  fenced block; it RAISES if a whitelisted heading is missing, because a brief that
  quietly loses its colour rules is rule 26's failure exactly.
* `config.THUMBNAIL_SPEC` — our deltas: the rules that invert for a course rather than
  a video, the prompt-craft rules, and the values the checks below enforce. Every rule
  has a `TH-*` ID and every finding names one, so a correction turn can quote the fix
  for that rule rather than "make it better" (rule 24).

The first version of this file held the brief inline and produced covers with a mean
saturation of about 0.05 — pale, thin, and rejected. That is why the colour rules are
*measured* on the pixels rather than merely stated (see `_check_png`).

Why an image model, and why that is a reversal
----------------------------------------------
This generator used to write **SVG** and rasterise it with headless Chrome, on one
stated premise: "a cover has to carry the course title, and diffusion cannot spell."
That premise is now measured, and it is false. Five OpenRouter image models were given
one identical prompt asking for the headline `HOW NEURONS FIRE`; **all five spelled it
correctly**, and a vision model reading the PNGs back transcribed all four PNG-returning
covers verbatim. The bake-off table is in `openrouter.py`.

The reason to move was never the spelling anyway — it was that an LLM drawing SVG
produces *drawings*, and seven test covers came back as boxes, lines and a wall of
blue-orange. An image model paints. So the ~25 `TH-*` vector rules that existed to stop
an SVG from being ugly are gone, along with Chromium (~510 MB) from the worker image.

What replaced them is narrower and load-bearing: the model paints the headline, and
`openrouter.transcribe` reads the finished PNG back so the text must match by exact
string equality on a normalised string. That is a *stronger* legibility test than the
ratio it replaces — it asks whether the words can actually be read, rather than whether
two luminance bands differ.

Three of the four pixel gates that survived the pivot turned out never to have fired
-----------------------------------------------------------------------------------
Measured across 37 covers in `output/thumbnails/` plus the 4 painted ones. Kept here
because it is the reason only one of them is still a gate:

* `TH-SATURATION` (now 0.10, was 0.35) — **real, and the only one**, but the number was
  wrong for this medium and has been re-sited on a 57-cover re-measurement. The word
  "accepted" in the original note did the damage: the 0.778-0.928 band it called accepted is
  the SVG-era corpus this effort exists to replace. Painted covers run 0.13-0.84 and 0.35
  cut the bottom third of them, including two good chalkboard covers at 0.13 and 0.22. The
  0.03-0.06 population it was written to reject is real and still fails. See the constant.
* `TH-CONTRAST` (4.5:1) — **never fired once**, including on all six covers that *were*
  rejected (they measured 14.2-14.3:1; what was wrong with them was saturation). On
  painted input it is worse than useless: see `MIN_BAND_SHARE`. Now advisory.
* `TH-HUES` (<=3) — **never fired**; the SVG corpus never exceeded 2. Fires on 3 of 4
  painted covers, where hue variety is the point rather than a defect. Retired.
* `TH-BYTES` (2 MB) — **never fired**; SVG covers ran 0.03-0.09 MB, 20-60x under. 3 of 4
  painted covers exceed it. Now advisory at 4 MB with an operator-facing remedy, because
  no retry message can make a diffusion model emit fewer bytes (rule 24).

The covers were unrecognisable, and the cause was in this file, not in the model
--------------------------------------------------------------------------------
*"I am not able to recognise it"*, on covers that passed every gate above. Two mechanical
causes, both mine, both now measured:

* **The exclusion clause was stripping the subject's own markings.** `_EXCLUSIONS` banned
  all text including "no letters hidden in the artwork", so once the subject came from the
  curriculum it was routinely a thing whose meaning IS its markings, and the model wrote —
  in its own words — a split-flap price board "with no digits, letters, or symbols printed
  on any flap". A price board with no prices. Split into `_EXCLUSIONS` (added text only)
  plus `_MARKS_CLAUSE` (the subject's markings, asked for positively), with a new machine-
  checked `MARKS:` reply field so the permission is not prose nobody executes (rule 26).
  The one constraint on it: **non-lexical** marks only, because the transcription gate
  compares the headline letter for letter against every legible word in the picture.
* **Three rules whose intersection was "invent a prop".** `TH-GROUND` asks for a concept
  (abstract), `TH-SUBJECT` banned diagrams, and `TH-STOCK` banned "the field's obvious
  object". For *market equilibrium* that barred the recognisable answer three ways over.
  The corpus says the opposite: all four covers on disk that work draw the field's obvious
  artifact plainly (a crate of oranges, a coin stack, a score on a stand, a bale of silk)
  and all four that fail draw an invented prop. So `TH-SUBJECT` now asks for *the physical
  artifact a practitioner handles* and `TH-STOCK` is narrowed to the office-photograph
  register it should always have meant. Grounding chooses the topic; the artifact rule
  chooses the object.

Two gates came out of the same measurement: `TH-ACCENT` (advisory — mean saturation cannot
separate a muddy cover from a good one; see `MIN_ACCENT_SHARE` for the eleven-cover table
that proves it) and `TH-GLYPH` (hard — `CLASSÆS` shipped clean because a vision model asked
for *words* answers with the word it expects; see `openrouter.SPELL_PROMPT`).

One provider, not two
---------------------
A text model writes the *image prompt* and an image model paints it — both through
OpenRouter, both booked from the `usage.cost` the response reports. The text call was
briefly `svg_agent._llm_call_async` (Bedrock), and that was wrong for a reason no test
could see: `svg_agent` imports `anthropic`, which does not exist in the venv the worker
process runs under, so the whole phase was unloadable in the built image. See the comment
at the import below. `svg_agent.py` itself is still deliberately NOT edited — its
`_bedrock` client is a module-level singleton built at import time, and disturbing it
would reach the in-lesson diagrams, which stay on SVG by decision.

`png_scanlines` and everything above it in the colour section are pure stdlib and were
always origin-agnostic — they never cared that Chrome produced the bytes. Verified
rather than assumed: all four painted PNGs decode with `readable=True`. That single fact
is what made this pivot cheap.

Two rules in the brief are deliberately ungated
-----------------------------------------------
`TH-TRUE` ("the shape must be true, not merely plausible") and `TH-PALETTE`. The first
is unchanged and unreachable by measurement: a cover drawn beautifully that states
something false is worse than one with no shape, and this generator has shipped exactly
that — a bond potential-energy curve drawn as a peak where the stable state is a
minimum.

`TH-PALETTE` used to be enforced by scanning hexes in the SVG source, which a raster has
none of. The measurable proxy — does the painted cover's dominant hue family match the
requested row? — was tested and rejected: asked for indigo (family 8), all four models
painted family 7 (blue) with family 8 under 4%, honouring cyan and yellow correctly. A
bin-exact gate would reject all four good covers and a +/-1-bin gate would be fitted to
n=4, which is rule 25's trap. So the palette is art direction, ungated, and the
anti-monotony fix moved into the prompt instead: `palette_for()` rotates it
deterministically off the title, because asking the model to choose produced 6
blue-orange covers out of 7.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import os
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import NamedTuple

import config
import openrouter
import usage

# NOT `from svg_agent import _llm_call_async`, and the reason is measured rather than
# stylistic: `svg_agent` imports `anthropic`, which is absent from the venv the worker
# actually runs under (`uv run --directory /app/ontology-engine`), so that one import made
# the whole cover phase unloadable in the built image — `No module named 'anthropic'`,
# every course, whatever the key. The art direction goes through OpenRouter now, so this
# module needs only `httpx`, which that venv does have. `svg_agent.py` is deliberately
# untouched: its `_bedrock` client is a module-level singleton built at import time, and
# the in-lesson diagrams depend on it.
DEFAULT_MODEL = openrouter.DEFAULT_TEXT_MODEL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# 16:9, the aspect every card and og:image wants — requested as a RATIO because no model
# on the OpenRouter images endpoint accepts an explicit pixel size (measured against
# `/api/v1/images/models/{id}/endpoints` for all 48). What comes back is the model's own
# grid: measured 1536x864, 1824x1024, 2560x1440 and 2752x1536 for one identical request.
#
# So the dimension check is a RATIO plus a FLOOR rather than an equality. The floor is
# the og:image minimum, which every measured model clears by a wide margin; the tolerance
# is because two of the four are not exactly 16:9 (1824/1024 = 1.7812, 2752/1536 =
# 1.7917 against 1.7778) and a cover is not less usable for being 0.8% wide.
ASPECT_RATIO = "16:9"
TARGET_ASPECT = 16 / 9
ASPECT_TOLERANCE = 0.02
MIN_PNG_WIDTH, MIN_PNG_HEIGHT = 1200, 630

# One generate plus three corrections. Unchanged from the SVG era, but the arithmetic is
# different and worth restating: an attempt is now ~$0.045 (image) + ~$0.006
# (transcription) + the Claude call that writes the prompt, so a full 4-attempt run is
# roughly $0.25. Still no spend cap needed, unlike the lesson loop's
# MAX_VALIDATION_ATTEMPTS = 500, which has none.
MAX_ATTEMPTS = 4

# The skill's "Max 6 words". Now doing double duty: it keeps the headline short (which
# is also what image models spell most reliably) AND it bounds the string the
# transcription gate has to match exactly. A 9-word headline is both worse design and a
# larger surface for one transcription slip to fail the gate on.
MAX_TEXT_WORDS = 6

# The shortest string that can be an art direction rather than a caption. Named because
# two places need to agree on it and they are 500 lines apart: `parse_art_direction`
# rejects a reply below it, and `compose_text_free_prompt` uses it to decide whether
# pruning the headline out of an art direction has left anything worth painting.
MIN_ART_CHARS = 80

# ---- How much of the course goes into the prompt ----------------------------------
#
# Measured, and the measurement is the reason these exist. Before this, the COURSE block
# was **2,821 chars against `_DESIGN`'s 25,411** — the model was told 84% about YouTube
# thumbnail craft and 9% about the course it was drawing, and what it did get was the
# title, 420 chars of description and ten bare module titles. Meanwhile every real spine
# on this machine (34 of them, 364 module dicts) carries `key_concepts` in **364/364** —
# 2,122 named things, ~62 per course, e.g. "Production Possibility Frontier", "Refractory
# period", "Design Matrix" — and every one of them was dropped on the floor. Rule 27's
# shape: computed upstream, never read.
#
# (The count says *real*: `rglob` also finds 2 hand-written fixtures under
# `output/covers-review/spines/`, which have no `key_concepts` at all. Counting those gave
# an earlier "36 spines / 370 modules, 370/370" — a denominator that blamed the planner for
# files I wrote. The corpus test excludes them by path and prints which ones.)
#
# `MAX_CURRICULUM_CHARS` is a bound, not a target. The largest spine in the corpus
# renders to 18,003 chars, so nothing measurable today is trimmed at all; the cap is here
# so a future 30-module spine degrades predictably instead of silently doubling a prompt
# that is re-sent up to MAX_ATTEMPTS times.
MAX_CURRICULUM_CHARS = 20_000
# 12 before, and three corpus spines have 15-16 modules, so the last ones were being
# dropped without a word. 14 covers all but two, and those two now say so.
MAX_MODULES = 14
# Per-field caps, applied before the global bound. A module's description is prose that
# restates its title; the concepts are the load-bearing part, so they get the most room.
MAX_MODULE_DESC = 300
MAX_CONCEPT_CHARS = 80
MAX_CONCEPTS_PER_MODULE = 8
MAX_CHECKPOINT_CHARS = 220
MAX_SEED_CHARS = 140
MAX_SEEDS_PER_MODULE = 3
MAX_OBJECTIVES = 8
MAX_PREREQUISITES = 5

# ---- Pixel floors: one gate, three reports ----------------------------------------
#
# Every number here was set by running BOTH directions (rule 25), because a gate that
# cannot fail on the known-bad input is decoration and one that fires on input which
# followed the brief is worse than nothing (rule 24). Two populations, measured with
# `_measure_png` itself rather than a fresh script: the **37 SVG-era covers** in
# `output/thumbnails/` (including the 6 in `rejected-original/`, which is the known-bad)
# and the **4 painted covers** from the bake-off, which is the medium that now ships.
#
# Running that is what demoted three of the four. The table is in the module docstring;
# what follows is the consequence, one constant at a time.

# MIN_MEAN_SATURATION — **the gate, re-sited from 0.35 to 0.10 on a re-measurement of the
# whole corpus.** It still catches "it does not have colors", the complaint the whole cover
# effort started from. What changed is that 0.35 had begun firing on good covers, because
# the style gallery added dark-ground styles the number was calibrated before.
#
# The original note here read "rejected 0.030-0.059, accepted 0.778-0.928 … a 13x
# separation". Both figures reproduce exactly (`covers-review/sat_probe.py`, using
# `hsv_saturation` itself rather than a reimplementation — rule 25). The error was not in
# the arithmetic, it was in the word **accepted**: that 0.778-0.928 band is the SVG-era
# corpus, i.e. the covers this whole effort exists to replace. Measured over 57 covers, one
# instrument, three populations:
#
#     n   mean sat     population
#     6   0.03-0.06    pale near-white SVG  — "it does not have colors", the real complaint
#    45   0.13-0.84    painted, current pipeline
#     5   0.78-0.92    SVG-era vivid        — rejected as "boxes and lines"
#
# So on this corpus the statistic's correlation with cover quality is, if anything,
# **inverted**: `covers-review/README.md` names `3-old-svg-era/v13-economics.png` as "the
# clearest example of the complaint that started this work" and it measures **0.87**, 4th
# highest of 57. Meanwhile two forced-`chalkboard` covers measured **0.13** and **0.22** and
# both are covers I would ship (opened and looked at — rule 18) and the 0.35 floor rejected
# both. Re-checked afterwards on those exact bytes: 0.22 and 0.13 are now advisory, and a
# 0.49 cover gets no line at all. Within one style and one spine the figure spans 0.13-0.76,
# a 6x spread, so no per-style floor is available either.
#
# The retry it triggered is rule 24's unfixable-feedback trap on a structural argument, NOT
# on the evidence I first cited for it: "be more saturated" has no satisfying answer on a
# chalkboard, because the ground is most of the canvas and it is neutral by definition. I had
# read a forced run's `TH-STYLE: 'dark-atmospheric' is not one of the 1 names in the STYLE
# GALLERY` as the model answering that feedback by trying to leave the style. A second forced
# run tried to leave on **attempt 1, with no feedback at all** (`vector-illustration`), so
# escaping is baseline behaviour of the forced-gallery patch and is not evidence about this
# gate. The argument stands; that observation was never support for it.
#
# **0.10 is the gap, not a guess:** 1.7x above the pale population's ceiling (0.06) and 1.3x
# below the painted population's floor (0.13). The bound that matters is the upper one, and
# it is thin — so a genuinely washed-out grey render, which is diffusion's easiest mistake
# and is NOT in this corpus, would now have to be greyer than any chalkboard to be caught.
# That is the accepted cost of not rejecting the good ones. `ADVISORY_SATURATION` below is
# what keeps the middle of the range observable rather than discarded.
#
# Deliberately NOT a demotion to advisory, unlike `TH-CONTRAST`. The 0.03-0.06 population is
# real, is the founding complaint, and is one env var away from recurring — every declined
# pale style below sits in it.
MIN_MEAN_SATURATION = 0.10

# ADVISORY_SATURATION — the old floor, kept as the top of an advisory band so that
# re-siting the gate does not throw the information away. 0.10-0.35 is **printed** and never
# retried, alongside `_check_png`'s other advisories — print-only, not `report["advisories"]`,
# which this function does not populate. That retry is precisely what cost the chalkboard
# covers their style. A rule deleted rather than relabelled is rule 26's regression that no
# test catches, so both numbers stay in the file with their reasons.
ADVISORY_SATURATION = 0.35

# MIN_ACCENT_SHARE — **advisory, and its limit is stated below rather than discovered
# later.** The share of pixels that are both bright and saturated (`luma > ACCENT_MIN_LUM`
# and `hsv_saturation > ACCENT_MIN_SAT`) — the "single warm pool of light against a cool
# dark surround" every cover that works describes.
#
# It exists because MIN_MEAN_SATURATION above **cannot see the failure that prompted it.**
# Measured on eleven covers on disk with `accent_share()` itself, working ones first:
#
#     accent%  sat   cover
#      49.4   0.65  silk-road            works
#      14.6   0.48  music-theory         works
#       8.7   0.67  compound-interest    works
#       4.4   0.45  supply-and-demand    works
#       4.0   0.39  after/python-oop     unrecognisable
#       3.9   0.48  before/python-oop    unrecognisable
#       0.9   0.45  recursion            unrecognisable
#       0.8   0.55  before/economics     unrecognisable
#       0.3   0.43  after/economics      worst
#
# Read the `sat` column: **mean saturation does not separate these at all.** The worst
# cover (0.43) scores ABOVE a good one (0.45), and `before/economics` at 0.55 beats two of
# the three good ones. Mean luminance is no better — the good `supply-and-demand` is the
# second-darkest of the set. So the 0.35 floor was never going to catch a near-black subject
# on a dark field, and this statistic is what does.
#
# **`ACCENT_MIN_LUM` is compared against `luma()`, NOT against `luminance()`, and the
# difference is not cosmetic.** `luminance()` is WCAG relative luminance — sRGB linearised
# — which is the right thing for a contrast ratio and the wrong thing here: it pushes every
# mid-tone down, and re-measuring this table through it collapses the whole set into
# 0.02%-27.8% with the populations INTERLEAVED (the working `supply-and-demand` lands at
# 0.29% below the failing `after/python-oop` at 0.71%, so no threshold on it separates
# anything). Written first with the helper that happened to be in the file, which quietly
# changed the statistic the threshold had been calibrated against — rule 25's exact shape,
# the same mistake as measuring an SVG's text widths with a character count. HSV *value*
# fails the other way: it rates `before/economics` at 28.6%, above three covers that work.
#
# **Advisory, and honestly labelled: it separates MUDDY from NOT MUDDY, not RECOGNISABLE
# from UNRECOGNISABLE.** Both python-oop covers clear 2% and both are unrecognisable — what
# is wrong with them is the subject, which no pixel statistic can reach (that is the vision
# critique's job). And the margin is thin in the other direction too: the lowest working
# cover (4.4) sits only 0.4pp above the highest failing one (4.0), so this is a floor with
# 2x headroom under the good population, not a boundary between them. Promoting it to a hard
# gate on nine samples is precisely the trap that once flagged 76% of this project's diagrams
# and silently replaced the review that mattered (rule 24); it stays advisory until precision
# is measured on ten hand-sampled covers (rule 25's bar). The 2% floor sits in the gap
# between 0.9 and 3.9, so on the measured set it flags `recursion` and both economics covers
# and passes all four that work.
#
# **RE-MEASURED on 57 covers after MIN_MEAN_SATURATION above turned out to be mis-sited, and
# the suspicion did NOT carry over** (`covers-review/sat_probe.py --all --accent`, which
# computes this share with THESE thresholds rather than a reimplementation). I expected the
# same defect, because the same change — the `chalkboard` / `dark-atmospheric` styles — is
# what broke the other statistic. It is not the same, for two measured reasons.
#
# First, **the two statistics are complementary, not redundant, and this is the evidence for
# it.** Every SVG-era cover that mean saturation scored HIGH — the inverted correlation that
# forced the re-siting above — this one scores LOW: `v13-algo-trading` 0.0% at sat 0.92,
# `v13-economics` 0.8% at 0.87 (the cover `covers-review/README.md` names as the clearest
# example of the founding complaint), `v14-chemistry` 1.0%, `v14-model-fitting` 1.4%. So the
# claim four paragraphs up — that mean saturation cannot see this failure — held up on 5x the
# covers it was written from, and this floor is the thing that catches the population the
# other one now waves through.
#
# Second, **the false positives are real but they cost a printed line, and that difference is
# the whole reason this is not the same bug.** It fires on 17 of 57, including 2 of the 6
# covers I hand-labelled good (`probe-chalk/…attempt2` 1.1%, `styled6/recursion` 1.8%) — both
# dark-ground, so the mechanism IS present — while passing a bad-subject cover at 8.2%. That
# is well under rule 25's 90% bar. But `accent_share` is `print()`ed here and put in the
# report under a key `phases/thumbnail.py` never reads: nothing retries on it, nothing blocks
# on it. The saturation floor was HARD and rejected good covers; this one describes them.
# **So it is deliberately NOT moved** — a threshold with poor precision and no consequence is
# worth less than nothing only if someone promotes it, and the paragraph above already
# forbids that. Ten hand-sampled covers is still the bar before it moves in either direction.
ACCENT_MIN_LUM = 0.45
ACCENT_MIN_SAT = 0.45
MIN_ACCENT_SHARE = 0.02

# MIN_CONTRAST_RATIO — **advisory, and the demotion was measured, not conceded.**
#
# What `_measure_png` compares: the modal luminance bin (the "ground") against the most
# distant bin that still covers MIN_BAND_SHARE of the canvas. That worked on flat SVG,
# where type sits in one solid bin. It does not survive painting, and the mechanism is
# worth writing down because the failure looks like a bad cover rather than a bad gate:
# flux's headline really is bright — luminance bin 957, an 18.0:1 ratio against its
# ground, plainly legible — but it is anti-aliased with a glow, so those pixels smear
# across dozens of bins and *none* of them clears a 0.5% floor. The winning bin collapses
# to 35 and the cover reads 1.5:1.
#
# Two things follow. MIN_BAND_SHARE drops 0.005 -> 0.001, which recovers the real
# numbers (flux 12.4, gemini 11.4, gpt-image-2 14.5, riverflow 13.9) and moves the SVG
# corpus by less than 0.1 — the 0.005 figure was never exercised, which is *why* nobody
# noticed. And the ratio itself stops being a gate: across all 37 SVG covers it **never
# fired once**, including all six that were genuinely rejected (they measured 14.2-14.3:1;
# what was wrong with them was saturation). A threshold that has never fired on 37 files
# is not protecting anything, and on painted input its floor is a property of the
# anti-aliasing rather than of the design.
#
# What it existed *for* — "can the title be read" — is now tested directly and far more
# strictly by `openrouter.transcribe`: a vision model must read the headline back
# letter-for-letter. That is a stronger claim than any two-band ratio, so the ratio is
# reported and nothing branches on it.
MIN_CONTRAST_RATIO = 4.5
MIN_BAND_SHARE = 0.001

# Hue families: **reported, never enforced.** There was a MAX_HUE_FAMILIES = 3 here, from
# the skill's "use 3 colors maximum". It never fired on the SVG corpus (max 2) and fires
# on 3 of the 4 painted covers — where hue variety is the point rather than a defect: a
# painted neuron legitimately carries indigo ground, cyan filaments, a yellow pulse and a
# warm rim light. Enforcing it would reject every cover that succeeded. The count stays
# in the report because "how many colours is this thing" is worth being able to read.

# SQUINT_W is the skill's 120px test: the cover is box-downscaled to this width and the
# luminance spread is REPORTED, with no threshold at all. There was a floor of 40 here
# and measuring it is what removed it: the statistic does not separate the two
# populations. Compliant covers score 28.1 / 32.5 / 32.7 / 32.8 / 46.0 / 50.5 and the
# rejected ones score 24.4-32.1 — overlapping ranges, so a floor anywhere in there
# rejects covers that followed the brief, and no fix text would help them (rule 24).
# Even as an advisory it fired on 4 of 6 good covers, which is noise, not a signal.
#
# The painted covers score 45.7-69.8, i.e. above every SVG cover in the set — consistent
# with paint carrying more tonal range than flat fills, and still not a separation you
# could put a line through. So the number is printed on every run and nothing branches on
# it. The skill's actual instrument is a person looking at the PNG at 120px, and this
# keeps the number next to that person rather than pretending to replace them (rule 18).
SQUINT_W = 120

# MAX_PNG_BYTES — **advisory, and raised.** The SVG era's 2 MB came from the skill's
# Specifications table and never fired: flat vector covers ran 0.03-0.09 MB, twenty to
# sixty times under. Painted covers are photographic and 3 of 4 exceed it (2.96 / 4.59 /
# 5.56 MB; gpt-image-2's 1.61 MB is the only one that would pass).
#
# It cannot be a gate, for the reason rule 24 is about: **no retry message can make a
# diffusion model emit fewer bytes.** "Use fewer colours" is not a fix, it is a different
# cover. And there is no Pillow in this venv, so there is nothing to recompress with. The
# only real remedies are operator-side — pick a lower `resolution` tier, or a different
# `OPENROUTER_IMAGE_MODEL` — so the finding says that instead of asking the model for
# something it cannot do. 4 MB keeps the winner (2.96) clear while still reporting when a
# model change has quietly tripled the size of every course cover.
MAX_PNG_BYTES = 4 * 1024 * 1024

# ---- The palette table -----------------------------------------------------------
#
# The skill names colours ("Blue + Orange"); a prompt needs hexes, because "blue" to a
# diffusion model is a distribution and `#0B4FD8` is a request. Three per row is the
# skill's "Use 3 colors maximum" made exact, and the roles are named rather than listed:
# GROUND is the dominant field, ACCENT is the subject/light colour, NEUTRAL is the
# HEADLINE colour.
#
# The role assignment is the part that matters and the part that was once wrong. This
# comment used to read "every neutral-on-ground pair below clears WCAG AA — computed, not
# eyeballed"; computing it failed on THREE of the five rows — green-white 3.25:1,
# red-white 3.91:1, and yellow-black asking for white-on-yellow at 1.43:1, which is
# illegible. Accent and neutral were simply the wrong way round, and they are swapped
# here. `test_palette_contrast_is_computed_not_claimed` runs `contrast()` over every row
# so the claim cannot rot back into prose (rule 18's corollary).
#
# That assertion is now the ONLY thing holding the headline colour, and it is worth being
# clear that this is a downgrade accepted on purpose. In the SVG era a second check read
# the type's hex straight out of the source. A raster has no hexes, and the pixel-side
# proxy was measured and rejected — see TH-PALETTE in the module docstring: asked for
# indigo, all four models painted the neighbouring blue family. So the table's role
# assignment is art direction that the transcription gate confirms is *readable* without
# confirming it is the requested colour. Stated rather than papered over (rule 26).
#
# yellow-black is deliberately TWO colours, not three: #FFFFFF is unusable anywhere on a
# yellow ground, so both the subject and the type are #111111. The skill's pair is
# "Yellow + Black"; a third hex per row is a maximum, not a quota.
#
# The accent is a SUBJECT colour and is deliberately not held to 4.5:1 — blue-orange's
# orange-on-blue is 2.58:1 and reads plainly at 120px, checked by looking. WCAG's 3:1
# non-text minimum is about UI boundaries; importing it here would reject the row that has
# produced the best covers, so it is reported and not enforced.
#
# The skill's sixth row, White + Dark, is deliberately ABSENT: a near-white ground
# measures around 0.05 mean saturation against MIN_MEAN_SATURATION, so it cannot
# satisfy the gate, and it is precisely the pale look these covers were rejected for.
# Recorded in the spec too, so its absence reads as a decision (rule 26).
# (ground, accent, neutral) — neutral is the HEADLINE colour, and the measured
# neutral-on-ground / accent-on-ground ratios are in the comment beside each row.
PALETTES: dict[str, tuple[str, str, str]] = {
    "blue-orange": ("#0B4FD8", "#FF7A1A", "#FFFFFF"),    # type 6.72  shape 2.58
    "green-white": ("#00753F", "#111111", "#FFFFFF"),    # type 5.81  shape 3.25  (swapped)
    "yellow-black": ("#FFD400", "#111111", "#111111"),   # type 13.19 shape 13.19 (two-colour)
    "purple-yellow": ("#6A2CC4", "#FFD400", "#FFFFFF"),  # type 7.58  shape 5.30
    "red-white": ("#E01B24", "#111111", "#FFFFFF"),      # type 4.83  shape 3.91  (swapped)
}

_PALETTE_NAMES: tuple[str, ...] = tuple(PALETTES)


def palette_for(title: str) -> str:
    """Pick a palette row for a course, deterministically, from its title.

    This exists because letting the model choose was measured and it does not: **6 of the
    7 covers generated while the palette was a free choice came back blue-orange**, and a
    catalogue of near-identical blue-orange cards is the "boring" complaint at the level
    above a single cover. That kind of monotony is invisible to every gate here, because
    the agent only ever sees one course — so it is removed by construction rather than
    checked.

    Deterministic on the title, not random: the same course must get the same palette on a
    regenerate, or `POST /courses/{id}/thumbnail` becomes a slot machine and no two S3
    versions of one cover look related. Case- and whitespace-insensitive for the same
    reason.

    `hashlib`, NOT `hash()`. `hash()` on a `str` is salted per process (PYTHONHASHSEED),
    so it would give a different palette on every worker start — deterministic within one
    run, which is exactly the shape of bug that looks fine in a test and drifts in prod.
    Eight bytes rather than one, so the modulo bias against 5 rows is negligible instead
    of 52/256 vs 51/256.

    The spread is measured, not assumed, and the measurement is here because the first
    look at it was misleading: **12 titles put 6 on `purple-yellow` and 0 on
    `yellow-black`**, which reads like a broken hash. Over 200 title-shaped strings it is
    41/44/32/45/38 — chi-square **2.75** against 9.49 at 4 dof, i.e. indistinguishable
    from uniform. So the clumping was a 12-sample artefact, and anything done about it
    would be rule 25's trap: tuning a distribution against a sample too small to see it.
    A one-word change to a title moves the row, which is the property that matters.
    """
    key = " ".join(title.split()).lower()
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return _PALETTE_NAMES[int.from_bytes(digest[:8], "big") % len(_PALETTE_NAMES)]


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def _strs(value, cap: int, limit: int) -> list[str]:
    """A spine list field as clean strings, each capped, the list capped. Never raises.

    A spine is generated JSON, so a field can be absent, `null`, a bare string where a
    list was expected, or a list with a `None` in it. None of those are worth a traceback
    on the cover path — a thinner brief is a worse cover, a crash is no cover at all.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(" ".join(item.split())[:cap])
    return out[:limit]


def _one(*values, cap: int) -> str:
    """The first non-empty string among `values`, whitespace-collapsed and capped."""
    for v in values:
        if isinstance(v, str) and v.strip():
            return " ".join(v.split())[:cap]
    return ""


# The order fields are given up when a spine renders longer than MAX_CURRICULUM_CHARS.
# Uniform across modules by field, NOT truncation of the module list: dropping the tail
# would hide a course's later half entirely, and the later modules are exactly where a
# course's distinctive material lives (module 1 of everything is "the fundamentals").
# So every module keeps contributing and the *depth* per module shrinks together.
#
# Ordered by how much each field helps choose a subject, least first. `seeds` go first
# because they are analogies and TH-SUBJECT forbids painting an analogy; `concepts` are
# never dropped, because they are the whole reason this exists.
_TRIM_ORDER = ("seeds", "description", "why", "builds", "stuck")


def load_brief(spine_path: Path) -> dict:
    """Everything about the course that a cover subject could be chosen from.

    Two spine shapes, both live and both handled. Measured across the 34 real spines on
    this machine (364 module dicts): 32 use `modules` with `module_title` and nest the
    checkpoint trio under `terminal_checkpoint`; 2 use `checkpoints` with
    `milestone_title` and put `struggle_hook` / `why_it_matters` /
    `proof_of_competency` at the module's OWN top level (e.g.
    `memebu-lesson-planner/output/test_v2_neuro/course_spine.json`). Reading only one
    depth silently yields an empty checkpoint for the other shape, which looks exactly
    like a spine that has none.

    `modules` stays a list of plain title strings, because `generate_thumbnail` prints a
    count from it and the caller has never wanted more; the depth lives in `curriculum`.
    `concepts` is the flat union, and it is what `parse_art_direction` checks a `SOURCE:`
    citation against — one place, so the prompt and the gate cannot disagree about what
    this course teaches.
    """
    data = json.loads(spine_path.read_text(encoding="utf-8"))
    raw = data.get("modules") or data.get("checkpoints") or []
    if not isinstance(raw, list):
        raw = []

    curriculum: list[dict] = []
    for m in raw[:MAX_MODULES]:
        if not isinstance(m, dict):
            continue
        # The trio at both depths, flat first. `or {}` and not `.get(..., {})`: a spine
        # with `"terminal_checkpoint": null` is real and `.get` returns the null.
        tc = m.get("terminal_checkpoint") if isinstance(m.get("terminal_checkpoint"), dict) else {}
        title = _one(
            m.get("module_title"), m.get("milestone_title"), m.get("title"),
            m.get("checkpoint_title"), cap=200,
        )
        entry = {
            "title": title,
            "description": _one(m.get("module_description"), cap=MAX_MODULE_DESC),
            "concepts": _strs(m.get("key_concepts"), MAX_CONCEPT_CHARS, MAX_CONCEPTS_PER_MODULE),
            "builds": _one(
                m.get("proof_of_competency"), tc.get("proof_of_competency"),
                cap=MAX_CHECKPOINT_CHARS,
            ),
            "why": _one(m.get("why_it_matters"), tc.get("why_it_matters"), cap=MAX_CHECKPOINT_CHARS),
            "stuck": _one(
                m.get("struggle_hook"), tc.get("struggle_hook"), cap=MAX_CHECKPOINT_CHARS
            ),
            "seeds": _strs(m.get("narrative_seeds"), MAX_SEED_CHARS, MAX_SEEDS_PER_MODULE),
        }
        if title or entry["concepts"]:
            curriculum.append(entry)

    def size(rows: list[dict]) -> int:
        return sum(
            len(r["title"]) + len(r["description"]) + len(r["builds"]) + len(r["why"])
            + len(r["stuck"]) + sum(map(len, r["concepts"])) + sum(map(len, r["seeds"]))
            for r in rows
        )

    trimmed: list[str] = []
    for field in _TRIM_ORDER:
        if size(curriculum) <= MAX_CURRICULUM_CHARS:
            break
        for r in curriculum:
            r[field] = [] if isinstance(r[field], list) else ""
        trimmed.append(field)
    # Concepts are never dropped wholesale, but a pathological spine (300 modules of
    # 8 concepts) still has to fit. Shrink the per-module allowance instead of losing
    # whole modules, and report it: a brief that was cut must not read as a whole one.
    per = MAX_CONCEPTS_PER_MODULE
    while size(curriculum) > MAX_CURRICULUM_CHARS and per > 1:
        per -= 1
        for r in curriculum:
            r["concepts"] = r["concepts"][:per]
        trimmed.append(f"concepts>{per}")

    return {
        "title": (data.get("course_title") or spine_path.parent.name).strip(),
        "description": (data.get("course_description") or "").strip()[:900],
        "audience": (data.get("target_audience") or "").strip()[:300],
        "duration": (data.get("estimated_total_duration") or "").strip(),
        "modules": [r["title"] for r in curriculum if r["title"]],
        "objectives": _strs(data.get("learning_objectives"), 200, MAX_OBJECTIVES),
        "prerequisites": _strs(data.get("prerequisites"), 160, MAX_PREREQUISITES),
        "curriculum": curriculum,
        # The flat union, deduplicated case-insensitively but keeping first spelling —
        # this is what a `SOURCE:` citation is checked against, so it has to be the same
        # set of words the prompt showed the model.
        "concepts": list(
            {c.lower(): c for r in curriculum for c in r["concepts"]}.values()
        ),
        "trimmed": trimmed,
    }


# ---------------------------------------------------------------------------
# The design brief — loaded from disk, not written here
# ---------------------------------------------------------------------------

# The sections of the vendored skill that apply to a drawn course cover. Kept as a
# whitelist rather than a blacklist so that a section ADDED upstream is ignored until
# someone reads it, instead of arriving in a prompt unreviewed.
_SKILL_KEEP = (
    "Specifications",
    "The 120px Test",
    "Safe Zones",
    "Color Strategy",
    "Text on Thumbnails",
    "Thumbnail Checklist",
    "Common Mistakes",
)
# Why each of the rest is dropped, kept next to the whitelist so the two cannot drift
# apart in someone's memory. Not code — documentation with a test asserting it covers
# every heading in the file.
#
# Every reason here was RE-EXAMINED at the pivot to an image model, because two of them
# had been written about SVG and one of them was about spelling — both premises that no
# longer hold, and a stale reason is how a section stays dropped for a reason that
# evaporated (rule 26 from the other end). Two changed, and the third was measured:
_SKILL_DROP = {
    # Was "...and diffusion cannot spell a title". That clause is now measured false and
    # is deleted; what remains is the part that was always the real reason.
    "Quick Start": "`belt app run` — the inference.sh CLI, which we do not have; we call OpenRouter directly",
    # Was "a photographed face cannot live in an SVG cover". An image model paints faces
    # perfectly well, so that reason is gone and this is now a DECISION rather than a
    # limitation: a synthesised face on a course cover asserts an instructor who does not
    # exist, and the section's own table is tuned for reaction/unboxing CTR ("Surprise/
    # shock — Highest"), which is not the register of a course catalogue.
    "Face Expression Psychology": "we will not paint a human face — it implies an instructor who does not exist",
    # Was "four diffusion prompts, all describing photographs". Post-pivot that is the
    # section that *should* have become relevant, so it was measured rather than assumed:
    # after `_FENCE` strips the code blocks it is **98 characters — four empty `###`
    # headings**, because every word of it is inside the fences. Un-stripping them is
    # possible and still declined: the four prompts are stock-photo register ("overhead
    # flat lay of organized workspace", "two products facing each other with sparks"),
    # which is exactly what TH-STOCK forbids, and they carry `belt app run` with them.
    "Thumbnail Patterns by Content Type": "100% fenced — stripping the fences leaves 4 empty headings; the prompts inside are stock-photo register (TH-STOCK)",
    "A/B Testing": "needs two published variants and view data; there is no such loop here",
    "Related Skills": "install instructions for other skills",
}
_FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def load_skill(path: Path | None = None) -> str:
    """The vendored skill, filtered down to the sections that apply to a course cover.

    Injecting it whole would tell the model to run `belt login` and describe a
    photograph, so sections are whitelisted by heading and every fenced block is
    stripped (the fences are all shell commands or an ASCII diagram whose bullets say
    the same thing).

    Raises on a missing whitelisted heading. That is the important behaviour: if
    upstream renames "Color Strategy", the alternative is a brief that silently loses
    its colour rules while every test stays green — rule 26, which is how an
    unenforced `font-family` rule shipped serif diagrams.
    """
    text = (path or config.THUMBNAIL_SKILL).read_text(encoding="utf-8")
    text = _FRONTMATTER.sub("", text)  # `allowed-tools: Bash(belt *)` must not survive

    # Split on level-2 headings, keeping each heading with its body.
    parts = re.split(r"^## +(.+?)\s*$", text, flags=re.MULTILINE)
    sections = dict(zip(parts[1::2], parts[2::2]))

    missing = [h for h in _SKILL_KEEP if h not in sections]
    if missing:
        raise RuntimeError(
            f"{(path or config.THUMBNAIL_SKILL)} no longer has the section(s) "
            f"{missing!r} — the vendored skill changed shape upstream. Read the new "
            "version and update _SKILL_KEEP / _SKILL_DROP; do not let the brief ship "
            "without these rules."
        )

    out = ["The design authority below is the `youtube-thumbnail-design` skill."]
    for heading in _SKILL_KEEP:
        body = _FENCE.sub("", sections[heading]).strip()
        out.append(f"## {heading}\n\n{body}")
    return "\n\n".join(out)


def _build_design() -> str:
    """The skill, then our course deltas. Both from disk; neither is written in code."""
    return f"{load_skill()}\n\n---\n\n{config.THUMBNAIL_SPEC.read_text(encoding='utf-8')}"


_DESIGN = _build_design()


# ---------------------------------------------------------------------------
# The two galleries — STYLE (how it is drawn) and LAYOUT (how it is organised)
# ---------------------------------------------------------------------------
#
# The layout value that means "no structure": one object, close, filling the frame, lit,
# with no reference file injected and no labels. It is not a fallback — it is the shape of
# every cover on disk that works, and keeping it reachable is what stops "make it
# informative" from throwing that away.
SINGLE_SUBJECT = "single-subject"

# At most this many labels, of at most this many words each. Both are bounds on the
# TRANSCRIPTION gate rather than on taste: every declared label is a word the vision model
# will read back off the pixels and TH-TITLE must then account for, so six three-word labels
# is already 18 tokens of read-back surface against the headline's six. Small numbers,
# because the failure they bound is a cover shipping with its headline garbled.
MAX_LABELS = 6
MAX_LABEL_WORDS = 3

#
# Why these exist at all: until now the entire style system was ONE SENTENCE of prompt
# ("rich painterly digital illustration, dramatic rim lighting"), so every course in every
# subject came back the same oil painting of one object, and the covers were rejected for
# exactly that. Two vendored skills supply the missing dimensions — `cover-image` 20 styles,
# `infographic` 20 layouts — see `config.THUMBNAIL_STYLES` / `THUMBNAIL_LAYOUTS` and the
# PROVENANCE.md beside each.
#
# ONE gallery owns each dimension. Both skills ship a style gallery and they do not agree:
# measured with `diff`, `chalkboard.md` is byte-identical across the two while `pixel-art.md`
# DIFFERS. Two files with one name and different contents is rule 23's divergence, so
# `infographic`'s 17 styles are declined wholesale rather than merged.
#
# The tables below are OURS, not a paste. Three reasons, each one a measured trap:
#
#   1. The skill's own auto-selection table points at a declined style in 11 of its 20 rows
#      (`elegant`, `minimal`, `warm`, `notion`, `vintage`, ...). Pasting it would recommend
#      styles the allow-list rejects, i.e. build a retry loop out of our own documentation.
#   2. `cover-image/SKILL.md:271` says "visual metaphors work better than literal
#      representations" — the exact inverse of what this project measured, where every
#      invented metaphor failed and every obvious artifact worked (see TH-SUBJECT). A skill
#      may not overrule a finding from this corpus.
#   3. Only 9 of the 20 styles are usable here, and the reason is a number, not taste — see
#      STYLES_DECLINED.
#
# `<style>` -> the one-line description the model chooses from. One line each, in the CACHED
# system half; the detailed reference file is loaded for the ONE style picked. All 40 files
# would be ~35k tokens to use one of them, which is the bound `mlai-games`' registry hit.
STYLE_GALLERY: dict[str, str] = {
    "bold-editorial": "magazine cover impact, dramatic scale, high contrast",
    "chalkboard": "chalk drawing on a board, imperfect hand-drawn line, chalk dust",
    "dark-atmospheric": "cinematic, glowing accents, deep shadow",
    "editorial-infographic": "magazine explainer, callouts and numbered parts",
    "pixel-art": "retro 8-bit, hard pixel grid, limited palette",
    "retro": "halftone dots, vintage badges, aged print texture",
    "sketch-notes": "hand-drawn marker notes, arrows and annotations",
    "vector-illustration": "flat vector, heavy black outlines, bold shapes",
}
# Declined, with the reason kept BESIDE the allow-list so the two cannot drift apart in
# someone's memory — the same convention as `_SKILL_DROP`, and a test asserts this map plus
# STYLE_GALLERY covers every style file on disk, so an upstream addition fails loudly
# instead of arriving unreviewed.
#
# **The criterion is measured, and my first pass at it was wrong.** I curated these by
# reading the style NAMES and dropping the ones that sounded pale. Then I read the files:
# 10 of the 13 I had kept declare a WHITE OR CREAM background (`flat-doodle` #FFFFFF,
# `playful` #FFFBEB, `warm` #FFFAF0, `fantasy-animation` #E8F4FC). That matters because the
# palette table already carries the measurement — see the note above PALETTES on why the
# skill's sixth row was left out: "a near-white ground measures around 0.05 mean saturation
# against MIN_MEAN_SATURATION, so it cannot satisfy the gate". A light-ground style is not a
# preference we are declining, it is a cover that fails a hard gate four times.
#
# So the real question is: does the style's identity survive being drawn on one of the five
# SATURATED grounds in PALETTES? For a style that is a way of MAKING MARKS — halftone,
# chalk, pixels — yes, and canonically (chalk on #00753F is a school board). For a style
# whose identity IS its pale light, no, and overriding its ground leaves nothing of it.
#
# That question is necessary and it is NOT sufficient, which is what the first entry below
# records: `blueprint` passes it easily — a blueprint on #0B4FD8 is a blueprint, and it was
# kept on exactly that reasoning — and it still had to be declined, on live covers, for a
# reason no reading of the file predicted. Colour was the only axis this list had when it was
# written because colour was the only axis with covers behind it (rule 25).
STYLES_DECLINED: dict[str, str] = {
    # Declined on LIVE evidence rather than on its file, and it is the only entry here that was
    # kept first and measured second — the plan that added this gallery named it "the one to
    # watch". Five covers chose it across four runs (4 Sep 2026) and **all five came back with
    # garbled pseudo-measurements** stamped over the subject: 20 tokens on `python-oop`
    # (`STANETATG`, `PYITINBER`, `ANPYSTIRRY`, `11:60`), 14 on `recursion` (`1414.4`, `2841.1AM`,
    # `90160`), 10 with a Cyrillic `Б` in an earlier run. The critique named it unprompted twice
    # — "the dimension labels and text on the boxes are garbled, illegible pseudo-text" — and
    # once went further, to "generic blueprint-style translucent boxes with arrows and gibberish
    # labels, not a clearly identifiable object", which is the ORIGINAL complaint about this
    # project's covers reproduced by a style added to fix it: boxes and lines.
    #
    # The mechanism is in its own reference file: `Visual Elements` asks for "dimension lines and
    # measurement indicators", so every blueprint cover is an object PLUS an annotation layer,
    # and the annotation layer is where an image model invents letters. Bounding the mark count
    # in the prompt was tried first and did not hold — `recursion`'s art direction asked for "a
    # stamped frame number along each block's edge" and got 14 — because the style file asks for
    # the annotations independently of what the art direction asks for. Declining the style is
    # the lever; editing the vendored file is not, it stays verbatim.
    "blueprint": "5 of 5 live covers came back with garbled pseudo-measurements over the subject; its own Visual Elements list asks for dimension annotations, so the gibberish layer is the style rather than the art direction, and one critique read it back as 'boxes with gibberish labels' — the complaint this gallery exists to fix",
    # Identity is the soft light background; on a saturated ground nothing of the style is
    # left. Measured backgrounds in brackets.
    "fantasy-animation": "identity is its soft light (#E8F4FC sky / #FFF8E7 cream); nothing of it survives a saturated ground",
    "playful": "light cream ground (#FFFBEB) is the whole register, and 'cute' is not a course catalogue's voice",
    "warm": "cream/peach ground (#FFFAF0) is the identity; also the least distinguishable from the painterly default we are replacing",
    "flat-doodle": "pastel on clean white (#FFFFFF); pastel over a saturated ground is the muddy mass TH-ACCENT exists to catch",
    # Pale by design: cannot reach MIN_MEAN_SATURATION, and precisely the look the covers
    # were rejected for. A per-style floor instead would be a threshold with zero covers
    # behind it — rule 25's trap, the one that once flagged 76% of this project's diagrams.
    #
    # **These reasons survived MIN_MEAN_SATURATION moving 0.35 -> 0.10, and with a wider
    # margin than they had before.** Checked rather than assumed, because a decline whose
    # stated reason has gone stale is rule 26's silent regression: the six pale near-white
    # SVG covers in `output/thumbnails/rejected-original/` measure **0.03-0.06**, so a
    # near-white ground fails even the re-sited floor — by 1.7x rather than by 6x. What the
    # re-siting removed was the false positives on DARK grounds (chalkboard at 0.13), which
    # is the opposite end and touches none of these.
    "minimal": "ultra-clean and near-white by definition; cannot reach MIN_MEAN_SATURATION",
    "elegant": "understated low-chroma; same floor, and it is the default that produced the rejected covers",
    "notion": "grey SaaS dashboard chrome; low chroma, and TH-STOCK bans the UI register outright",
    "watercolor": "soft low-chroma washes; cannot reach MIN_MEAN_SATURATION",
    "nature": "earthy muted palette; same floor",
    "vintage": "aged paper ground; same floor. Worth RE-TESTING later — `silk-road` is the best cover on disk at 49.5% accent and is vintage in feel, but painterly-vintage, not this file's aged-paper scheme",
    # Not about colour at all.
    "intuition-machine": "its defining feature is bilingual Chinese labels, which the transcription gate would read as unaccounted text",
}

# `<layout>` -> what shape of curriculum it fits. Layout is INFORMATION STRUCTURE, which is
# the dimension the word "informative" in the complaint was actually about, and it is
# choosable from data `render_curriculum` already prints.
#
# `single-subject` is ours, not from the gallery, and it is load-bearing rather than a
# fallback: it means today's behaviour — one object, lit, no layout file injected, no labels.
# **All four covers on disk that WORK are single subjects.** Discarding that to chase
# "informative" would repeat the change that made these covers worse the last time.
LAYOUT_GALLERY: dict[str, str] = {
    "single-subject": "no structure — one object, close, filling the frame, lit. Use when the course has one central artifact",
    "linear-progression": "a sequence: timelines, step-by-step, a course whose modules run in order",
    "hierarchical-layers": "pyramids, concentric rings, levels — a course that builds upward",
    "hub-spoke": "one central concept with related items around it",
    "tree-branching": "categories and taxonomies — kinds of a thing",
    "structural-breakdown": "exploded or cut-away view with labelled parts — an anatomy",
    "winding-roadmap": "a journey with milestones along it",
    "circular-flow": "cycles and recurring processes",
    "iceberg": "what is visible above versus what is hidden below",
    "binary-comparison": "two things set against each other: before/after, A versus B",
    "bento-grid": "several distinct topics as panels — a course that is a survey",
}
LAYOUTS_DECLINED: dict[str, str] = {
    # The label cap is MAX_LABELS; a layout that needs more text than that cannot be
    # satisfied, and an unsatisfiable option is worse than a missing one.
    "comparison-matrix": "a grid of cells needs one label per cell, far past MAX_LABELS",
    "periodic-table": "same — dozens of cells, every one labelled",
    "dashboard": "metric tiles are numbers and captions, and TH-STOCK bans the UI register",
    "comic-strip": "narrative panels need sentences, not 3-word labels",
    "story-mountain": "same, plus it is a plot shape and a curriculum is not a plot",
    # Register, not capacity.
    "funnel": "conversion/marketing shape; a course is not a sales funnel",
    "bridge": "problem-solution marketing shape, and 'gap-crossing' is an abstraction not an artifact",
    "isometric-map": "spatial relationships between places; a curriculum has no geography",
    # The measured failure mode this project already has a name for.
    "venn-diagram": "two overlapping abstractions IS the 'two abstract things arranged so their relationship is the picture' failure the spec names",
    "jigsaw": "interlocking-puzzle-piece metaphor — TH-SUBJECT bans it explicitly, by name",
}

# Which sections of a reference file reach the image model, and which do not.
#
# Same shape as `_SKILL_KEEP` / `_SKILL_DROP` and for the same reason (rule 26): a whitelist,
# so a section ADDED upstream is ignored until someone reads it, and a RAISE when a required
# heading disappears, so a rename fails loudly instead of silently shipping a cover with no
# style rules while every test stays green.
#
# **Required vs optional is measured, not guessed — and this is the second thing my first
# pass got wrong.** I wrote the whitelist from reading `chalkboard.md`, which has `Design
# Aesthetic`, `Background` and `Style Rules`. It is the ONLY one of the nine that does: the
# other eight carry exactly `Color Palette | Visual Elements | Typography | Best For`. A
# required-heading list taken from that one sample would have raised on 8 of 9 styles. Rule
# 25 in one line: read all of them, not the first one.
_STYLE_KEEP = ("Visual Elements",)
_STYLE_OPTIONAL = ("Design Aesthetic", "Style Rules")
_STYLE_DROP = {
    # **Dropped on a measurement, and it is the one section that looked most obviously
    # useful.** I had it in the keep list. Then I read all nine: SIX of the nine mandate a
    # typeface that contradicts `_TEXT_CLAUSE`'s "heavy condensed sans-serif", and FOUR
    # mandate specifically the letterforms `TH-GLYPH` exists to catch — `retro` "vintage-style
    # hand lettering", `sketch-notes` "bold hand-written marker font", `chalkboard`
    # "hand-drawn chalk lettering … imperfect baseline", `pixel-art` "pixelated bitmap font,
    # chunky blocky letterforms". PROVENANCE.md already records the same defect one size
    # larger, as the reason `references/base-prompt.md` is declined wholesale: a hand-lettered
    # headline is what the transcription gate has the hardest time reading back.
    #
    # `_TEXT_CLAUSE` is appended after the style file, so ours would probably win on
    # ordering — but "probably wins because it comes last" is not a contract, and resolving a
    # direct contradiction is left to the image model, which is the measured failure
    # `compose_text_free_prompt` was rewritten for one clause over. So the style owns the
    # MARKS and the SHAPES; the letterforms stay entirely with the clause the gate reads back.
    "Typography": "6 of 9 contradict `_TEXT_CLAUSE`; 4 mandate the hand-lettered or bitmap forms TH-GLYPH fires on",
    # PALETTES stays the ONLY source of colour. Two palettes reaching one image model is a
    # contradiction it resolves however it likes, and the assigned row is what TH-CONTRAST,
    # TH-ACCENT, TH-FLAT and the headline colour are all computed against. So the style
    # contributes its MARKS and its TYPE, and the palette contributes its colours.
    "Color Palette": "PALETTES owns colour; a second palette in the same prompt is a contradiction",
    "Background": "same — the ground colour is assigned per course by `palette_for`",
    "Best For": "selection metadata, and selection has already happened by the time this is loaded",
}
_LAYOUT_KEEP = ("Structure", "Visual Elements", "Text Placement")
_LAYOUT_OPTIONAL = ("Variants",)
_LAYOUT_DROP = {
    "Best For": "selection metadata; the model has already chosen by the time this loads",
    # This one is a real trap rather than noise: every layout file recommends `infographic`'s
    # OWN styles (`craft-handmade`, `aged-academia`, ...), none of which is in STYLE_GALLERY.
    # Injecting it would tell the model to use a style the allow-list rejects.
    "Recommended Pairings": "names infographic's own 17 styles, every one of them declined — it would recommend a style `check_style` then refuses",
}


def _load_reference(
    path: Path,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    label: str,
) -> str:
    """One vendored gallery file, filtered to the sections that reach an image model.

    Shares `load_skill`'s contract deliberately: whitelist by heading, raise on a missing
    REQUIRED heading. What is different is `optional` — the kept style files genuinely do
    not have the same headings as each other (measured above), so "absent" and "renamed"
    have to be distinguishable, and only the second is an error.

    The file's first line after the `# title` is kept: it is the style's own thesis
    ("Black chalkboard background with colorful chalk drawing style") and it sits above
    every heading, so a section-only reader would drop the single most useful sentence in the
    file.
    """
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^## +(.+?)\s*$", text, flags=re.MULTILINE)
    sections = dict(zip(parts[1::2], parts[2::2]))

    missing = [h for h in required if h not in sections]
    if missing:
        raise RuntimeError(
            f"{path} no longer has the section(s) {missing!r} — the vendored {label} "
            "changed shape upstream. Read the new version and update the KEEP/OPTIONAL "
            "lists; do not let a cover ship with its design rules silently absent."
        )

    # Everything before the first `## ` heading, minus the `# name` line: the thesis.
    head = [
        ln.strip()
        for ln in parts[0].splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    out = [" ".join(head)] if head else []
    for heading in required + optional:
        body = sections.get(heading)
        if body is None:
            continue
        body = _FENCE.sub("", body).strip()
        if body:
            out.append(f"{heading}: {body}")
    return "\n".join(out).strip()


def load_style(name: str) -> str:
    """The chosen style's reference file, filtered. Raises on an unknown name."""
    if name not in STYLE_GALLERY:
        raise KeyError(name)
    path = config.THUMBNAIL_STYLES / "references" / "styles" / f"{name}.md"
    return _load_reference(path, _STYLE_KEEP, _STYLE_OPTIONAL, "style")


def load_layout(name: str) -> str:
    """The chosen layout's reference file, filtered.

    `single-subject` is ours and has no file — it means "no structure", so there is nothing
    to inject and returning `""` is the correct answer rather than a missing-file error.
    """
    if name == SINGLE_SUBJECT:
        return ""
    if name not in LAYOUT_GALLERY:
        raise KeyError(name)
    path = config.THUMBNAIL_LAYOUTS / "references" / "layouts" / f"{name}.md"
    return _load_reference(path, _LAYOUT_KEEP, _LAYOUT_OPTIONAL, "layout")


def _gallery_table(gallery: dict[str, str]) -> str:
    """One line per entry. The whole gallery is always present, so a choice is never
    withheld — the same reason `games.py`'s catalogue is uncut: ranking may order the
    options but must never be able to veto one."""
    width = max(len(k) for k in gallery)
    return "\n".join(f"  {k.ljust(width)}  {v}" for k, v in gallery.items())


# Content signal -> style. REBUILT, not pasted, and this is the concrete reason the tables
# above had to be ours: the skill's own `Auto Style Selection` table has 20 rows and **11 of
# them point at a style STYLES_DECLINED rejects** — `Education, classroom, tutorial` sends you
# to `chalkboard` (fine) but `Simple, zen, focus` sends you to `minimal`, `Fun, easy,
# beginner` to `playful`, `Business, professional, strategy` to `elegant`. Pasting it would
# have the system prompt recommending values `check_style` then refuses, i.e. a retry loop
# built out of our own documentation. A test asserts every value here is in STYLE_GALLERY.
#
# Rows whose skill counterpart named a kept style keep the skill's signal words; the four
# whose counterpart named a declined one are written from what a COURSE looks like, which is
# the thing the skill could not know.
#
# The engineering row used to send that signal to `blueprint`, which is the obvious answer and
# is now declined on live evidence (see STYLES_DECLINED — 5 of 5 covers came back with garbled
# pseudo-measurements). It goes to `vector-illustration` because that is the kept style that can
# render a built thing with NO annotation layer, which is where the gibberish came from.
#
# **`editorial-infographic` and `sketch-notes` are the two to watch next, and they are kept
# deliberately unwatched-but-named rather than declined pre-emptively.** Their gallery lines are
# "callouts and numbered parts" and "arrows and annotations" — the same annotation-heavy shape as
# blueprint's — but no live cover has chosen either, so declining them would be reasoning where
# the blueprint decision was measuring. If a cover picks one and the critique reports garbled
# marks, this is the paragraph that says so first.
_STYLE_SIGNALS = (
    ("architecture, system design, engineering, how a thing is built", "vector-illustration"),
    ("one dramatic claim, a manifesto, a single number that matters", "bold-editorial"),
    ("classroom teaching, worked examples, derivations, a taught subject", "chalkboard"),
    ("cinematic, high-stakes, deep focus, something hidden or vast", "dark-atmospheric"),
    ("science or technology explainer, research, named parts", "editorial-infographic"),
    ("gaming, retro computing, low-level or byte-level programming", "pixel-art"),
    ("history of a field, pop culture, 80s/90s, anything with lineage", "retro"),
    ("tutorial, walkthrough, note-taking, beginner-friendly", "sketch-notes"),
    ("bold flat shapes when the cover must punch at thumbnail size", "vector-illustration"),
)


def _signal_table() -> str:
    width = max(len(sig) for sig, _ in _STYLE_SIGNALS)
    return "\n".join(f"  {sig.ljust(width)}  -> {name}" for sig, name in _STYLE_SIGNALS)


# The reply format Claude must produce. Two fields, because the headline is not merely
# part of the art direction — it is the string the transcription gate compares against, so
# it has to be readable by code and not inferred from a paragraph of prose. A run that
# cannot say what it asked for cannot check whether it got it.
_REPLY_FORMAT = f"""\
REPLY FORMAT — exactly this, nothing before or after:

SUBJECT: <the one concrete thing you are going to draw, in a few words>
SOURCE: <the module title or key concept from the COURSE block above that this subject
         comes from, copied VERBATIM from the list. Machine-checked against the
         curriculum before any picture is generated — an invented source is rejected>
MARKS: <the markings this object carries in real life — the digits on the board, the
         notation on the score, the numerals on the dial, the engraving on the coin — or
         the single word `none` if the object reads as itself with nothing written or
         drawn on it (a crate of oranges, a stack of coins). Machine-checked before any
         picture is generated: whatever you name here must also be described in PROMPT>
STYLE: <exactly one name from the STYLE GALLERY above, copied character for character>
LAYOUT: <exactly one name from the LAYOUT GALLERY above, copied character for character>
LABELS: <the words to paint ON the picture besides the headline — at most {MAX_LABELS} of
         them, separated by `|`, at most {MAX_LABEL_WORDS} words each — or the single word
         `none`. Each one is machine-checked against the curriculum above before any
         picture is bought, so every label must be curriculum text: a module title, a key
         concept, or a phrase copied out of one. `none` is correct and expected whenever
         LAYOUT is `{SINGLE_SUBJECT}`, and it is always an acceptable answer>
HEADLINE: <the words to paint on the cover, uppercase, at most {MAX_TEXT_WORDS} words>
PROMPT:
<one paragraph of art direction for a text-to-image model, then a blank line, then a
second paragraph on composition. Plain prose. No bullet points, no markdown, no code
fences, no key: value lines.>

The HEADLINE line is machine-read and compared, letter for letter, against what a vision
model transcribes from the finished picture. So write it exactly as it must appear, and
repeat it verbatim inside PROMPT where you ask for the text to be painted.

The HEADLINE must also share a significant word with the course title above — a student
seeing the card has to know which course it is. `SUPPLY MEETS DEMAND` for a course called
`Economics for Developers` is rejected for this reason; `ECONOMICS FOR DEVELOPERS` and
`ECONOMICS, MADE MECHANICAL` both pass.

The MARKS you name are what makes the object legible as itself, so they must be in the
PROMPT as something painted: not "a price board" but "a price board, each flap showing a
crisp white numeral". Prefer figures, notation and symbols over words — an image model
asked for running prose on an object invents letters and paints visible gibberish. The
markings themselves are not judged: the transcription check reads the finished picture and
sorts what it finds into text ADDED on top of the image and writing that belongs to a
depicted object, and only the first group is compared. So a stencil, a dial figure or a
part number costs you nothing, while a caption, subtitle, tagline, watermark, logo wordmark
or signature fails a cover that is otherwise right.

The LABELS are the exception to that, and they are the reason this cover can say anything
at all. Declare them and they become legal text; leave them at `none` and the picture is
one object with nothing written on it but the headline. Whatever you declare must also
appear in PROMPT as text you are asking to be painted, in the place the LAYOUT puts it —
declaring a label and not asking for it wastes the only thing that makes a structured
cover readable.
"""


_GALLERIES = f"""\
STYLE GALLERY — pick exactly one for STYLE. This is HOW the cover is drawn.

{_gallery_table(STYLE_GALLERY)}

Which one, by what the course is about — a starting point, not a rule:

{_signal_table()}

A course whose subject has a canonical visual register should take it: a course on
low-level programming is `pixel-art`, a taught derivation is `chalkboard`. Where nothing is
canonical, pick the register a student would find most inviting for this particular subject,
and do not default to the same one every time.


LAYOUT GALLERY — pick exactly one for LAYOUT. This is HOW the cover is ORGANISED, and it is
a claim about the shape of the CURRICULUM, so read the COURSE block below before choosing.

{_gallery_table(LAYOUT_GALLERY)}

`{SINGLE_SUBJECT}` is the right answer whenever the course has one obvious central
artifact, and it is not a lesser choice — it is the shape of every cover this project has
made that works. Choose a structured layout only when the curriculum genuinely has that
shape: {len(LAYOUT_GALLERY) - 1} of these say something specific about a course, and a
layout that does not match the spine is a cover that lies about it.

A structured layout is still a PICTURE. `linear-progression` is not a row of boxes with
arrows — it is four real objects in a row, receding, lit, with a short label under each.
`structural-breakdown` is not a labelled diagram — it is the object itself, opened up, with
its parts named. If your prompt would produce boxes and arrows floating on a background,
you have written a diagram and the cover has failed.
"""

_ART_RULES = """\
HOW TO WRITE THE PROMPT

You are art-directing a text-to-image model, not drawing. Describe a PICTURE — a subject,
a light source, a material, a mood — in the language a painter would use. The single most
common failure is describing a diagram instead: a prompt that says "a labelled flowchart
of the process" produces boxes and arrows, which is exactly what this cover is replacing.

1. TH-GROUND — the TOPIC must come from THIS COURSE'S CURRICULUM, not from its field in
   general. The COURSE block below lists every module and the concepts each one teaches.
   Pick one module or one concept, copy it into SOURCE verbatim — it is checked against
   the list before any picture is bought, so an invented one costs a wasted turn — and
   then do rule 2 with it. A cover for a course teaching "Production Possibility
   Frontier" and "Comparative Advantage" that shows generic cracked stone with fire inside
   is the failure this rule exists for: it was drawn, it passed every other check, and it
   says nothing about the course.
2. TH-SUBJECT — now name the OBJECT. Ask: what does a practitioner of the thing I picked
   physically handle, trade, read, or build with? Draw THAT object, close, filling the
   frame, lit. This is the whole difference between a cover that works and one nobody can
   read, measured on this project's own output:
     · supply and demand → a crate of oranges at a night market       ← works
     · compound interest → a stack of gold coins                      ← works
     · reading music     → an open score on a wooden stand            ← works
     · the Silk Road     → a rope-bound bale of silk, scrolls, vials   ← works
     · market equilibrium → an invented split-flap board              ← unrecognisable
     · instantiation      → an invented brass vault door              ← unrecognisable
   The four that work are the field's OBVIOUS artifact, drawn plainly. The two that fail
   are props invented to stand for an abstraction. When the topic is abstract, do not
   invent a symbol for it — go down one level to the physical thing a student of it holds.
   Never a metaphor for learning (no lightbulbs, ladders, glowing brains, rocket ships,
   jigsaw pieces) and never an abstraction as the subject ("data", "growth", "knowledge").
   A diagram IS allowed when the diagram is the artifact — a printed score, a chart on
   paper, a schematic on a drafting table, a plotted curve on graph paper — because that
   is a physical object a practitioner reads. What is banned is a diagram drawn as the
   picture's own structure: boxes and arrows floating on a background, with nothing
   depicted holding them.
3. TH-TRUE — the picture must be TRUE, not merely plausible. A curve drawn as a peak
   where the real one has a minimum is worse than no curve. If you are not certain of the
   shape of a thing, choose a different subject you are certain of.
4. TH-STOCK — no stock-photo register. Not a person at a laptop, not a flat lay of a desk
   with a coffee cup and notebook, not hands typing, not a logo or a mascot, not two
   products with sparks between them, not motivational lens flare. This is an image
   model's default and it must be refused explicitly. Note what this rule does NOT ban:
   the field's own ordinary subject matter. The obvious object IS the right answer (rule
   2) — "stock" here means the generic office photograph, not a well-known artifact.
5. TH-STYLE / TH-LAYOUT — choose the REGISTER and the STRUCTURE, from the two galleries
   below. Say the MEDIUM and the LIGHT in the prompt itself, because saying nothing gets a
   photograph; but say the medium the STYLE you picked calls for, not the same one every
   time. Until this rule existed the entire style system was one sentence asking for "rich
   painterly digital illustration, dramatic rim lighting", and the measured result was that
   every cover of every course in every subject came back the same oil painting of one
   object — which is what got them rejected. A course on 8-bit programming should look
   nothing like a course on the Silk Road. The style's own reference file is appended to
   your prompt automatically once you have named it, so name it and then write prose that
   agrees with it.
6. The PALETTE, applied in this direction and not the other: the SUBJECT and the light on
   it carry the bright accent colour, and the dark ground colour is the field BEHIND it —
   a single warm pool of light against a cool dark surround. Do not name the dark colour
   as the subject's material. A near-black object on a dark field is the measured failure:
   it produced a cover with almost no bright saturated pixels in it, which reads as a
   muddy mass at card size however carefully it was described.
7. Composition, in the second paragraph: where the subject sits, and where the clear,
   calmer area for the headline is. An image model has no layout engine — the space for
   text exists only if the picture is composed around it.
8. Positive phrasing. This endpoint has NO negative prompt, so an exclusion only works as
   a sentence in the prompt itself. The exclusions that protect the text are appended for
   you automatically; you do not need to restate them. Do NOT write your own exclusion of
   markings on the subject — "no digits on the flaps", "no symbols on the dial" is how a
   recognisable object was turned into blank furniture. Ask for those markings instead
   (see MARKS in the reply format).
"""


def render_curriculum(brief: dict) -> str:
    """The COURSE block's curriculum section — labelled, not dumped.

    Every group carries one clause saying what it is *for*, and two of them carry a clause
    saying what must NOT be done with them. That is not padding: `narrative_seeds` are
    teaching analogies ("a class is a cookie cutter") and TH-SUBJECT bans painting a
    metaphor, while `struggle_hook` is almost always a developer at a screen ("why does
    this print 10?") and TH-STOCK bans exactly that register. Handed over unlabelled, the
    most concrete sentence in the whole brief would be an instruction to paint the thing
    the spec forbids — so the label is load-bearing and is pinned by a test (rule 26).
    """
    rows = brief.get("curriculum") or []
    if not rows:
        # Falls back to whatever titles exist rather than printing nothing: a spine with no
        # `key_concepts` anywhere is thin, not broken, and a cover still has to come out.
        titles = brief.get("modules") or []
        return "\n".join(f"  {i}. {t}" for i, t in enumerate(titles, 1)) or "  (none listed)"

    seeds_seen = any(r["seeds"] for r in rows)
    stuck_seen = any(r["stuck"] for r in rows)
    out: list[str] = []
    for i, r in enumerate(rows, 1):
        out.append(f"  {i}. {r['title'] or '(untitled module)'}")
        if r["concepts"]:
            out.append(f"     teaches: {' · '.join(r['concepts'])}")
        if r["description"]:
            out.append(f"     about: {r['description']}")
        if r["builds"]:
            out.append(f"     builds: {r['builds']}")
        if r["why"]:
            out.append(f"     matters because: {r['why']}")
        if r["stuck"]:
            out.append(f"     students get stuck on: {r['stuck']}")
        if r["seeds"]:
            out.append(f"     taught with the analogies: {' | '.join(r['seeds'])}")
    body = "\n".join(out)

    notes = []
    if seeds_seen:
        notes.append(
            "  (The `taught with the analogies` lines are TEACHING analogies. Do NOT paint\n"
            "   the analogy — TH-SUBJECT forbids metaphors. They tell you which concept\n"
            "   carries enough weight to need an analogy, and nothing more.)"
        )
    if stuck_seen:
        notes.append(
            "  (In `students get stuck on`, the CONCEPT named is the signal. The\n"
            "   desk-and-screen scene around it is not — TH-STOCK forbids painting a person\n"
            "   at a laptop, however literally the sentence describes one.)"
        )
    if notes:
        body = body + "\n" + "\n".join(notes)
    return body


def build_prompt(
    brief: dict,
    palette: str = "",
    problems: list[str] | None = None,
    previous: str = "",
) -> str:
    """The prompt for CLAUDE — the turn that writes the image prompt.

    Note what this is not: it is not the string sent to the image model. Claude writes art
    direction, `compose_image_prompt` turns it into the image request, and the exclusions
    the transcription gate depends on are added there rather than trusted to this turn.
    """
    palette = palette or palette_for(brief["title"])
    ground, accent, neutral = PALETTES[palette]
    modules = render_curriculum(brief)
    extra = ""
    if brief.get("objectives"):
        listed = "\n".join(f"  - {o}" for o in brief["objectives"])
        extra += (
            "- What a student can do at the end (the outcome the cover is selling):\n"
            f"{listed}\n"
        )
    if brief.get("prerequisites"):
        listed = "\n".join(f"  - {p}" for p in brief["prerequisites"])
        extra += (
            "- Assumed already known (so the subject can be pitched above this level, not\n"
            "  at an absolute beginner):\n"
            f"{listed}\n"
        )
    if brief.get("trimmed"):
        # Said out loud rather than left implicit: a brief that was cut must not read as a
        # whole one, or the model treats an absent field as an absent fact (rule 21).
        extra += (
            f"- NOTE: this curriculum was abridged to fit ({', '.join(brief['trimmed'])} "
            "dropped or shortened). The concepts listed are real; the list may not be\n"
            "  complete.\n"
        )
    # The word cap is repeated here, next to the actual title, because that is where
    # it gets broken: a real course title is routinely 7-9 words and the model's
    # instinct is to set all of it. Naming the cap beside the input turns "shorten
    # this" into an instruction about a specific string rather than a general rule.
    course = f"""\
COURSE
- Title: {brief['title']}
  (TH-WORDS: at most {MAX_TEXT_WORDS} words in the HEADLINE. If this title is longer,
  cut it to the {MAX_TEXT_WORDS - 1} or so words that name the subject. The full title
  appears everywhere else on the page. Short headlines are also the ones image models
  spell correctly, and the spelling is checked.)
- Audience: {brief['audience'] or '(not stated)'}
- Duration: {brief['duration'] or '(not stated)'}
- Description: {brief['description'] or '(not stated)'}
{extra}\
- Modules, and the concepts each one teaches. This is the material the subject must come
  from, and it is also the ONLY text allowed on the cover besides the headline: both the
  SOURCE line and every LABEL you declare are checked, as substrings, against exactly the
  titles and concepts below. A label that is not in this list costs a wasted turn:
{modules}

PALETTE — `{palette}`, assigned to this course. Not a suggestion and not yours to change:
- ground  {ground}  the dominant field of the picture
- accent  {accent}  the subject, and the light on it
- headline {neutral}  the colour of the painted words
Describe these as colours in the prompt ("deep {ground} field", "{accent} rim light"), and
name the hex for the headline. Use no fourth colour family. Note the direction (rule 6):
{accent} is what the SUBJECT is made of and lit by; {ground} is the field behind it. Do
not describe the subject's material as {ground} or as near-black — a dark object on a dark
field is the cover this rule was written from.
"""
    if not problems:
        return f"{_DESIGN}\n{_ART_RULES}\n{_GALLERIES}\n{course}\n{_REPLY_FORMAT}"

    # Correction turn. The findings are handed over verbatim because each one is
    # already phrased as the fix for the thing it names (rule 24) — a generic
    # "make it better" is what makes a retry loop burn calls without converging.
    listed = "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
    return f"""\
The cover generated from the art direction below was rejected. Fix exactly these problems
and change nothing else:

{listed}

Note what you are correcting: you cannot edit the picture, only the words that produce it.
So change the art direction so that a fresh render does not have these problems — if the
headline was misread, make it shorter, or ask for it larger, or put it somewhere emptier.

{_DESIGN}
{_ART_RULES}
{_GALLERIES}
{course}
PREVIOUS ART DIRECTION (revise it, do not start over):
{previous}

{_REPLY_FORMAT}
"""


# The parse is deliberately forgiving about decoration and strict about substance: a model
# that wraps its headline in quotes or asterisks has still answered the question, but one
# that omits the marker has not, and guessing which line was meant to be the headline is
# how the gate would end up comparing against the wrong string.
_HEADLINE_RE = re.compile(r"^[ \t>*#]*HEADLINE[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_PROMPT_RE = re.compile(r"^[ \t>*#]*PROMPT[ \t]*:[ \t]*", re.MULTILINE)
_SUBJECT_RE = re.compile(r"^[ \t>*#]*SUBJECT[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_SOURCE_RE = re.compile(r"^[ \t>*#]*SOURCE[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_MARKS_RE = re.compile(r"^[ \t>*#]*MARKS[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_STYLE_RE = re.compile(r"^[ \t>*#]*STYLE[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_LAYOUT_RE = re.compile(r"^[ \t>*#]*LAYOUT[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_LABELS_RE = re.compile(r"^[ \t>*#]*LABELS[ \t]*:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_DECORATION = " \t\"'`*_“”‘’«»"
# Below this, a "citation" carries no information — "AI", "OOP", "3" would match almost any
# curriculum by accident, which would make the gate decoration rather than a check.
MIN_SOURCE_CHARS = 4
# The literal answer that means "this object carries no markings". A single word so the
# check is an equality rather than a judgement about a sentence.
NO_MARKS = "none"
# Characters of shared prefix that make two words the same subject word for `check_headline`.
# 5, because `ECONOMIST`/`economics` and `BIOLOGICAL`/`biology` share five and are the same
# subject, while `STARTUP`/`stars` shares four and is not.
_SHARED_STEM = 5
# How much of a named marking has to survive into the prompt before the marking counts as
# actually requested. Any one subject-bearing word: `MARKS: crisp white numerals on each
# flap` is satisfied by a PROMPT that says "numerals", which is the thing being asked for.
# Requiring more would reject a prompt that paraphrases correctly, and requiring less (a
# substring of the whole phrase) would reject one that reorders the words.
MIN_MARKS_CHARS = 3
# The other half of the same check, and the precise one. The positive test above is lenient by
# design, and being lenient it has a hole: `MARKS: crisp white numerals on each flap` is satisfied
# by a prompt that says "flap", because "flap" is one of the phrase's own words. The prompt can
# therefore name the OBJECT and still blank its markings — which is exactly the failure, not a
# hypothetical one. So scan the art direction for the model *negating* markings.
#
# Measured, not reasoned (rule 25). Run over all 21 real art directions in
# `output/covers-review/**/*.prompt.txt`, art half only: **1 hit, 0 false positives**, and the one
# hit is `grounding/after/economics` — the causal failure, whose prompt reads "its flaps converged
# flat and blank … with no digits, letters, or symbols printed on any flap". n=1 is a small
# calibration and it is stated as such; the cost of a false positive is one text call and zero image
# calls, which is why this is affordable at that n.
#
# `no text` and `no writing` are deliberately ABSENT. `no text` fired on three prompts including the
# WORKING `supply-and-demand` — where it is "no texture in it", about the headline's background, and
# harmless. Word-shaped text is what `_NO_TEXT_CLAUSE` and the transcription gate want banned, so a
# prompt banning it is being obedient rather than defective. What must not be banned is the
# non-lexical marking: digits, notation, numerals, engraving.
_MARK_NEGATIONS = (
    "no digits", "no letters", "no symbols", "no numbers", "no numerals", "no lettering",
    "no markings", "no marks", "no inscription", "no printing", "nothing printed",
    "unmarked", "unlettered", "featureless", "blank",
)


class ArtDirectionError(RuntimeError):
    """Claude's reply did not carry a usable headline and prompt."""


def _norm(s: str) -> str:
    """The comparison form for a citation: case- and whitespace-insensitive.

    Same shape `palette_for` uses, and for the same reason — two strings that differ only
    in how they were wrapped are the same string, and a gate that says otherwise burns a
    retry on nothing.
    """
    return " ".join(s.split()).lower()


def _citation_sample(brief: dict, n: int = 8) -> list[str]:
    """`n` example citations, spread ACROSS modules rather than sliced off the front.

    The naive `brief["concepts"][:8]` is wrong in a way that was measured, not reasoned.
    `load_brief` builds that list by walking modules in order, so on `python_v0` (43
    concepts, 10 modules) the first eight are **all from module 1** and the message printed:

        For example: 'Namespace'; 'Built-in Namespace'; 'Global Namespace'; 'Local
        Namespace'; 'Scope'; 'Built-in Scope'; 'Global Scope'; 'Local Scope'

    which is byte-identical to that module's `teaches:` line in `render_curriculum`. The
    model pasted all eight back joined by ` · `, `check_source` refused them as eight
    citations, and one whole attempt was spent. So the refusal was correct and the *example*
    was the defect: a message meant to name the fix (rule 24) demonstrated the failure
    instead, by handing over a contiguous run of one line as the thing to copy from.

    Round-robin by concept index, so eight examples come from eight different modules and
    read as alternatives rather than as a line. Falls back to the flat list and then to
    module titles, keeping today's behaviour for a spine with no `curriculum` rows.
    """
    rows = brief.get("curriculum") or []
    out: list[str] = []
    seen: set[str] = set()
    depth = max((len(r.get("concepts") or []) for r in rows), default=0)
    for i in range(depth):
        for r in rows:
            concepts = r.get("concepts") or []
            if i >= len(concepts):
                continue
            key = concepts[i].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(concepts[i])
            if len(out) == n:
                return out
    if out:
        return out
    return (brief.get("concepts") or brief.get("modules") or [])[:n]


def check_source(source: str, brief: dict) -> None:
    """Raise unless `source` cites something this course actually teaches.

    Deterministic, no LLM call, and run BEFORE any image is bought — which is the whole
    point: `ArtDirectionError` is the cheapest retry in the loop (one text call, zero image
    calls), so the check that can reject a subject belongs on this side of the spend.

    **Substring, not equality**, and that is measured rather than lenient. Real
    `key_concepts` are compound strings — `"Demand: law of demand, demand curves,
    determinants of demand"` — so a model that cites `law of demand`, the honest and
    specific answer, would be rejected by exact equality and would then have to learn to
    quote a whole clause it did not choose. Matching the citation *inside* the corpus keeps
    the check strict about invention (a cover subject that appears nowhere in the course
    cannot pass) while letting a precise citation through.

    The failure message names the fix, not the failure (rule 24): the model gets a sample of
    the list it was supposed to copy from, so one turn is enough to correct it.
    """
    cited = _norm(source)
    if len(cited) < MIN_SOURCE_CHARS:
        raise ArtDirectionError(
            f"the `SOURCE:` line is too short to be a citation ({source!r}). Copy one of "
            "the module titles or key concepts from the COURSE block, verbatim."
        )
    corpus = _norm(
        " || ".join(list(brief.get("modules") or []) + list(brief.get("concepts") or []))
    )
    if not corpus:
        # Nothing to check against. Fails OPEN, loudly, because this is a *read-only* audit
        # of the model's citation and a spine with no titles and no concepts is a thin
        # input, not a bad cover — refusing every cover for such a course would make the
        # gate the defect (rule 21, and fail-open-vs-closed is per path, rule 31).
        print(
            "⚠️  TH-GROUND: this spine lists no module titles and no key concepts, so "
            f"`SOURCE: {source}` could not be checked against anything (gate did not run)"
        )
        return
    if cited in corpus:
        return
    # A citation that spans the ` · ` separator `render_curriculum` prints BETWEEN concepts.
    # Measured on the first real run of this gate: the reply cited
    # `SOURCE: Class Object · Instance Object`, two adjacent concepts read as one. That is a
    # defect my own formatting invites, so it gets its own message — the generic refusal
    # above would say "does not appear in this curriculum" about two entries that both do,
    # which is false and gives the model nothing to act on (rule 24).
    parts = [p for p in (q.strip() for q in source.split("·")) if p]
    if len(parts) > 1 and all(_norm(p) in corpus for p in parts):
        raise ArtDirectionError(
            f"TH-GROUND: `SOURCE: {source}` copies {len(parts)} separate entries across the "
            "` · ` separator that only divides them in the list. Cite exactly ONE — "
            f"`{parts[0]}` or `{parts[1]}`, not both — and draw that one thing."
        )
    sample = _citation_sample(brief)
    raise ArtDirectionError(
        f"TH-GROUND: `SOURCE: {source}` does not appear in this course's curriculum, so "
        "the subject was invented rather than chosen from what the course teaches. Pick a "
        "module title or key concept from the COURSE block and copy it into SOURCE "
        "verbatim, then draw THAT. For example: "
        + "; ".join(repr(s) for s in sample)
    )


def check_marks(marks: str, art: str) -> None:
    """Raise unless the markings the reply named are actually asked for in the prompt.

    The cheap half of the fix for "I cannot recognise it". `_EXCLUSIONS` used to strip the
    subject's own markings and the model was obediently writing "no digits on any flap" for
    a *price board*; the clause is now split, but a permission nothing checks is a rule that
    lives in prose (rule 26). So the reply has to commit to the markings in a machine-read
    field and then the prompt has to contain them.

    Deterministic, no LLM call, and — like `check_source` — run BEFORE any image is bought,
    which is the point rather than an implementation detail: `ArtDirectionError` is the
    cheapest retry in the loop, one text call and zero image calls.

    **Deliberately lenient about paraphrase, strict about silence.** One subject-bearing
    word of the named markings has to appear in the art direction, not the phrase. A model
    that writes `MARKS: crisp white numerals on each flap` and then a paragraph describing
    "each flap struck with a numeral" has done the thing being asked for, and rejecting it
    would burn a turn to teach it a wording.

    **Two tests, because the lenient one has a hole the real failure fits through.** Matching
    any one word of the phrase includes the phrase's own *object* noun, so "on each flap"
    against a prompt that says "flaps converged flat and blank" passes — the markings are
    named, the object is drawn, the markings are explicitly absent. So the second test scans
    the art direction for the model *negating* markings (`_MARK_NEGATIONS`, calibrated on the
    corpus at 1 hit / 0 false positives). The negation is checked FIRST: when both fire, the
    contradiction is the more specific and more actionable finding.
    """
    value = " ".join((marks or "").split()).strip(_DECORATION + ".")
    if not value:
        raise ArtDirectionError(
            "the `MARKS:` line is empty. Name the markings the object carries — the "
            "digits, the notation, the numerals, the engraving — or write `none` if it "
            "reads as itself with nothing written on it."
        )
    # `none` plus an explanation is still `none`: the reply format asks the model to say
    # WHICH unmarked object it means, so "none — a crate of oranges" is the compliant
    # answer and an equality check would reject it.
    if value.split()[0].lower().strip(_DECORATION + ".,;:") == NO_MARKS:
        return
    lowered = art.lower()
    # Word boundaries, so "no texture" is not read as "no text" — the substring false positive
    # that is the reason `no text` is not in the list at all.
    negated = [
        n for n in _MARK_NEGATIONS if re.search(r"\b" + n.replace(" ", r"\s+") + r"\b", lowered)
    ]
    if negated:
        raise ArtDirectionError(
            f"TH-MARKS: `MARKS: {value}` names markings the object carries, but the art "
            f"direction then takes them away — it says {negated[0]!r}. That contradiction IS "
            "the defect this field exists to catch: a price board with no prices on it reads "
            "as blank furniture and a student cannot tell what the course is. Delete the "
            "phrase that removes the markings and describe them as painted instead: not 'a "
            "price board' but 'a price board, each flap showing a crisp numeral'. You do not "
            "need to exclude them for the headline's sake — the exclusion clause appended to "
            "your prompt already bans ADDED text, and markings that are part of the object "
            "are wanted. Keep them non-lexical: figures and symbols, not readable words."
        )
    terms = _ground_terms(value)
    if any(len(t) >= MIN_MARKS_CHARS and t in lowered for t in terms):
        return
    raise ArtDirectionError(
        f"TH-MARKS: `MARKS: {value}` names markings the object carries, but the art "
        "direction never asks for them, so the image model will not paint them and the "
        "object will read as blank furniture — that is the exact defect this field exists "
        "to prevent (a price board with no prices on it). Describe them in PROMPT as "
        "something painted: not 'a price board' but 'a price board, each flap showing a "
        "crisp numeral'. Keep them non-lexical — figures and symbols, not readable words."
    )


def _check_membership(value: str, gallery: dict[str, str], field: str, rule: str) -> str:
    """Exact membership in an allow-list — the cheapest check in the file.

    Exact rather than fuzzy on purpose: the value names a FILE that has to be opened, so
    "close enough" has nowhere to go, and a normalised near-miss would resolve `Chalkboard`
    to `chalkboard` silently and then teach the model nothing. What the failure gives back
    instead is the whole list (rule 24): an unfixable message is what burns attempts, and
    the list IS the fix.
    """
    name = " ".join((value or "").split()).strip(_DECORATION + ".,;:").lower()
    if name in gallery:
        return name
    raise ArtDirectionError(
        f"{rule}: `{field}: {value}` is not one of the {len(gallery)} names in the "
        f"{field} GALLERY. Copy one of these character for character: "
        + ", ".join(gallery)
    )


def check_style(style: str) -> str:
    """The chosen style must be one of ours. Returns the normalised name."""
    return _check_membership(style, STYLE_GALLERY, "STYLE", "TH-STYLE")


def check_layout(layout: str) -> str:
    """The chosen layout must be one of ours. Returns the normalised name."""
    return _check_membership(layout, LAYOUT_GALLERY, "LAYOUT", "TH-LAYOUT")


def check_labels(labels: str, brief: dict, layout: str = "") -> tuple[str, ...]:
    """The words to be PAINTED on the cover, checked against the curriculum first.

    This is the field that makes a structured cover possible at all, and it is also the
    concrete answer to "the prompt is still not very course based". Today exactly one thing
    connects the picture to the curriculum — the `SOURCE:` citation — and none of it is
    visible: it steers the subject and then disappears. After this, the words a student
    actually READS on the card are curriculum text, verified verbatim before a cent is spent.

    Substring into the same corpus `check_source` builds, for the same measured reason: real
    `key_concepts` are compound strings, so `law of demand` is the honest citation out of
    `"Demand: law of demand, demand curves, determinants of demand"` and equality would
    refuse it.

    Three bounds, each one on the TRANSCRIPTION gate rather than on taste — every label is a
    word the vision model reads back and `TH-TITLE` must then account for:

      · at most `MAX_LABELS`, so the read-back surface stays small;
      · at most `MAX_LABEL_WORDS` words each, because a sentence painted on a cover is a
        caption, and `_EXCLUSIONS` bans captions;
      · at least one `_ground_terms` word per label, which is what stops `the`, `and`, `a`
        from passing the substring test against any corpus in existence. `MIN_SOURCE_CHARS`
        does the same job one level down for the whole string.

    Fails OPEN, loudly, on an empty corpus — same path, same reason as `check_source`: this
    is a read-only audit of our own reply, and a spine with no titles and no concepts is a
    thin input rather than a bad cover (rules 21 and 31).

    Returns the labels as a tuple, `()` for `none`.
    """
    value = " ".join((labels or "").split()).strip(_DECORATION + ".")
    if not value:
        raise ArtDirectionError(
            "the `LABELS:` line is empty. Either name the words to paint on the picture — "
            "curriculum text, separated by `|` — or write `none`."
        )
    # `none` plus an explanation is still `none`, exactly as `check_marks` reads it: the
    # reply format invites "none — one object, lit", and equality would reject the
    # compliant answer.
    if value.split()[0].lower().strip(_DECORATION + ".,;:") == NO_MARKS:
        return ()

    items = [p for p in (q.strip(_DECORATION + ".,;") for q in value.split("|")) if p]
    if not items:
        raise ArtDirectionError(
            f"the `LABELS:` line {labels!r} has no labels in it. Separate them with `|`, "
            "or write `none`."
        )
    if len(items) > MAX_LABELS:
        raise ArtDirectionError(
            f"TH-LABELS: {len(items)} labels, over the {MAX_LABELS} cap. Every label is a "
            "word a vision model has to read back off the finished picture and the title "
            f"check has to account for, so keep the {MAX_LABELS} that carry the most "
            "meaning and drop the rest."
        )
    if layout == SINGLE_SUBJECT:
        raise ArtDirectionError(
            f"TH-LAYOUT: `LAYOUT: {SINGLE_SUBJECT}` means one object with nothing written "
            f"on it, but {len(items)} labels were declared. Either write `LABELS: none`, or "
            "choose a layout that has somewhere to put them."
        )

    corpus = _norm(
        " || ".join(list(brief.get("modules") or []) + list(brief.get("concepts") or []))
    )
    if not corpus:
        print(
            "⚠️  TH-LABELS: this spine lists no module titles and no key concepts, so the "
            f"{len(items)} declared label(s) could not be checked against anything "
            "(gate did not run)"
        )
        return tuple(items)

    sample = _citation_sample(brief)
    for item in items:
        if len(item.split()) > MAX_LABEL_WORDS:
            raise ArtDirectionError(
                f"TH-LABELS: the label {item!r} is {len(item.split())} words, over the "
                f"{MAX_LABEL_WORDS} cap. A label is two or three words on a picture; "
                "anything longer is a caption, and captions are excluded from the cover."
            )
        cited = _norm(item)
        if len(cited) < MIN_SOURCE_CHARS:
            raise ArtDirectionError(
                f"TH-LABELS: the label {item!r} is too short to carry meaning. Use "
                "curriculum text — a module title or a key concept, or a phrase out of one."
            )
        if not _ground_terms(item):
            raise ArtDirectionError(
                f"TH-LABELS: the label {item!r} is made only of common words, so it says "
                "nothing about this course. Use a module title or a key concept."
            )
        if cited not in corpus:
            raise ArtDirectionError(
                f"TH-LABELS: the label {item!r} does not appear in this course's "
                "curriculum, so it would put invented text on the cover. Every painted "
                "word must be copied out of the module titles or key concepts in the "
                "COURSE block. For example: " + "; ".join(repr(s) for s in sample)
            )
    return tuple(items)


def check_headline(headline: str, brief: dict) -> None:
    """Raise unless the headline names this course.

    Measured failure: `Economics for Developers` shipped a cover reading `SUPPLY MEETS
    DEMAND`. Every gate passed — it is short, spelled right, legible — and a student
    scanning a catalogue cannot tell which course the card is for. The cover's job is to
    identify the course, so a headline that shares no subject word with the title has
    failed at it however good the picture is.

    Prefix matching on top of `_ground_terms`' plural fold, because the near-misses are all
    morphological: `COMPOUNDING` for *Compound Interest*, `STAR` for *The Life Cycle of
    Stars*. Both are the course's own word and both would fail exact equality, which would
    make this gate a tax on good headlines.

    Plus a shared-stem rule, because prefix matching is not enough for the commonest
    derivation: `ECONOMIST` against *Economics* diverges at the 8th character, so neither is a
    prefix of the other and a perfectly good headline gets refused. `_SHARED_STEM` chars of
    common prefix accepts that pair, and also `BIOLOGICAL`/*Biology* and
    `STATISTICAL`/*Statistics*. It only ever *widens* acceptance, so it cannot cause a new
    refusal; the bar is 5 rather than 4 because `STARTUP`/*Stars* shares four.

    Fails OPEN, loudly, on a title with no subject-bearing words — a read-only audit of our
    own reply, and refusing every cover for a course called `Go` would make the gate the
    defect (rule 21, and fail-open-vs-closed is per path, rule 31).
    """
    want = _ground_terms(brief.get("title") or "")
    if not want:
        print(
            f"⚠️  TH-WORDS: the course title {brief.get('title')!r} has no word long "
            f"enough to carry subject meaning, so `HEADLINE: {headline}` could not be "
            "checked against it (gate did not run)"
        )
        return
    got = _ground_terms(headline)
    for a in got:
        for b in want:
            if a == b or a.startswith(b) or b.startswith(a):
                return
            if len(os.path.commonprefix([a, b])) >= _SHARED_STEM:
                return
    raise ArtDirectionError(
        f"TH-WORDS: `HEADLINE: {headline}` shares no word with the course title "
        f"{brief.get('title')!r}, so the card does not say which course it is for. The "
        "cover's first job is to identify the course. Keep at least one of "
        + ", ".join(sorted(want)[:5])
        + " in the headline — or use a shortened form of the title itself."
    )


class ArtDirection(NamedTuple):
    """The parsed reply. A NamedTuple rather than a plain tuple because this grew from 2
    fields to 8 and an 8-tuple's call sites are unreadable — but still a tuple, so the
    existing unpacking and indexing keep working.

    **The field ORDER is load-bearing and the three new ones are deliberately last.**
    `subject, source, marks, headline, art` are positions 0-4 exactly as they were, so
    every caller that indexes `[3]` for the headline or `[:2]` still means what it meant.
    Appending rather than inserting is what made this a two-line change instead of a hunt.
    """

    subject: str
    source: str
    marks: str
    headline: str
    art: str
    style: str = ""
    layout: str = SINGLE_SUBJECT
    labels: tuple[str, ...] = ()


def parse_art_direction(reply: str, brief: dict | None = None) -> ArtDirection:
    """An `ArtDirection` out of Claude's reply.

    Raises rather than guessing. This is a retryable failure — it costs one Claude call
    and no image call — and the alternative is worse than a retry: a silently wrong
    headline would make the transcription gate compare the picture against a string nobody
    asked for, which fails 4 times and ships a text-free cover for no reason.

    `brief` is optional only so that the headline/prompt half stays testable on its own; when
    it is passed, `SOURCE` is checked against the curriculum and an invented citation raises,
    and `HEADLINE` is checked for naming the course. `MARKS` is checked either way, since it
    is compared against the prompt rather than against the brief.
    """
    m = _HEADLINE_RE.search(reply)
    if not m:
        raise ArtDirectionError(
            "the reply has no `HEADLINE:` line, so there is nothing to check the "
            f"painted text against. Reply began: {reply[:200]!r}"
        )
    headline = " ".join(m.group(1).split()).strip(_DECORATION)
    if not headline:
        raise ArtDirectionError("the `HEADLINE:` line is empty")
    words = headline.split()
    if len(words) > MAX_TEXT_WORDS:
        raise ArtDirectionError(
            f"the headline is {len(words)} words, over the {MAX_TEXT_WORDS} cap: "
            f"{headline!r}. Cut it to the words that name the subject."
        )

    pm = _PROMPT_RE.search(reply, m.end())
    if not pm:
        raise ArtDirectionError("the reply has no `PROMPT:` marker after the headline")
    art = reply[pm.end():].strip()
    # A fenced block is the one decoration worth unwrapping rather than rejecting: the
    # reply format forbids fences, but a model that ignores that has still written usable
    # prose inside them, and the fence markers themselves would reach the image model.
    art = re.sub(r"^```[^\n]*\n", "", art)
    art = re.sub(r"\n```\s*\Z", "", art).strip()
    if len(art) < MIN_ART_CHARS:
        raise ArtDirectionError(
            f"the art direction is {len(art)} characters, too short to be a picture: "
            f"{art!r}"
        )
    if headline.lower() not in art.lower():
        # Structural, not stylistic: the image model paints only what the prompt asks
        # for, so a prompt that never mentions the headline cannot produce it, and the
        # transcription gate would then fail four times on a picture that was never asked
        # to carry any text.
        raise ArtDirectionError(
            f"the art direction never mentions the headline {headline!r}, so nothing "
            "would be painted for the transcription check to read back. Repeat it "
            "verbatim inside PROMPT."
        )

    # Checked last, deliberately: the headline and prompt failures are about whether there
    # is a usable reply at all, and reporting "your citation is wrong" for a reply that has
    # no PROMPT: marker would name the wrong defect.
    sm = _SUBJECT_RE.search(reply)
    if not sm:
        raise ArtDirectionError(
            "the reply has no `SUBJECT:` line, so there is nothing to compare the finished "
            "picture against. Name the one concrete thing you are drawing."
        )
    subject = " ".join(sm.group(1).split()).strip(_DECORATION)
    om = _SOURCE_RE.search(reply)
    if not om:
        raise ArtDirectionError(
            "the reply has no `SOURCE:` line. Copy the module title or key concept your "
            "subject comes from out of the COURSE block, verbatim."
        )
    source = " ".join(om.group(1).split()).strip(_DECORATION)
    if not subject:
        raise ArtDirectionError("the `SUBJECT:` line is empty")
    mm = _MARKS_RE.search(reply)
    if not mm:
        raise ArtDirectionError(
            "the reply has no `MARKS:` line. Name the markings the object carries — the "
            "digits, the notation, the numerals, the engraving — or write `none` if it "
            "reads as itself with nothing written on it."
        )
    marks = " ".join(mm.group(1).split()).strip(_DECORATION)
    check_marks(marks, art)

    # STYLE / LAYOUT / LABELS. Absent is a hard failure rather than a default, for the
    # reason the whole galleries change exists: a silent default is what "one hardcoded
    # style" WAS, and a reply that did not choose has not answered the question. The
    # exception is `brief is None`, the headline/prompt-only test path — the three fields
    # are checked when they are present and skipped when they are not, which keeps the
    # older cases meaningful without making them lie about the new contract.
    stm = _STYLE_RE.search(reply)
    ltm = _LAYOUT_RE.search(reply)
    lbm = _LABELS_RE.search(reply)
    if brief is None and not (stm or ltm or lbm):
        return ArtDirection(subject, source, marks, headline, art)
    if not stm:
        raise ArtDirectionError(
            "the reply has no `STYLE:` line. Pick one name from the STYLE GALLERY and copy "
            "it character for character: " + ", ".join(STYLE_GALLERY)
        )
    if not ltm:
        raise ArtDirectionError(
            "the reply has no `LAYOUT:` line. Pick one name from the LAYOUT GALLERY and "
            "copy it character for character: " + ", ".join(LAYOUT_GALLERY)
        )
    if not lbm:
        raise ArtDirectionError(
            "the reply has no `LABELS:` line. Name the words to paint on the picture, "
            "separated by `|` and copied from the curriculum — or write `none`."
        )
    style = check_style(stm.group(1))
    layout = check_layout(ltm.group(1))
    labels = check_labels(lbm.group(1), brief or {}, layout)
    # Same structural check the headline already gets, and for the same reason: the image
    # model paints only what the prompt asks for. A declared label that is nowhere in the
    # art direction is a word the transcription gate has been told to expect and the
    # picture was never asked to carry — the inverse defect, and it costs the same 4
    # attempts. Substring on the lowered art, because the label reaches the picture as
    # text and its casing is `_TEXT_CLAUSE`'s business, not the model's.
    lowered = art.lower()
    missing = [x for x in labels if x.lower() not in lowered]
    if missing:
        raise ArtDirectionError(
            "TH-LABELS: the art direction never mentions the label(s) "
            + ", ".join(repr(x) for x in missing)
            + ", so nothing would be painted for them. Ask for each label in PROMPT as "
            "text on the picture, in the place the layout puts it — or drop it from LABELS."
        )
    if brief is not None:
        check_source(source, brief)
        check_headline(headline, brief)
    return ArtDirection(subject, source, marks, headline, art, style, layout, labels)


# Appended to every image prompt by code, never by a generation turn. These two clauses
# are the transcription gate's PRECONDITION — the gate compares the transcription to the
# headline by exact equality, so a stray caption, watermark or signature fails it just as
# hard as a misspelling. Leaving them to the model to restate each turn is rule 26's
# failure exactly: a rule that lives only in prose someone has to remember.
_TEXT_CLAUSE = (
    'Painted text: render the words "{headline}" and no other words, in a heavy '
    "condensed sans-serif, uppercase, in {neutral}, occupying the clear area described "
    "above, large enough to read on a phone at thumbnail size. Spell it exactly, "
    "letter for letter: {headline}"
)
#
# `_EXCLUSIONS` is split into two sentences, and the split is the fix for the complaint that
# the covers were unrecognisable. It used to ban ALL text including "no letters hidden in
# the artwork", and that clause was doing real damage rather than nothing: once the subject
# is chosen from the curriculum it is routinely a thing whose meaning IS its markings — a
# price board, a score, a dial, a coin — and this clause then stripped exactly those
# markings. The failing prompt asked, in its own words, for a split-flap price board "with
# no digits, letters, or symbols printed on any flap": a price board with no prices. So the
# ban is now on ADDED text (the caption/watermark/logo register the gate actually fails on)
# and the subject's own markings are asked for POSITIVELY. `music-theory.png` is the
# existence proof — it survived the old clause only because its notation was requested
# before the exclusion reached it.
_EXCLUSIONS = (
    "This is the only text ADDED to the picture: no subtitle, no caption, no watermark, "
    "no logo, no signature, no date, no page numbers, no user-interface elements, no "
    "placeholder or lorem ipsum text."
)
# Both text clauses have a labelled twin, and the twins exist because the originals say the
# opposite of what a labelled cover needs. `_TEXT_CLAUSE` asks for the headline "and no
# other words"; `_EXCLUSIONS` calls it "the only text ADDED to the picture". Left as they
# are, the prompt would ask for labels in one paragraph and forbid them in the next, and an
# image model resolves a contradiction however it likes — which is the measured failure
# `compose_text_free_prompt` was rewritten for, one clause over.
#
# Twins rather than a `{}` slot in the originals: the unlabelled path has to stay
# BYTE-IDENTICAL to what produced the four covers that work, and a reformatted template is
# the cheapest way to break that silently. A test pins the identity.
_TEXT_CLAUSE_LABELLED = (
    'Painted text: render the words "{headline}" in a heavy condensed sans-serif, '
    "uppercase, in {neutral}, occupying the clear area described above, large enough to "
    "read on a phone at thumbnail size. Spell it exactly, letter for letter: {headline}. "
    "The only other words in the picture are the labels listed below."
)
_EXCLUSIONS_LABELLED = (
    "The headline and those labels are the only text ADDED to the picture: no subtitle, "
    "no caption, no watermark, no logo, no signature, no date, no page numbers, no "
    "user-interface elements, no placeholder or lorem ipsum text."
)
# The permission — and it no longer carries the blur mandate it used to, because that
# mandate was measured doing damage on 4 of 5 covers (4 Sep 2026).
#
# It read: "anywhere the object would carry writing, paint it too small and blurred to read
# as words." It existed because `TH-TITLE` transcribed the WHOLE image and judged every
# legible word against the headline, so a stencil on a crate was a hard failure. The gate now
# sorts what it reads into added text and the subject's own markings and judges only the
# first (`openrouter.parse_transcription`), so the mandate protects nothing — and it was
# never free. It is why `economics`' split-flap price boards read `GRAD` and `GRADO` instead
# of prices: a price board whose prices are deliberately unreadable. Worse, on `recursion`
# the correction turn repeated it, the model complied by blurring the largest text in the
# frame, and the cover shipped with NO HEADLINE at all after four attempts.
#
# What survives is the *preference* for figures and notation over words, and it is a
# preference and not a rule: an image model spelling a word it invented produces visible
# gibberish (`immune-system-single` painted a vial reading `FUSMIEEISNATEMET`), which is
# cosmetic and recorded in `report["marks_seen"]` rather than gated — judging it is exactly
# what cost two covers their headline.
#
# The COUNT bound is the second half of that preference and it was added from a measurement,
# not from a worry: the two covers of 4 Sep 2026's third run differ in nothing else. `economics`
# painted 3 marks (`3.20/kg`, `B-27`, `LOT 04`) — every one of them correct, meaningful, and the
# reason the picture reads as a market. `python-oop` painted **20** (`STANETATG`, `PYITINBER`,
# `ANPYSTIRRY`, `11:60`, `1.334"`, …) and every one is gibberish, on a cover whose headline was
# perfect. So legibility does not degrade gradually with quantity — a model asked for a few marks
# gets them right and a model asked to annotate every surface invents. `blueprint` provokes it
# hardest, because the style file's own `Visual Elements` list asks for "dimension lines and
# measurement indicators" on a cover that already has a subject; the bound is stated here rather
# than by editing the vendored style file, which stays verbatim.
#
# Stated as a quantity the model can act on ("two or three places", "one surface") rather than as
# a threshold this code enforces. A `marks_seen` token count *would* be gateable, but calibrating
# one on 4 covers is the trap that once flagged 76% of this project's SVG diagrams (rule 25), and
# the vision critique already reports the defect: `TH-TRUE: the dimension labels and card text are
# garbled nonsense`. Advisory findings that name the defect precisely are what a threshold is
# supposed to approximate.
_MARKS_CLAUSE = (
    "Markings that are PART OF THE SUBJECT are wanted, not excluded: digits on a price "
    "board, notation on a score, numerals on a dial, engraving on a coin, syntax colours "
    "in code on a screen. Paint them crisply and legibly — they are what makes the object "
    "recognisable as itself. Prefer figures, symbols and notation over words: where the "
    "real object would carry running prose or a masthead, suggest it with a few short "
    "marks rather than inventing sentences. Keep them FEW — two or three markings on one "
    "or two surfaces, painted correctly, not every surface annotated. A handful of right "
    "marks makes the object real; a frame covered in small text makes it gibberish."
)
# The SAME clause with its last sentence replaced, for a cover that has declared labels.
#
# The twin survives the removal of the blur mandate above, and the difference between them is
# now small but real: this one says which words are the LABELS and asks for those, at label
# size, against the thing they name. Without that sentence the model has a list of labels in
# one paragraph and a preference for notation-over-words in the next, and the measured
# consequence of leaving a prompt to resolve its own contradiction is on disk twice over
# (`compose_text_free_prompt`, and `_EXCLUSIONS` before it was narrowed to *added* text).
#
# What is deliberately NOT here is a blanket "text is allowed now". A caption, a subtitle or a
# watermark is still a hard `TH-TITLE` failure, because those are text added ON TOP of the
# picture and that is the register the gate reads: the permission has to be exactly as wide as
# the gate that follows it, or it widens INTO the gate.
_LABELLED_MARKS_CLAUSE = (
    "Markings that are PART OF THE SUBJECT are wanted, not excluded: digits on a price "
    "board, notation on a score, numerals on a dial, engraving on a coin, syntax colours "
    "in code on a screen. Paint them crisply and legibly — they are what makes the object "
    "recognisable as itself. Prefer figures, symbols and notation over words, except for "
    "the labels named above: those are wanted as legible words, at label size, each one "
    "against the part of the picture it names. Keep the rest FEW — two or three markings "
    "on one or two surfaces, painted correctly, not every surface annotated. A handful of "
    "right marks makes the object real; a frame covered in small text makes it gibberish, "
    "and it is the labels that lose legibility first when it is crowded."
)
# The labels themselves. Spelled out one per line, quoted, with the spelling asked for
# explicitly — the same shape as `_TEXT_CLAUSE`, because these words go through the same
# transcription read-back and a misspelt one is a finding.
_LABELS_CLAUSE = (
    "Painted labels, in addition to the headline and in the positions described above — "
    "these words and no others: {listed}. Set them in the same condensed sans-serif as the "
    "headline but much smaller, in {neutral}, each one placed against the part of the "
    "picture it names, large enough to read on a phone at thumbnail size. Spell each one "
    "exactly as written."
)
_FRAME_CLAUSE = (
    "No border, no frame, no letterboxing: the illustration reaches all four edges."
)

# Replaces both clauses above on the fallback render. Positive phrasing throughout, because
# this endpoint has no negative prompt and "no text" as an afterthought is routinely
# ignored — the request has to be *for* an unbroken picture rather than *against* letters.
_NO_TEXT_CLAUSE = (
    "This picture contains no writing of any kind: no words, no letters, no numbers, no "
    "title, no caption, no label, no watermark, no logo, no signature, no user-interface "
    "elements. It is a purely pictorial illustration, filling the frame edge to edge, with "
    "no border and no letterboxing. Where a headline would have gone, extend the "
    "illustration and its background."
)


def compose_image_prompt(
    headline: str,
    art: str,
    palette: str,
    style: str = "",
    layout: str = SINGLE_SUBJECT,
    labels: tuple[str, ...] = (),
) -> str:
    """The string actually sent to the image model.

    Claude's art direction, the two vendored reference files for the style and layout it
    chose, plus the deterministic clauses. Assembled in code so that the text request and
    its exclusions are identical on every attempt and on every course — the one part of the
    prompt the retry loop must not be able to erode.

    **The reference files are injected HERE, not in the text turn**, and that is the same
    decision for the same reason: a retry rewrites the art direction, so anything the model
    holds in its own prose can be eroded across four attempts, while anything code appends
    cannot. It is also the token bound — ~400 tokens for the chosen pair against ~35k to
    load all 40 in order to use one, which is exactly what `mlai-games`' registry hit.

    Every argument defaults to today's behaviour: no style file, `single-subject`, no
    labels. So the call that produced the four covers on disk that work still produces a
    byte-identical prompt, and a test pins that.
    """
    _, _, neutral = PALETTES[palette]
    parts = [art]
    if style:
        parts.append(f"STYLE — {style}:\n{load_style(style)}")
    layout_ref = load_layout(layout) if layout else ""
    if layout_ref:
        parts.append(f"LAYOUT — {layout}:\n{layout_ref}")
    if labels:
        listed = ", ".join(f'"{x}"' for x in labels)
        parts.append(_TEXT_CLAUSE_LABELLED.format(headline=headline, neutral=neutral))
        parts.append(_LABELS_CLAUSE.format(listed=listed, neutral=neutral))
        parts.append(f"{_EXCLUSIONS_LABELLED} {_LABELLED_MARKS_CLAUSE} {_FRAME_CLAUSE}")
    else:
        parts.append(_TEXT_CLAUSE.format(headline=headline, neutral=neutral))
        parts.append(f"{_EXCLUSIONS} {_MARKS_CLAUSE} {_FRAME_CLAUSE}")
    return "\n\n".join(parts)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def compose_text_free_prompt(headline: str, art: str) -> tuple[str, bool]:
    """The fallback render's prompt: the art direction with the HEADLINE PRUNED OUT, then
    the no-text clause.

    Not `art + clause`, which is what it was and which was a contradiction by
    construction. `parse_art_direction` *requires* the art direction to mention the
    headline — that check is what stops the model asking for a picture the text was never
    going to appear in — so the art direction always contains a sentence like `the words
    "X" sit in the calm upper-left`. Appending "this picture contains no writing of any
    kind" to that leaves the model to resolve a direct conflict, and it is free to resolve
    it either way. Measured against the fake transport before this existed: it kept the
    words, so a path whose entire purpose is a text-free cover produced a cover with text.

    Returns `(prompt, pruned)`. `pruned=False` means every sentence named the headline and
    dropping them would have left less than `MIN_ART_CHARS` to paint, so the full art
    direction is sent and the clause is the only thing arguing against text — strictly
    weaker, and the caller says so out loud rather than reporting a clean fallback.
    """
    needle = headline.strip().lower()
    kept = [s for s in _SENTENCE_SPLIT.split(art.strip()) if needle not in s.lower()]
    remainder = " ".join(kept).strip()
    if len(remainder) < MIN_ART_CHARS:
        return f"{art}\n\n{_NO_TEXT_CLAUSE}", False
    return f"{remainder}\n\n{_NO_TEXT_CLAUSE}", True


# ---------------------------------------------------------------------------
# Pixels — decoding the PNG, with no browser and no Pillow
# ---------------------------------------------------------------------------
#
# This section is the reason the pivot away from Chrome was cheap. It was written to
# measure covers that Chrome had rasterised, and it never knew that: it reads bytes out of
# a PNG file. Verified rather than assumed at the pivot — all four bake-off PNGs from three
# different vendors decode here with `readable=True`, so every number below is produced the
# same way for a painted cover as for a drawn one, which is what makes the SVG-era corpus a
# legitimate comparison population for the thresholds above.


def _norm_hex(value: str) -> str:
    """`#abc` -> `#AABBCC`. Shorthand and case are not a difference worth reporting."""
    v = value.strip().upper()
    if len(v) == 4:
        return "#" + "".join(c * 2 for c in v[1:])
    return v


def png_scanlines(path: Path):
    """(width, height, channels, rows) for an 8-bit non-interlaced PNG, stdlib only.

    Pillow is not in this project's venv and a cover generator is a poor reason to
    add it, so the PNG is decoded here: IHDR for the dimensions, then zlib plus
    scanline unfiltering. `rows` is a generator of unfiltered `bytearray`s, or None
    when the encoding is one this cannot read (see below).

    Split out from `png_probe` only so it can be checked against a real decoder —
    while the unfilter was welded to the uniformity test, the only observable was
    one boolean, and a wrong unfilter that happens to produce a non-uniform image
    passes that (rule 18, and rule 25's "measure the thing").
    """
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"{path} is not a PNG")

    width = height = 0
    bit_depth = colour_type = interlace = -1
    idat = bytearray()
    pos = 8
    while pos + 8 <= len(raw):
        (length,) = struct.unpack(">I", raw[pos : pos + 4])
        kind = raw[pos + 4 : pos + 8]
        body = raw[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, bit_depth, colour_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", body[:13]
            )
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length

    # Chrome writes 8-bit non-interlaced RGB/RGBA. Anything else (palette, 16-bit,
    # Adam7) is reported as unreadable rather than decoded wrongly.
    channels = {0: 1, 2: 3, 6: 4}.get(colour_type, 0)
    if bit_depth != 8 or interlace != 0 or channels == 0 or not idat:
        return width, height, channels, None

    def rows():
        data = zlib.decompress(bytes(idat))
        stride = width * channels
        prev = bytearray(stride)
        at = 0
        for _ in range(height):
            if at + 1 + stride > len(data):
                return
            filt = data[at]
            line = bytearray(data[at + 1 : at + 1 + stride])
            at += 1 + stride
            # PNG filters 0-4, per spec: each byte is reconstructed from its left
            # neighbour (`a`), the byte above (`b`) and the one above-left (`c`).
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                x = line[i]
                if filt == 1:
                    line[i] = (x + a) & 0xFF
                elif filt == 2:
                    line[i] = (x + b) & 0xFF
                elif filt == 3:
                    line[i] = (x + (a + b) // 2) & 0xFF
                elif filt == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    line[i] = (x + pred) & 0xFF
            prev = line
            yield line

    return width, height, channels, rows()


def png_probe(path: Path) -> tuple[int, int, bool | None]:
    """(width, height, has_more_than_one_colour), where the third value is **None**
    when the encoding could not be read.

    The uniformity question is the one that matters: a silently failed raster is not
    an empty file, it is a flat rectangle of exactly the right size, which a header
    check alone would pass.

    `None` rather than `True` for an encoding we decline, because `True` is
    indistinguishable from a real verdict and every caller would read it as "fine"
    — which is fail-open *quietly*, the thing rule 21 is about. The caller has to
    notice and say so.
    """
    width, height, channels, rows = png_scanlines(path)
    if rows is None:
        return width, height, None  # unreadable encoding: decline to judge
    first: bytes | None = None
    for line in rows:
        pixels = [bytes(line[i : i + channels]) for i in range(0, len(line), channels)]
        if first is None and pixels:
            first = pixels[0]
        if any(p != first for p in pixels):
            return width, height, True
    return width, height, False


# ---------------------------------------------------------------------------
# What the pixels say (the skill's own instruments, run rather than described)
# ---------------------------------------------------------------------------

# sRGB -> linear, precomputed. WCAG's relative luminance needs the linearised
# channel, and doing the pow() per pixel over 2 million pixels is the difference
# between a check and a coffee break.
_LINEAR = [
    (c / 255 / 12.92) if (c / 255) <= 0.04045 else (((c / 255) + 0.055) / 1.055) ** 2.4
    for c in range(256)
]


def luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance. The one implementation — `_measure_png` calls it per
    sampled pixel and `contrast` calls it on declared hexes (rule 23)."""
    return 0.2126 * _LINEAR[r] + 0.7152 * _LINEAR[g] + 0.0722 * _LINEAR[b]


def luma(r: int, g: int, b: int) -> float:
    """Display luma (Rec.709 weights on the sRGB values as stored), 0.0-1.0.

    Deliberately NOT `luminance()` above, which linearises first. Both are "brightness" and
    they are not interchangeable: this one is what `MIN_ACCENT_SHARE`'s calibration table was
    measured with, and re-running that table through the WCAG version collapses it and
    interleaves the two populations — see the note above `ACCENT_MIN_LUM`. Two functions
    rather than one is the point here, each named for the thing it is right for: WCAG
    luminance for a contrast ratio, display luma for "is this pixel bright".
    """
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def hex_rgb(value: str) -> tuple[int, int, int]:
    """`#abc` or `#AABBCC` -> `(r, g, b)`, so the colour helpers take a table hex."""
    h = _norm_hex(value).lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def contrast(hex_a: str, hex_b: str) -> float:
    """The WCAG contrast ratio between two hexes, as `PALETTES` stores them.

    Exists so the palette table's contrast claim can be EXECUTED rather than asserted in
    a comment. It was asserted in a comment, and running it showed the comment was wrong
    for THREE of the five rows — including a white-on-yellow 1.43:1. I had predicted two
    by eye before running it, which is rule 25 landing on my own estimate as well as on
    the table. See the note above `PALETTES`.
    """
    lums = [luminance(*hex_rgb(value)) for value in (hex_a, hex_b)]
    hi, lo = max(lums), min(lums)
    return (hi + 0.05) / (lo + 0.05)


# HUE_MIN_VALUE / HUE_MIN_SATURATION gate whether a pixel counts as carrying a hue at all.
# Greys and near-blacks do not: counting them would make every cover with white type read
# as one family richer than it is, and `#111111` is on three rows of the table.
HUE_MIN_VALUE = 40
HUE_MIN_SATURATION = 0.20
HUE_FAMILIES = 12  # 30-degree bins


def hsv_saturation(r: int, g: int, b: int) -> float:
    """HSV saturation, which is what `TH-SATURATION` averages over the canvas.

    Note what this does to black: `#111111` scores 0.0, not "unmeasurable". That is
    correct for the gate — a cover that is half black IS less saturated — and it is the
    reason the depth tones are shades rather than tints, since a tint scores low here too.
    """
    hi, lo = max(r, g, b), min(r, g, b)
    return ((hi - lo) / hi) if hi else 0.0


def hue_family(r: int, g: int, b: int) -> int | None:
    """Which of 12 thirty-degree hue bins this pixel falls in, or None for grey.

    Factored out of `_measure_png`'s sampling loop so `TH-HUES` and the depth-tone
    assertions run the same arithmetic (rule 23). Inside that loop it was uncallable and
    therefore untested, which is exactly how a table of hexes came to carry a contrast
    claim that was false on three rows.
    """
    hi, lo = max(r, g, b), min(r, g, b)
    chroma = hi - lo
    if hi < HUE_MIN_VALUE or not chroma or chroma / hi < HUE_MIN_SATURATION:
        return None
    if hi == r:
        h6 = ((g - b) / chroma) % 6
    elif hi == g:
        h6 = (b - r) / chroma + 2
    else:
        h6 = (r - g) / chroma + 4
    return int(h6 * 60 // (360 // HUE_FAMILIES)) % HUE_FAMILIES


def _measure_png(path: Path, *, step: int = 4) -> dict:
    """Colour and legibility statistics for a finished cover.

    Every number here is a *statistic* over the image, so it is computed on every
    `step`-th pixel in both axes: a 1824x1024 painted cover sampled at step 4 is
    ~117,000 pixels, which is far more than any of these percentages needs and about 16x
    faster in pure Python. The squint grid still gets 16 samples per output cell, so its
    box average is an average rather than a point sample.

    Returned separately from `_check_png` so the thresholds can be calibrated against
    real files by printing these, instead of being reasoned about (rule 25). Every number
    in the config block was set that way, and re-set that way at the pivot: this same
    function produced both populations, which is the only reason the SVG-era covers and
    the painted ones are comparable at all. Use THIS to compare a future run, not a fresh
    ad-hoc script — measuring the SVG floor with a hand-written counter is what produced a
    figure that was exactly double, twice.
    """
    width, height, channels, rows = png_scanlines(path)
    out: dict = {
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
        "readable": rows is not None,
    }
    if rows is None:
        return out

    grid_w = min(SQUINT_W, width) or 1
    grid_h = max(1, round(grid_w * height / width)) if width else 1
    cells = [[0.0, 0] for _ in range(grid_w * grid_h)]

    sat_sum = 0.0
    samples = 0
    accent_hits = 0
    hues = [0] * HUE_FAMILIES
    # A 1001-bin histogram of WCAG relative luminance. A histogram rather than a list
    # because the percentiles are all that is wanted and 130k floats is pointless.
    lum_bins = [0] * 1001

    for y, line in enumerate(rows):
        if y % step:
            continue
        gy = (y * grid_h) // height if height else 0
        row_base = gy * grid_w
        for x in range(0, width, step):
            i = x * channels
            r, g, b = line[i], line[i + 1], line[i + 2]

            sat = hsv_saturation(r, g, b)
            sat_sum += sat
            samples += 1

            family = hue_family(r, g, b)
            if family is not None:
                hues[family] += 1

            lin = luminance(r, g, b)
            lum_bins[int(lin * 1000)] += 1
            # Both conditions, on the same pixel: a bright grey is not an accent and neither
            # is a saturated near-black. That conjunction is the whole discriminating power —
            # each half on its own is one of the two statistics already measured here, and
            # neither of them separates the covers (see MIN_ACCENT_SHARE). `luma`, not the
            # `lin` on the line above: same pixel, different brightness definition, and using
            # the WCAG one here silently voided the calibration (see ACCENT_MIN_LUM).
            if luma(r, g, b) > ACCENT_MIN_LUM and sat > ACCENT_MIN_SAT:
                accent_hits += 1

            cell = cells[row_base + min(grid_w - 1, (x * grid_w) // width)]
            cell[0] += 0.2126 * r + 0.7152 * g + 0.0722 * b
            cell[1] += 1

    if not samples:
        out["readable"] = False
        return out

    # Contrast is the ground against the most distant thing drawn ON the ground, so the
    # ground is the modal luminance and the candidates are the bands with a real area
    # share. Deliberately NOT a percentile pair: type is a small share of a cover by
    # design (a 72pt title inks about 3% of the canvas), so a 5th/95th percentile
    # measures the ground against itself. See MIN_CONTRAST_RATIO above both for the covers
    # that caught that and for why this statistic is now reported rather than enforced —
    # on painted input the area-share floor is a property of the anti-aliasing.
    ground_bin = max(range(len(lum_bins)), key=lum_bins.__getitem__)
    ground_lum = ground_bin / 1000
    floor_count = MIN_BAND_SHARE * samples
    ratio = 1.0
    for idx, count in enumerate(lum_bins):
        if count < floor_count:
            continue
        hi, lo = max(idx / 1000, ground_lum), min(idx / 1000, ground_lum)
        ratio = max(ratio, (hi + 0.05) / (lo + 0.05))

    means = [c[0] / c[1] for c in cells if c[1]]
    mean_lum = sum(means) / len(means) if means else 0.0
    variance = sum((m - mean_lum) ** 2 for m in means) / len(means) if means else 0.0

    out.update(
        mean_saturation=sat_sum / samples,
        accent_share=accent_hits / samples,
        contrast_ratio=ratio,
        ground_luminance=ground_lum,
        hue_families=sum(1 for count in hues if count >= samples * 0.01),
        squint_spread=variance**0.5,
        squint_size=(grid_w, grid_h),
        samples=samples,
    )
    return out


def accent_share(path: Path) -> float | None:
    """The bright-saturated pixel share of one PNG, or `None` if it cannot be read.

    A thin `_measure_png` rather than its own pixel walk, and that is rule 23 rather than
    tidiness: this is the function the calibration table in `MIN_ACCENT_SHARE` was produced
    with and the one the tests re-derive it with, so it has to be the same code the gate
    runs. Measuring the SVG floor with a hand-written counter is what produced a figure that
    was exactly double, twice.
    """
    m = _measure_png(path)
    return m.get("accent_share") if m.get("readable") else None


def _check_png(path: Path) -> list[str]:
    """The skill's colour rules, measured on the pixels a student will actually see.

    Returns only the findings a **correction turn can act on**, which after the pivot is
    two: saturation, and the dimensions. Everything else this function measures is printed
    and returned to nobody, deliberately — see the config block for the per-statistic
    measurement, and the module docstring for the summary table.

    That asymmetry is the point rather than an omission. A retry costs an image call, so a
    finding is only worth raising if the words in the retry could plausibly change the
    pixels (rule 24): "your cover reads as grey, saturate it" can, "your PNG is 4.6 MB"
    cannot — there is no phrasing that makes a diffusion model emit fewer bytes, and no
    Pillow here to recompress with. The advisories go to the log, whose reader is an
    operator who *can* act on them by changing the model or the resolution tier.
    """
    m = _measure_png(path)
    if not m["readable"]:
        # Fail open, loudly — a read-only audit of our own output (rule 21/31). Now more
        # reachable than it was: the bytes come from a third-party model rather than from
        # Chrome, and nothing stops a future model returning a 16-bit or interlaced PNG.
        # Verified today for all four bake-off models, which is a statement about those
        # four (rule 18).
        print(
            f"  ⚠️  PIXEL_CHECKS_SKIPPED — {path.name} decodes to an encoding this "
            "reader does not claim (not 8-bit non-interlaced RGB/RGBA), so "
            "TH-SATURATION did NOT run on it"
        )
        return []

    gw, gh = m["squint_size"]
    mb = m["bytes"] / 1024 / 1024
    print(
        f"  ·  pixels: {m['width']}x{m['height']} · {mb:.2f} MB · saturation "
        f"{m['mean_saturation']:.2f} · accent {m['accent_share'] * 100:.1f}% · "
        f"contrast {m['contrast_ratio']:.1f}:1 · "
        f"{m['hue_families']} hue famil{'y' if m['hue_families'] == 1 else 'ies'} · "
        f"squint spread {m['squint_spread']:.0f} at {gw}x{gh}"
    )

    problems: list[str] = []
    if m["mean_saturation"] < MIN_MEAN_SATURATION:
        problems.append(
            f"TH-SATURATION: the finished cover's mean saturation is "
            f"{m['mean_saturation']:.2f}, under the floor of {MIN_MEAN_SATURATION} — it "
            "reads as grey and will disappear in a catalogue. Ask for a saturated, "
            "vivid, high-chroma picture and name the palette hexes as colours in the "
            "prompt; say the light is coloured rather than white. A muted, desaturated, "
            "film-still or misty look is what this floor exists to reject — the skill's "
            "rule is \"saturate more than real life\""
        )

    # The dimension check is a RATIO plus a FLOOR, not an equality: no model on this
    # endpoint accepts a pixel size, so the exact figure is the model's own grid and an
    # equality assertion would break on every model change (see ASPECT_RATIO above).
    if m["width"] and m["height"]:
        aspect = m["width"] / m["height"]
        if abs(aspect - TARGET_ASPECT) / TARGET_ASPECT > ASPECT_TOLERANCE:
            problems.append(
                f"TH-ASPECT: the cover is {m['width']}x{m['height']}, an aspect of "
                f"{aspect:.3f} against the 16:9 target of {TARGET_ASPECT:.3f}. Every card "
                "and og:image slot is 16:9 and a mismatch is cropped by the browser, "
                "usually through the headline. This is not fixable in the art direction — "
                "the request already asks for 16:9, so the model ignored it; change "
                "OPENROUTER_IMAGE_MODEL"
            )
        if m["width"] < MIN_PNG_WIDTH or m["height"] < MIN_PNG_HEIGHT:
            problems.append(
                f"TH-SIZE: the cover is {m['width']}x{m['height']}, under the og:image "
                f"floor of {MIN_PNG_WIDTH}x{MIN_PNG_HEIGHT} — it will be upscaled and "
                "look soft. Not fixable in the art direction: raise the model's "
                "`resolution` tier or change OPENROUTER_IMAGE_MODEL"
            )

    # ---- Advisory from here down. Printed, never retried. -------------------------
    #
    # Each of these was a hard gate in the SVG era and each was measured at the pivot to
    # have NEVER FIRED on 37 real covers, while firing on the painted covers that worked.
    # Keeping them as gates would have made the new medium unshippable on evidence that
    # the old medium never generated (rule 25's trap, from the inside).
    #
    # The saturation band is the newest member and the only one that was a hard gate in
    # THIS medium: 0.10-0.35 is where a dark-ground style lands by construction, so the retry
    # it used to trigger had no satisfying answer (rule 24) — the ground is most of the canvas
    # and neutral by definition, so "be more saturated" is only answerable by changing style.
    if MIN_MEAN_SATURATION <= m["mean_saturation"] < ADVISORY_SATURATION:
        print(
            f"  ⚠️  TH-SATURATION {m['mean_saturation']:.2f} is in the "
            f"{MIN_MEAN_SATURATION}-{ADVISORY_SATURATION} advisory band, which was the hard "
            "floor until it was measured firing on good dark-ground covers. Expected on "
            "chalkboard or dark-atmospheric, where the ground is a large neutral area; on "
            "any other style it is worth a look, since there it may be a washed-out render"
        )
    if m["bytes"] > MAX_PNG_BYTES:
        print(
            f"  ⚠️  TH-BYTES {mb:.2f} MB is over the {MAX_PNG_BYTES / 1024 / 1024:.0f} MB "
            "advisory. Not a defect in the picture and not fixable by a retry — if every "
            "cover reads like this, drop the model's `resolution` tier or change "
            "OPENROUTER_IMAGE_MODEL"
        )
    if m["accent_share"] < MIN_ACCENT_SHARE:
        print(
            f"  ⚠️  TH-ACCENT {m['accent_share'] * 100:.1f}% of pixels are both bright and "
            f"saturated, under the {MIN_ACCENT_SHARE * 100:.0f}% advisory floor — the cover "
            "has no warm pool of light in it and reads as a muddy mass at card size. The "
            "usual cause is the palette applied backwards: the subject painted in the dark "
            "ground colour instead of the bright accent. Advisory, and it only separates "
            "muddy from not-muddy — a cover can clear this floor and still be "
            "unrecognisable, which is what the vision critique is for"
        )
    if m["contrast_ratio"] < MIN_CONTRAST_RATIO:
        print(
            f"  ⚠️  TH-CONTRAST {m['contrast_ratio']:.1f}:1 is under {MIN_CONTRAST_RATIO}:1 "
            "(advisory). On a painted cover this is usually the statistic failing rather "
            "than the cover — anti-aliased type smears across luminance bins. The "
            "legibility claim that matters is the transcription gate below"
        )
    return problems


# ---------------------------------------------------------------------------
# The transcription gate — can the headline actually be read?
# ---------------------------------------------------------------------------
#
# This is what replaced nine SVG geometry rules (TH-TITLE / FONT / MARGIN / SAFE-ZONE /
# TYPE-SIZE / TYPE-FLOOR / ANCHOR / OVERLAP / WORDS), and it is a stronger test than all
# nine together: they measured Arial advance widths against a canvas box to *infer* that
# type would be legible. This asks a vision model to read the finished picture and compares
# what it read, letter for letter, to what was asked for. Illegible, misspelled, cropped,
# swallowed by the artwork, or accompanied by an invented caption all fail the same way.
#
# Measured before it was built (`/tmp/bakeoff/transcribe_probe.py`, spent real money):
# 4 of 4 painted covers transcribed to the asked-for headline after normalisation, a decoy
# differing by TWO LETTERS was rejected 4 of 4, and a synthetic text-free PNG returned
# exactly `NO_TEXT` twice. So the gate discriminates rather than rubber-stamps, which is
# the only property that made it worth making hard.

# The noise the comparison must absorb, and nothing more. Measured from the real replies:
# three of the four models wrapped the headline across lines ('HOW\nNEURONS\nFIRE'), so
# **line breaks are the actual noise** — not preambles and not punctuation, neither of
# which appeared once. Case is folded because a heavy display face is often transcribed
# uppercase whatever it was set in. The quote and dash substitutions are prophylactic:
# unobserved, but a model rendering a typographic apostrophe in "LET'S BUILD" would
# otherwise fail a cover that is perfectly correct.
#
# LETTERS ARE NOT NOISE. Nothing here removes, adds or substitutes a letter, which is why
# the two-letter decoy fails: that is the whole discriminating power of the gate and any
# "helpful" fuzziness (stemming, edit distance, dropping short words) would spend it.
_TEXT_NOISE = (
    ("‘", "'"), ("’", "'"), ("‛", "'"),
    ("“", '"'), ("”", '"'),
    ("–", "-"), ("—", "-"), ("−", "-"),
    (" ", " "), ("…", "..."),
)


def normalise_text(s: str) -> str:
    """Fold transcription noise, preserve every letter.

    `" ".join(s.split())` is doing the load-bearing work: it collapses the line breaks a
    painted headline is wrapped across, and any run of spaces with it.
    """
    s = s.strip().upper()
    for a, b in _TEXT_NOISE:
        s = s.replace(a, b)
    return " ".join(s.split())


def lexical_text(s: str) -> str:
    """`normalise_text` with the letterless tokens dropped — the TH-TITLE comparison form.

    **This exists because the `MARKS` permission and this gate were enforcing opposite
    contracts, and the gate won by destroying the cover.** Measured on the `recursion` cover:
    the art direction asked for brass linked-list tags "each stamped with a numeral and a
    pointer-hook arrow", which is exactly what `MARKS` is for and exactly what makes a linked
    list legible. `transcribe` reads *all* text in the image, so it came back
    `'RECURSION AND DATA STRUCTURES\\n12\\n7\\n19\\n20'`; equality failed; four attempts
    burned; the text-free fallback could not be text-free either, because the digits are part
    of the subject. What shipped had **no headline on it at all** — a worse card than any
    defect this gate was written to catch.

    So the rule is: **strict about letters, tolerant of everything with none.** A token with
    no letter in it is dropped from BOTH sides before comparing. Three consequences, stated
    because two of them are costs:

    * The headline's spelling is still checked letter for letter, and *extra words* in the
      artwork still fail — `MASTERCLASS 2026` keeps its letters and is still caught. That is
      the check that matters, and it is the same "non-lexical only" line the prompt draws.
    * A digit **in the headline** can no longer be enforced: `PYTHON 3 CLASSES` painted as
      `PYTHON CLASSES` now passes. Accepted knowingly — there is no way to be strict about a
      headline digit while permitting a subject's digits, since the transcript does not say
      where in the frame a glyph sat, and the alternative measured above is no headline at all.
    * `spelled_glyphs` deliberately keeps digits (`isalnum`), so the spell-back gate is
      unaffected: `CLASSÆS` is still caught. The two gates ask different questions.
    """
    return " ".join(w for w in normalise_text(s).split() if any(c.isalpha() for c in w))


# How close a transcribed word has to be to a declared label before it counts as that label
# rather than as unasked-for text. `difflib.SequenceMatcher` ratio, stdlib.
#
# **This number is a guess, and it is stated as one because it cannot be calibrated yet** —
# no labelled cover exists to sample, so there is nothing to measure precision against
# (rule 25's bar is ten hand-sampled instances, and the honest count today is zero). What
# CAN be reasoned about is which direction to be wrong in, and the two costs are wildly
# asymmetric:
#
#   too generous → a misspelt label ships, reported as an advisory. Cosmetic.
#   too strict   → a correct cover is rejected, four attempts burn, and the fallback ships
#                  a cover with NO HEADLINE. That is on disk: the `recursion` cover, failed
#                  by this very gate over its own subject's digits.
#
# So it sits in the generous direction deliberately. 0.75 accepts `RECURSSION` for
# `RECURSION` (0.947) and `DEMANDD` for `DEMAND` (0.923) while still rejecting an unrelated
# word — `MASTERCLASS` against `RECURSION` is 0.20. Re-measure once ten labelled covers
# exist; until then this threshold has cost nothing, because a value it lets through is an
# advisory line and not a retry.
LABEL_MATCH_RATIO = 0.75


def account_transcription(
    headline: str, seen: str, labels: tuple[str, ...] = ()
) -> tuple[list[str], list[str]]:
    """Compare the ADDED text read off the picture against the headline AND the labels.

    Returns `(problems, advisories)` — hard findings that drive a retry, and soft ones that
    are printed and recorded and never retried.

    `seen` is the TEXT half of `openrouter.parse_transcription`, never the raw reply: writing
    that belongs to a depicted object — a dial figure, a stencil, a part number — is sorted
    out by the vision model before this function ever sees it, and is not judged at all. That
    split is not a refinement, it is a defect fix. Judging the whole frame flagged incidental
    markings on 4 of 5 live covers on 4 Sep 2026 (`'Ø09'`, `'19068G'`, `'GRADO'`), and two of
    those five shipped with NO headline because the retry that followed asked the model to
    make its subject's writing unreadable and it obliged with the title. The discrimination
    between "added on top" and "part of the thing" is not available to a string rule; it is
    available to a model looking at the pixels, which is where it now lives.

    **Why this replaced a one-line equality, and why the asymmetry is the entire design.**
    The old check was `lexical_text(seen) == lexical_text(headline)`: every word in the frame
    had to be the headline and nothing else. That is a correct gate for a cover that says one
    thing, and it also *forbids* a cover from saying anything — every labelled layout in the
    `infographic` gallery was unreachable by gate rather than by preference, and the prompt
    carried a matching clause telling the model to blur any writing into illegibility. So
    "make the cover informative" and "check the title is right" were in direct conflict, and
    the title won by making the cover mute.

    Three steps, and the strictness is different at each on purpose:

    1. **The headline must appear as a contiguous run of tokens.** Substring instead of
       equality — the only widening the headline gets. Letter for letter, in order, as
       before; what changes is that other words may now exist around it.
    2. **Every other token must be accounted for by a declared label**, fuzzily
       (`LABEL_MATCH_RATIO`). Anything unaccounted for is a HARD `TH-TITLE`, which is what
       still catches `MASTERCLASS 2026`, a watermark, a signature, and the garbled
       `NEN STN NUIT SOT STLE` that a failing render produces.
    3. **A token that matched a label but is not spelled like it** is an advisory
       `TH-LABELS`. Never a retry.

    Hard headline, soft labels, and the measured reason is on disk rather than argued: a
    wobbly label is a blemish, a wobbly headline is a dead card, and six labels have six
    times the chance of one bad glyph. The `recursion` cover is what a hard failure over a
    subject's own text costs — four attempts, then a card with no title on it at all.

    With `labels=()` the verdict is identical to the old equality check on every input that
    matters: exact match passes, and any extra lexical word is unaccounted and fails hard.
    """
    want_tokens = lexical_text(headline).split()
    got_tokens = lexical_text(seen).split()
    problems: list[str] = []
    advisories: list[str] = []

    # Step 1 — the headline, as a contiguous run.
    at = -1
    n = len(want_tokens)
    if n:
        for i in range(len(got_tokens) - n + 1):
            if got_tokens[i : i + n] == want_tokens:
                at = i
                break
    if at < 0:
        problems.append(
            f"TH-TITLE: the picture reads {' '.join(got_tokens)!r} where it must contain "
            f"{' '.join(want_tokens)!r}. A vision model transcribed the finished cover and "
            "the headline is not in it, so a student cannot read the title. Either the "
            "letters are wrong, or the words are too small, too low-contrast, or "
            "overlapping the artwork — ask for the headline larger, in a heavier face, and "
            "in an emptier part of the frame"
        )
        return problems, advisories

    # Step 2 — everything else has to be a label we declared.
    rest = got_tokens[:at] + got_tokens[at + n :]
    label_tokens = [t for x in labels for t in lexical_text(x).split()]
    unaccounted: list[str] = []
    for token in rest:
        if not label_tokens:
            unaccounted.append(token)
            continue
        best = max(label_tokens, key=lambda t: difflib.SequenceMatcher(None, token, t).ratio())
        ratio = difflib.SequenceMatcher(None, token, best).ratio()
        if ratio < LABEL_MATCH_RATIO:
            unaccounted.append(token)
        elif token != best:
            # Step 3 — accounted for, but misspelled. Advisory.
            advisories.append(
                f"TH-LABELS: the painted label reads {token!r} where it was declared "
                f"{best!r} (similarity {ratio:.2f}). Cosmetic, not retried — a misspelt "
                "label is a blemish while a fifth attempt risks shipping a cover with no "
                "headline at all"
            )
    if unaccounted:
        # The fix text names ADDED text only, and that wording is load-bearing rather than
        # tidy. It used to end "and keep incidental writing on the subject too small to
        # read" — and on `recursion` (4 Sep 2026) the model obeyed exactly that: it blurred
        # the largest lettering in the frame, lost the headline, and the cover shipped with
        # no title after four attempts. This finding can now only fire on added text, so
        # asking for the subject's own markings to be suppressed would be feedback the
        # defect it names cannot be fixed by (rule 24).
        problems.append(
            "TH-TITLE: the headline is correct, but the picture also has words laid over "
            "it that were not asked for: "
            + ", ".join(repr(t) for t in unaccounted)
            + ". Every word ADDED to the picture must be either the headline or one of the "
            "declared LABELS. Remove the added caption, subtitle, tagline, watermark, logo "
            "wordmark or signature — keep the headline exactly as large and as legible as "
            "it is, and leave the subject's own markings alone"
        )
    return problems, advisories


def spelled_glyphs(s: str) -> str:
    """The comparison form for the spell-back gate: letters and digits, nothing else.

    Everything the spelling reply adds — the separating spaces, and any punctuation the
    headline itself carries — is dropped from BOTH sides. Word boundaries are gone on
    purpose: `transcribe` already compares them, and asking a model to mark a gap gets the
    marker spelled out. What survives is the glyph sequence, which is the one thing this
    gate exists to check.

    Non-ASCII letters survive as themselves rather than being folded, and that is the whole
    point: `CLASSÆS` must not compare equal to `CLASSES`. Nothing here removes, adds or
    substitutes a letter — the same rule `normalise_text` follows, for the same reason.
    """
    return "".join(ch for ch in normalise_text(s) if ch.isalnum())


# ---------------------------------------------------------------------------
# The vision critique — TH-SUBJECT, TH-STOCK, TH-TRUE
# ---------------------------------------------------------------------------
#
# These three rules had `no gate` in the spec because nothing measurable could reach them:
# they are claims about what the picture MEANS, and no pixel statistic knows whether a
# painting of two crossed ropes is about economics. A vision model is already being called
# for the transcription gate, so asking it three more questions costs ~$0.005.
#
# **Advisory, printed, never retried, and it must stay that way until precision is measured
# on ten hand-sampled covers** (rule 25's bar). Rule 24 is the specific hazard: a judge
# placed inside the retry loop with unmeasured precision flagged 76% of SVG diagrams and
# silently replaced the review that mattered. So this runs ONCE, on the bytes that ship,
# after the loop has finished — it can inform a human, and it cannot burn an image call.
#
# The two covers that prompted it: a course titled "Economics for Developers" got two
# crossed crystals with a spark, then two crossed ropes with a spark. Both spelled the
# headline perfectly and passed every pixel gate. Neither says "economics".
CRITIQUE_PROMPT = (
    "You are reviewing a course cover image. Answer exactly three questions about the "
    "PICTURE, ignoring any text in it.\n\n"
    "1. SUBJECT — Can you name one concrete, specific thing that is clearly depicted? "
    "Answer no if the picture is an abstract arrangement of generic shapes (crossing "
    "lines, ropes, crystals, glowing orbs, gradients, floating cubes) that could "
    "illustrate almost any topic.\n"
    "2. STOCK — Is this free of stock-photo and stock-illustration cliche? Answer no for "
    "a person at a laptop, a flat lay of a desk, a handshake, a lightbulb meaning an "
    "idea, a rocket meaning growth, a generic upward arrow, or a field's logo standing in "
    "for the field.\n"
    "3. TRUE — Is everything depicted factually correct for what it shows? Answer no if a "
    "curve, diagram, formula, mechanism or labelled part is drawn wrongly. Answer yes if "
    "the picture makes no factual claim at all.\n\n"
    "Output exactly three lines and nothing else, in this order and this format:\n"
    "SUBJECT: yes|no - <the thing you can name, or what makes it generic>\n"
    "STOCK: yes|no - <the cliche, or 'none'>\n"
    "TRUE: yes|no - <what is drawn wrongly, or 'no factual claim'>"
)

# id -> (rule, what a `no` means)
_CRITIQUE_RULES = {
    "SUBJECT": "TH-SUBJECT",
    "STOCK": "TH-STOCK",
    "TRUE": "TH-TRUE",
}
_CRITIQUE_LINE = re.compile(
    # `[ \t...]` and NOT `[\s...]` for the separator: `\s` includes the newline, so a bare
    # `STOCK: yes` swallowed the whole next line as its note and `TRUE` then read as
    # unanswered. Caught by the case for a verdict with no explanation after it, which is
    # the shape a terse model actually returns.
    r"^[ \t]*(SUBJECT|STOCK|TRUE)[ \t]*:[ \t]*(yes|no)\b[ \t\-–—:]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_critique(reply: str) -> list[str]:
    """The vision critique as a list of advisory strings — empty when the picture is clean.

    A key the model failed to answer is reported as its own advisory rather than treated as
    a pass. That direction matters: this is a read-only audit, so it fails open (rule 21) —
    but *loudly*, because a critique that quietly returns nothing is indistinguishable from
    a clean cover, which is the whole failure this exists to end.
    """
    seen: dict[str, tuple[bool, str]] = {}
    for key, verdict, note in _CRITIQUE_LINE.findall(reply or ""):
        seen.setdefault(key.upper(), (verdict.lower() == "yes", note.strip()))

    out: list[str] = []
    for key, rule in _CRITIQUE_RULES.items():
        if key not in seen:
            out.append(
                f"{rule}: the critique did not answer {key} — the reply was "
                f"{(reply or '').strip()[:120]!r}. Advisory not evaluated, not passed"
            )
            continue
        ok, note = seen[key]
        if not ok:
            out.append(f"{rule}: {note or 'the vision model answered no and said nothing more'}")
    return out


# Words that carry no subject information, so an overlap on one of them is not evidence that
# the picture shows what was asked for. Short tokens are excluded by length instead of being
# listed, which is why this stays small.
_GROUND_STOPWORDS = frozenset(
    """
    about above across after against along among around because before behind below
    between during from into like near onto over than that their them then there these
    this those through under until upon what when where which while with without
    picture image cover illustration painting drawing scene shows showing depicted
    depicts thing things some other another generic abstract single very many much
    """.split()
)
_GROUND_MIN_WORD = 4


def _ground_terms(text: str) -> set[str]:
    """The subject-bearing words of a phrase, stemmed only of a trailing `s`.

    Plural folding is the one transformation applied, and it is not cosmetic: the commitment
    routinely reads `macrophage` while the transcription reads `macrophages`, and treating
    those as different words would make the advisory fire on a correct cover.
    """
    words = re.findall(r"[a-z]+", (text or "").lower())
    out = set()
    for w in words:
        if len(w) < _GROUND_MIN_WORD or w in _GROUND_STOPWORDS:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > _GROUND_MIN_WORD else w)
    return out


def ground_advisory(subject: str, source: str, critique_reply: str) -> str | None:
    """`TH-GROUND` on the finished picture: does the thing the critique NAMED match the
    thing this run committed to drawing? Advisory, and free.

    Free because the comparison needs no extra call: `CRITIQUE_PROMPT` already asks the
    vision model to name what it sees, and the question stays **blind** — the model is never
    told what was asked for, deliberately, because a model shown the commitment will agree
    with it. So the naming is independent evidence and the comparison happens here, in code.

    The demo case this was written from: the art direction asked for "a macrophage caught
    mid-phagocytosis, pseudopods curling around a rod-shaped bacterium" and the critique
    named "a gold blob swallowing a white pill". Every pixel gate passed, the headline
    transcribed perfectly, and the picture was of the wrong thing.

    **Advisory, computed outside the retry loop, and it stays that way until precision is
    measured on ten hand-sampled covers** (rule 25's bar; rule 24's trap is a judge with
    unmeasured precision placed inside a loop). Word overlap has an obvious false-positive
    mode — a cover that draws exactly the right thing and gets described in different words,
    "a split-flap board" for "price display" — which is a second reason it only prints.

    Returns `None` when there is nothing to say, including when the critique did not answer:
    that case is already reported by `parse_critique` as "not evaluated, not passed", and
    reporting it twice under two different rule IDs would double-count one silence.
    """
    named = ""
    for key, _verdict, note in _CRITIQUE_LINE.findall(critique_reply or ""):
        if key.upper() == "SUBJECT":
            named = note.strip()
            break
    if not named:
        return None
    committed = _ground_terms(subject) | _ground_terms(source)
    seen = _ground_terms(named)
    if not committed or not seen:
        return None
    if committed & seen:
        return None
    return (
        f"TH-GROUND: the picture was asked for {subject!r} (from the curriculum entry "
        f"{source!r}), but the vision model, shown only the picture, named "
        f"{named!r} — no word in common. Either the model painted something else, or the "
        "subject is not recognisable as what it was meant to be. Advisory: word overlap, "
        "so a correct cover described in different words lands here too"
    )


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------


def _require_png(media_type: str, model_used: str) -> None:
    """Fail closed on anything that is not a PNG, and do it once rather than four times.

    Not a retryable problem: `media_type` is a property of the MODEL, identical on every
    attempt, so retrying spends four image calls to learn the same fact (rule 24 — the
    feedback must be fixable by the thing it names, and no art direction changes an
    encoder). Measured: `bytedance-seed/seedream-4.5` returns `image/jpeg` for a request
    identical to the one flux answers in PNG.

    There is no Pillow in this venv, so this cannot be converted; and the cover ships to an
    S3 key ending `.png`, served as `image/png`. A JPEG under that name is a lie the
    browser punishes, so it must not reach `out_png` at all.
    """
    if media_type != "image/png":
        raise openrouter.OpenRouterError(
            f"{model_used} returned {media_type or 'an unlabelled image'}, not image/png. "
            "The cover ships to a .png key served as image/png and there is no image "
            "library here to convert with, so nothing was written. Set "
            "OPENROUTER_IMAGE_MODEL to a model that returns PNG (measured: "
            "openai/gpt-5.4-image-2, black-forest-labs/flux.2-pro, "
            "google/gemini-3-pro-image, openai/gpt-image-2, sourceful/riverflow-v2.5-pro)"
        )


def keep_attempts_enabled() -> bool:
    """Whether to keep each attempt's render beside the cover. Default OFF.

    Read per call rather than captured at import, so a review script can set it after the
    module is loaded — which is how every other flag here is used from `styled.py`.
    """
    return os.environ.get("THUMBNAIL_KEEP_ATTEMPTS", "0").strip() not in (
        "0",
        "",
        "false",
        "no",
    )


def _keep_attempt(out_png: Path, label: str, raw: bytes, image_prompt: str) -> Path | None:
    """Copy one render's bytes to `<stem>.<label>.png`, when asked to.

    **Why this exists, and it is a gap in my own method rather than a feature.** Every attempt
    writes to `out_png` and the next one overwrites it, so at the end of a run the only render
    on disk is the one that shipped. Every failed render is gone — and in this project every
    real finding, including the one that started this work, came from *opening a PNG* (rule
    18). So the one artifact that could explain a failure is the one the loop destroys.

    Measured cost of not having it: `chalkboard` transcribed back as `''` twice on one cover
    and I could not say whether the headline was missing, mis-lit, or simply unreadable to the
    vision model — three different fixes — because the two failing images no longer existed. A
    `TH-TITLE` message says what the transcription *read*, which is not the same as what a
    human would see; treating those as interchangeable is what "measure the thing, don't reason
    about the thing" warns against.

    **Off by default, and that is a per-path decision (rule 31), not caution for its own
    sake.** In the worker the cover is written to `OUTPUT_DIR / "course_thumbnail.png"`, and
    while `phases/thumbnail.py` uploads that one named file — so no extra bytes reach the
    cover's own key either way — `OUTPUT_DIR` is a directory other phases `s3_sync`. Rejected
    renders under a synced prefix is rule 29's shape: bytes nobody validated, sitting where
    something else may later read them as the artifact. A reviewer opting in on a laptop has
    no such prefix.

    It fails soft: a filesystem error here must never cost a cover that was otherwise fine,
    so the failure is printed rather than raised.
    """
    if not keep_attempts_enabled():
        return None
    kept = out_png.with_name(f"{out_png.stem}.{label}.png")
    try:
        kept.write_bytes(raw)
        kept.with_suffix(".prompt.txt").write_text(image_prompt, encoding="utf-8")
    except OSError as exc:
        # Soft, deliberately. A diagnostic that can fail a run is worse than no diagnostic.
        print(f"  ⚠️  could not keep {label} ({exc}) — the cover is unaffected")
        return None
    print(f"    kept {kept.name}")
    return kept


def resolve_text_model(model: str) -> str:
    """The OpenRouter text model to use, given whatever the caller passed.

    The caller passes a **Bedrock** name. `workers/phases/thumbnail.py` reads `MODEL` from
    the environment and forwards it, `curriculum.py` forwards it at four sites, and `MODEL`
    in a worker is `global.anthropic.claude-sonnet-5` — which is not an OpenRouter model
    id and would 400 the very first call with "model not found".

    So a name that is not `vendor/model` shaped is **ignored, out loud**, rather than sent.
    Three reasons this is a translation and not a validation error. It is always wrong for
    this endpoint, so there is nothing to preserve. Raising would fail the phase over the
    *default* configuration, which is rule 24's trap — feedback naming something the
    operator did not choose and cannot act on from here. And the alternative, editing the
    five call sites that forward `MODEL`, would leave a fourth one to be found later by a
    404 in production: better that this function is the only place that knows.
    """
    model = (model or "").strip()
    if not model:
        return openrouter.DEFAULT_TEXT_MODEL
    if "/" not in model:
        print(
            f"  ⚠️  ignoring model={model!r} — that is a Bedrock name and this path talks "
            f"to OpenRouter. Using {openrouter.DEFAULT_TEXT_MODEL} "
            "(set OPENROUTER_TEXT_MODEL to change it)"
        )
        return openrouter.DEFAULT_TEXT_MODEL
    return model


async def generate_thumbnail(
    spine_path: Path,
    out_png: Path,
    *,
    model: str = "",
) -> dict:
    """Generate one course cover. Returns a small report; raises on hard failure.

    `model` is the OpenRouter **text** model that writes the art direction — the image
    model is a separate knob, `OPENROUTER_IMAGE_MODEL`, and the two must not be confused.
    A Bedrock-shaped name is ignored with a printed line; see `resolve_text_model`.
    """
    model = resolve_text_model(model)
    brief = load_brief(spine_path)
    palette = palette_for(brief["title"])
    print(f"→ {brief['title']}")
    print(f"  {len(brief['modules'])} modules · {brief['duration'] or 'duration not stated'}")
    print(f"  palette {palette} · image model {openrouter.DEFAULT_IMAGE_MODEL}")

    out_png = out_png if out_png.suffix.lower() == ".png" else out_png.with_suffix(".png")
    out_png.parent.mkdir(parents=True, exist_ok=True)

    # The art direction is written beside the PNG, replacing the `.svg` sidecar. It is the
    # only record of what was asked for: the PNG cannot be diffed and a cover that comes
    # back wrong is otherwise undebuggable. Deliberately the COMPOSED prompt, exclusions
    # included, because that is the string the model actually answered.
    out_txt = out_png.with_suffix(".prompt.txt")

    art = ""
    headline = ""
    subject = ""
    source = ""
    marks = ""
    # What the vision model actually READ off the object, as opposed to `marks` above, which is
    # what the art direction asked for. Recorded because it is the only place the two can be
    # compared afterwards — a cover whose price board came back as `FUSMIEEISNATEMET` is a real
    # cosmetic defect, and it is deliberately NOT a finding: judging it is what cost two covers
    # their headline (see `TRANSCRIBE_PROMPT`). Kept so a human can look, per rule 25's bar —
    # ten hand-sampled instances before anything here becomes a rule.
    marks_seen = ""
    problems: list[str] = []
    attempts = 0
    # (problem_count, attempt, png_bytes, problems, image_prompt, chosen) — the fallback needs
    # the least-bad image, and "least bad" has to be recorded as it goes: attempt 4 is not
    # reliably better than attempt 2, since each render is a fresh sample rather than an
    # edit of the last. It carries its own `problems` because the fallback has to know WHAT
    # is still wrong, not just how many things are (see the `else` branch), its own
    # prompt because the sidecar must describe the render that actually ships, and `chosen`
    # — the style, layout, labels and label advisories of THAT attempt — for the same reason
    # one level on: the report must describe the picture, not the last one attempted.
    best: tuple[int, int, bytes, list[str], str, dict] | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        prompt = build_prompt(brief, palette, problems if attempt > 1 else None, art)
        try:
            reply, _art_cost = await openrouter.complete_text(prompt, model=model)
        except openrouter.OpenRouterError as exc:
            # A failed art-direction CALL, not a bad reply — and until this was measured it
            # killed the whole phase: one truncated completion propagated out of the loop and
            # no cover shipped, on a run where three of the four calls had already succeeded.
            # It belongs on the same path as an unusable reply for the same reason that one
            # is a retry: it has cost no image call, and the next turn may simply work.
            # Still bounded by MAX_ATTEMPTS, and `best is None` after the loop raises with
            # the last problem — so a real outage is reported, never silently absorbed.
            print(f"  attempt {attempt}: the art-direction call failed — {exc}")
            problems = [
                f"TH-FORMAT: the previous turn produced no usable reply ({exc}). Answer with "
                "ONLY the eight fields — SUBJECT, SOURCE, MARKS, STYLE, LAYOUT, LABELS, "
                "HEADLINE, PROMPT — and no deliberation before them."
            ]
            continue
        try:
            # `brief` passed, so an invented `SOURCE:` raises here — before any image is
            # bought. That ordering is the point of the check, not an implementation detail.
            direction = parse_art_direction(reply, brief)
            subject, source, marks, headline, art = direction[:5]
        except ArtDirectionError as exc:
            # Costs one Claude call and no image call, so it is the cheapest possible
            # retry — and it must be a retry rather than a raise, because the fix is
            # simply "answer in the format", which the next turn is told.
            print(f"  attempt {attempt}: unusable art direction — {exc}")
            problems = [f"TH-FORMAT: {exc}"]
            continue

        image_prompt = compose_image_prompt(
            headline,
            art,
            palette,
            style=direction.style,
            layout=direction.layout,
            labels=direction.labels,
        )
        print(f'  attempt {attempt}: headline "{headline}" · {len(image_prompt)} char prompt')
        print(f'    subject "{subject}" ← curriculum: "{source}"')
        print(f'    marks "{marks}"')
        print(f"    style {direction.style or '(none)'} · layout {direction.layout}")
        if direction.labels:
            print(f"    labels {' | '.join(direction.labels)}")
        raw, media_type, cost = await openrouter.generate_image(
            image_prompt, aspect_ratio=ASPECT_RATIO
        )
        _require_png(media_type, openrouter.DEFAULT_IMAGE_MODEL)

        # Written straight to the output path rather than to a temp copy, so the bytes the
        # gates measure are the exact bytes that ship (rule 29 — the defect that had S3
        # holding pre-repair drafts for months was precisely this gap).
        out_png.write_bytes(raw)
        out_txt.write_text(image_prompt, encoding="utf-8")
        print(f"    ${cost:.4f} · {len(raw) / 1024 / 1024:.2f} MB")
        _keep_attempt(out_png, f"attempt{attempt}", raw, image_prompt)

        problems = _check_png(out_png)
        # Initialised here, not in the `else:` below, because the transcription gate fails
        # OPEN: on an API error the else-branch never runs and a name bound only there
        # would make an outage a NameError instead of a skipped audit.
        label_notes: list[str] = []

        _, _, varied = png_probe(out_png)
        if varied is None:
            print("  ⚠️  UNIFORMITY_CHECK_SKIPPED — the PNG encoding could not be read")
        elif not varied:
            # Retryable, unlike in the SVG era where this meant the rasteriser had failed
            # silently. A model returning one flat colour is a bad sample, and the next
            # sample is likely fine.
            problems.append(
                "TH-FLAT: the whole cover is a single flat colour — nothing was painted. "
                "Describe a concrete subject with a light source on it"
            )

        # The gate. Runs on every attempt including a clean one, because a cover with
        # perfect colour and an unreadable headline is the failure this replaced nine
        # geometry rules to catch.
        try:
            seen, t_cost = await openrouter.transcribe(raw)
        except openrouter.OpenRouterError as exc:
            # Fail OPEN here, loudly, and only here. The transcription is a read-only
            # audit of our own output; a vision-API outage must not turn a good cover into
            # four wasted image calls and then a text-free fallback (rule 21/31). The
            # asymmetry with `_require_png` is deliberate: that one is a write.
            print(f"  ⚠️  TH-TITLE_GATE_SKIPPED on attempt {attempt} — {exc}")
        else:
            # What this gate proves, and what it does not. The comparison proves the HEADLINE
            # is spelled right and is legible enough for a vision model to read, and that no
            # unasked-for *word* was added on top of the picture. It is deliberately blind to
            # the writing that belongs to an object in the frame — the digits on a price
            # board, the part number on a casting, the numerals on a linked-list tag — because
            # the prompt asks for exactly those and a gate that then rejects them is two
            # halves of this file enforcing opposite contracts. That is not a hypothetical: it
            # cost the `recursion` and `python-oop` covers their entire headline on 4 Sep 2026.
            #
            # The split is the vision model's, not a rule of ours — see `TRANSCRIBE_PROMPT`
            # for why the discrimination has to happen at the pixels. `seen_marks` is recorded
            # and printed and never judged.
            seen_text, seen_marks = openrouter.parse_transcription(seen)
            print(f"    transcribed {seen_text!r} (${t_cost:.4f})")
            if seen_marks:
                print(f"    · object markings (recorded, not judged): {seen_marks!r}")
                marks_seen = seen_marks
            title_problems, label_notes = account_transcription(
                headline, seen_text, direction.labels
            )
            problems.extend(title_problems)
            for note in label_notes:
                print(f"    ⚠️  {note}")
            if not title_problems:
                # ---- The glyph gate, and ONLY when the word gate passed ----------------
                #
                # Second question, one call, ~$0.005. It runs on the pass path because that
                # is where the hole is: a headline the transcription already rejects has its
                # finding, and buying a second opinion to confirm it would spend money to
                # learn nothing. The measured escape it closes shipped clean — `CLASSÆS`
                # transcribed as `MASTER PYTHON CLASSES`, because a model asked for words
                # answers with the word it expects (see `SPELL_PROMPT`).
                #
                # Fails OPEN, loudly, on an API error, for the same reason as the gate above:
                # this is a read-only audit of our own output, and an outage must not turn a
                # correct cover into four wasted image calls (rule 21/31).
                try:
                    spelled, s_cost = await openrouter.spell_back(raw)
                except openrouter.OpenRouterError as exc:
                    print(f"  ⚠️  TH-GLYPH_GATE_SKIPPED on attempt {attempt} — {exc}")
                else:
                    print(f"    spelled {spelled!r} (${s_cost:.4f})")
                    want_g, got_g = spelled_glyphs(headline), spelled_glyphs(spelled)
                    if got_g != want_g:
                        problems.append(
                            f"TH-GLYPH: read letter by letter the painted headline spells "
                            f"{got_g!r}, but it must spell {want_g!r}. The words gate above "
                            "passed, so this is a malformed or substituted CHARACTER that "
                            "reads as the right word at a glance — a ligature (Æ for AE), a "
                            "doubled or dropped letter, or a shape that is not a letter at "
                            "all. It cannot be fixed by moving the text: ask for the "
                            "headline in a plain heavy condensed sans-serif with no "
                            "ligatures and no decorative letterforms, and spell it out "
                            "letter by letter in the prompt"
                        )

        if best is None or len(problems) < best[0]:
            # The 6th slot carries what this ATTEMPT chose, and it exists because the cover
            # that ships is routinely not the last one generated. Reporting `direction.style`
            # from the loop variable would name attempt 4's style beside attempt 2's pixels —
            # the same class of mistake as the sidecar always holding the last prompt, fixed
            # a few lines below for the same reason. `label_notes` rides here too: an
            # advisory about a label is a statement about specific pixels.
            best = (
                len(problems),
                attempt,
                raw,
                list(problems),
                image_prompt,
                {
                    "style": direction.style,
                    "layout": direction.layout,
                    "labels": list(direction.labels),
                    "label_advisories": list(label_notes),
                },
            )

        if not problems:
            print(f"  ✓ clean on attempt {attempt}")
            break
        print(f"  attempt {attempt}: {len(problems)} problem(s)")
        for p in problems:
            print(f"    - {p}")
    else:
        # ---- The text-free fallback, and ONLY when the text is what failed -----------
        #
        # Four attempts have failed to produce a readable headline. Shipping the
        # least-bad of them means shipping a cover with visibly WRONG words on it, and a
        # misspelled title is worse than no title: the correct title is already rendered
        # as page text beside the cover, so the words in the picture add nothing and
        # subtract credibility. So one final render asks for a picture with no text at
        # all, and the same vision model confirms it is text-free.
        #
        # Costs one image call plus one transcription (~$0.05) on a path that has already
        # spent four of each, and only on that path.
        #
        # The TH-TITLE guard below was not here, and its absence was two defects in one.
        # A flat or desaturated cover repainted without a headline is still flat, so the
        # extra call cannot help; and this branch then *overwrote* `problems` with "no
        # readable headline after 4 attempts", naming a defect that had not occurred while
        # the finding the gates did compute was dropped on the floor — rule 27's shape
        # exactly ("grep for whether a verdict is ever read"), one level up from where it
        # was found. Measured against the fake transport: a single-flat-colour cover whose
        # headline transcribed perfectly four times reported TH-TITLE twice and TH-FLAT
        # not at all.
        # TH-GLYPH counts as a text failure here, alongside TH-TITLE: a headline whose
        # letterforms are malformed is exactly as unshippable as one that reads wrong, and
        # a picture with no headline in it is the same remedy. Adding it to the predicate
        # rather than to a second branch keeps one definition of "the text is what failed".
        residual = best[3] if best else problems
        if not all(p.startswith(("TH-TITLE", "TH-GLYPH")) for p in residual):
            problems = residual
            print(
                f"  ! {MAX_ATTEMPTS} attempts, and what is still wrong is not the text — a "
                "text-free render cannot fix it, so no further call is made"
            )
            for p in problems:
                print(f"    - {p}")
        else:
            print(
                f"  ! headline unreadable after {MAX_ATTEMPTS} attempts — one text-free render"
            )
            problems = [
                f"TH-TITLE: no readable headline after {MAX_ATTEMPTS} attempts; shipped a "
                "text-free cover instead. The course title is rendered as page text beside "
                "the cover, so this is degraded, not broken — but look at it"
            ]
            try:
                image_prompt, pruned = compose_text_free_prompt(headline, art)
                if not pruned:
                    print(
                        "  ⚠️  TH-TITLE_PRUNE_FAILED — every sentence of the art direction "
                        "names the headline, so it is sent as-is and the no-text clause is "
                        "the only thing arguing against text"
                    )
                raw, media_type, cost = await openrouter.generate_image(
                    image_prompt, aspect_ratio=ASPECT_RATIO
                )
                _require_png(media_type, openrouter.DEFAULT_IMAGE_MODEL)
                print(f"    ${cost:.4f} · {len(raw) / 1024 / 1024:.2f} MB")
                # Kept for the same reason as the loop's attempts: this render is discarded
                # entirely if it comes back with text on it, and then the reason a headline
                # kept appearing in a picture that asked for none is unlookable-at.
                _keep_attempt(out_png, "textfree", raw, image_prompt)
                seen, t_cost = await openrouter.transcribe(raw)
                seen_text, fallback_marks = openrouter.parse_transcription(seen)
                print(f"    transcribed {seen_text!r} (${t_cost:.4f})")
                if fallback_marks:
                    print(f"    · object markings (recorded, not judged): {fallback_marks!r}")
                    marks_seen = fallback_marks
                # The TEXT group only, and `lexical_text` on top of it, for the same reason as
                # the gate above: this branch asks "did the render come back free of ADDED
                # words", and a subject whose markings are digits can never come back free of
                # digits — the numerals are the object. Judging it on the flat transcript made
                # the fallback structurally unreachable for exactly the covers that needed it,
                # which is how `economics` shipped with two TH-TITLE problems instead of one,
                # the second of them naming '154 NIZ 25' — stencilling on a crate.
                if lexical_text(seen_text) not in ("", lexical_text(openrouter.NO_TEXT)):
                    # The one thing this render had to achieve, it did not. Keep the
                    # least-bad earlier cover rather than a fresh one with unasked-for words.
                    problems.append(
                        f"TH-TITLE: the text-free render is not text-free either — it reads "
                        f"{normalise_text(seen_text)!r}. Kept the best earlier attempt"
                    )
                else:
                    # No labels and no layout: this render is the text-free fallback, so it
                    # carries neither by construction. Saying so explicitly beats inheriting
                    # the failed attempt's choices into the report for a picture that has
                    # none of them.
                    best = (
                        len(problems),
                        MAX_ATTEMPTS + 1,
                        raw,
                        list(problems),
                        image_prompt,
                        {
                            "style": direction.style,
                            "layout": SINGLE_SUBJECT,
                            "labels": [],
                            "label_advisories": [],
                        },
                    )
                    attempts = MAX_ATTEMPTS + 1
            except openrouter.OpenRouterError as exc:
                problems.append(f"TH-TITLE: the text-free render also failed — {exc}")

    if best is None:
        raise RuntimeError(
            "no cover was produced: every attempt failed before an image was returned. "
            f"Last problems: {problems}"
        )

    # One write, at the end, of the bytes that ship AND the prompt that produced them. The
    # per-attempt write above exists so `_check_png` has a path to measure (rule 29 — the
    # gates must read the shipped bytes, not a copy), not to decide what ships. Before this,
    # the sidecar always held the LAST attempt's prompt while the PNG could be an earlier
    # attempt or the text-free render, which makes the one debugging record for an
    # un-diffable artifact actively misleading.
    out_png.write_bytes(best[2])
    out_txt.write_text(best[4], encoding="utf-8")
    if problems:
        print(f"  ! shipping attempt {best[1]} with {len(problems)} unresolved problem(s)")

    # ---- The vision critique. One call, on the bytes that ship, outside the loop. --------
    # Advisory by the same per-path reasoning as GAMES-BELOW-FLOOR (rule 31): a cover whose
    # art is generic is weaker, not broken, and a five-hour course run must not fail over it.
    # `THUMBNAIL_CRITIQUE=0` disables it without a rebuild, matching SVG_FLOOR /
    # GAME_FLOOR_RATE. An OpenRouter failure here is reported and swallowed — this is an
    # audit, and refusing to return a cover we already have would be strictly worse.
    # Seeded with the SHIPPED attempt's label findings, so a misspelt label is recorded even
    # when the critique is disabled or fails. They belong here rather than in `problems` for
    # the reason `account_transcription` gives: retrying over a label risks the whole
    # headline, which is a failure already on disk.
    advisories: list[str] = list(best[5].get("label_advisories") or [])
    if os.environ.get("THUMBNAIL_CRITIQUE", "1").strip() not in ("0", "false", "no"):
        try:
            reply, c_cost = await openrouter.ask_about_image(CRITIQUE_PROMPT, best[2])
            # `extend`, not `=` — the list is pre-seeded with the label findings above, and
            # an assignment here would discard them silently whenever the critique ran.
            advisories.extend(parse_critique(reply))
            # TH-GROUND, from the same reply and the same call: the critique names what it
            # sees WITHOUT being told what was asked for, so comparing the two costs nothing
            # and the naming stays independent evidence.
            ground = ground_advisory(subject, source, reply)
            if ground:
                advisories.append(ground)
            print(f"    critiqued (${c_cost:.4f})")
        except openrouter.OpenRouterError as exc:
            advisories.append(
                f"TH-SUBJECT/TH-STOCK/TH-TRUE: the critique could not run — {exc}"
            )
        for a in advisories:
            print(f"  ⚠️  {a} (advisory)")

    width, height, _ = png_probe(out_png)
    # Measured on the SHIPPED bytes, not on the last attempt's — `_check_png` runs per
    # attempt and the cover that ships may be an earlier one (rule 29's shape: report the
    # statistic for the artifact the student gets). One extra pixel walk, sampled at step 4.
    shipped_accent = accent_share(out_png)
    spend = usage.snapshot()
    print(f"  ✓ {out_png}  {width}x{height}  {out_png.stat().st_size / 1024:.0f} KB")
    print(f"  ✓ {out_txt}")
    print(
        f"  ${spend['total_cost']:.4f} · {spend['input_tokens']:,} in / "
        f"{spend['output_tokens']:,} out · {spend['api_calls']} call(s)"
    )
    return {
        "png": str(out_png),
        "prompt": str(out_txt),
        "headline": headline,
        # What the run committed to drawing, and where in the curriculum it came from. Both
        # ride the report dict and stay OFF the `##PHASE##` marker — `courses.py::_parse_marker`
        # splits the marker body on `:` and a subject phrase is full of them, exactly as
        # `advisories` already does.
        "subject": subject,
        "source": source,
        # The markings the run committed to, kept beside the subject for the same reason:
        # the PNG cannot be diffed, so what was asked for is only recoverable from here and
        # the sidecar. Off the marker with the other two.
        "marks": marks,
        # What was read back off the object, beside what was asked for. Off the marker with
        # the rest of this group.
        "marks_seen": marks_seen,
        # The two new dimensions, and the words painted on the picture. Read from `best[5]`
        # rather than from the loop variable, so they describe the attempt that SHIPPED.
        # Off the `##PHASE##` marker with everything else here — a layout name is safe but a
        # label is curriculum prose full of `:`, which `_parse_marker` splits on.
        "style": best[5].get("style", ""),
        "layout": best[5].get("layout", SINGLE_SUBJECT),
        "labels": best[5].get("labels", []),
        "palette": palette,
        "width": width,
        "height": height,
        # `None` when the encoding could not be read, never 0.0 — a cover whose pixels were
        # not measured must not be indistinguishable from one measured at zero (the shape of
        # the `input_tokens BIGINT DEFAULT 0` problem, which is why those rows can never be
        # backfilled).
        "accent_share": shipped_accent,
        "attempts": attempts,
        "problems": problems,
        # Separate from `problems` on purpose. `thumbnail.py` prints `problems` and ships
        # anyway; these are weaker still — a judgement with unmeasured precision — so they
        # must not be counted where a future reader might make them blocking by accident.
        "advisories": advisories,
        **spend,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate one course thumbnail (PNG).")
    ap.add_argument("spine", type=Path, help="path to course_spine.json")
    ap.add_argument("--out", type=Path, default=Path("thumbnail.png"), help="output .png")
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="the CLAUDE model that writes the art direction (not the image model — "
        "that is OPENROUTER_IMAGE_MODEL)",
    )
    args = ap.parse_args(argv)

    if not args.spine.exists():
        print(f"no such spine: {args.spine}", file=sys.stderr)
        return 2
    try:
        asyncio.run(generate_thumbnail(args.spine, args.out, model=args.model))
    except Exception as exc:  # noqa: BLE001 — a CLI should report, not traceback
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
