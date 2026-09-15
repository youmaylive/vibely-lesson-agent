"""Cases for thumbnail_agent and openrouter. Stdlib only, no key, no network.

    uv run python thumbnail_agent.test.py

Exit 0 = passed, 1 = a case failed, 2 = the suite could not run. Sections that need
something absent from the worker image (the installed skill, the full-size bake-off PNGs)
skip with a loud banner and are COUNTED rather than passing quietly — a gate that cannot
run must not report success (rule 21).

`workers/Dockerfile` runs this at BUILD time, which is what it is really for. It replaced
`raster_gate.py`, which proved the Chrome renderer that no longer exists: without a gate
there, a broken cover generator is discovered on the first course of a ~5 h run. So
everything here is offline by construction — the network calls are exercised through their
*parse* functions and through fakes, which is why `openrouter.py` splits
`parse_image_response` out of `generate_image` at all.

Most of what is here exists because of a defect a real run produced. In the order found:

* `test_palette_contrast_is_computed_not_claimed` — the claim "every neutral-on-ground pair
  clears WCAG AA, computed not eyeballed" lived in a comment and was false on THREE of five
  rows, the worst being white type on a yellow ground at **1.43:1**. It shipped for weeks.
* `test_spec_and_gate_agree` — `MIN_ANY_PX` was 11 while the brief told the model labels may
  be `font-size="10"`, so every conforming cover was rejected with a correction it could not
  satisfy (rule 24). Those constants are retired, the coupling is not: this is now one
  assertion per enforced number, plus an ID-by-ID diff of the spec against the code.
* `test_check_png_separates_the_two_populations` — the calibration itself, as cases. A floor
  that cannot fail on the known-bad input is decoration; one that fires on known-good input
  is worse than none.
* `test_real_cover_fixtures` — the pivot's load-bearing assumption, executed. `png_scanlines`
  was written to read Chrome's output and had never seen a diffusion model's; if it could
  not, every pixel gate would have died with the browser. Four vendors' bytes, downsampled
  (see `fixtures/covers/README.md`).
* `test_generate_thumbnail_*` — the fallback. Four unreadable headlines must ship a
  text-free cover plus a loud `TH-TITLE` problem string and **never raise**, because
  `workers/phases/thumbnail.py` treats a raise as "no cover at all" and a cover is cosmetic
  (rule 31). Exercised against fakes, so the whole retry loop runs with no money spent.
* `test_require_png` — `bytedance-seed/seedream-4.5` answers an identical request with
  `image/jpeg`. There is no Pillow here, and the S3 key ends `.png` and is served as
  `image/png`, so this one fails CLOSED while the transcription gate fails open.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import contextlib
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    spec = importlib.util.spec_from_file_location("thumbnail_agent", HERE / "thumbnail_agent.py")
    ta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ta)
    orr = ta.openrouter
except Exception as exc:  # pragma: no cover - import failure is a suite failure
    print(f"SUITE CANNOT RUN: {exc}")
    raise SystemExit(2)


_PASS = 0
_FAIL = 0
_SKIPPED_SECTIONS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  ✓ {label}")
    else:
        _FAIL += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def skipped(banner: str) -> None:
    """Announce a section that cannot run here — and COUNT it.

    The banner alone was not enough. Sections that need the installed skill or the
    full-size originals `return` early, so the totals read lower in-image than locally with
    nothing in the summary saying checks had gone missing. A skip visible only as prose
    scrolled past 300 lines earlier is the accounting version of failing open quietly
    (rule 21): the number is what gets quoted, so the number has to carry the caveat.
    """
    global _SKIPPED_SECTIONS
    _SKIPPED_SECTIONS += 1
    print(banner)


PAIR = "blue-orange"
G, A, N = ta.PALETTES[PAIR]


# ---------------------------------------------------------------------------
# The palette table — the one piece of the SVG era that survived intact,
# because it is about colour rather than about coordinates.
# ---------------------------------------------------------------------------


def test_palette_contrast_is_computed_not_claimed() -> None:
    """The table's own contrast claim, executed per row. See the module docstring.

    Nothing else could catch it. `TH-CONTRAST` is advisory now and was always measuring the
    ground against the most distant band of *rendered* pixels, so a cover with a dark shape
    and white type on yellow passes on the shape's 13.2:1 while the title is unreadable
    beside it. The live covers hid it too, by the model quietly using the accent for type.
    """
    print("PALETTES (the table's contrast claim, executed)")
    for pair, (ground, accent, neutral) in ta.PALETTES.items():
        type_on_ground = ta.contrast(neutral, ground)
        shape_on_ground = ta.contrast(accent, ground)
        check(
            f"{pair}: the headline clears WCAG AA on its own ground "
            f"({type_on_ground:.2f}:1 >= {ta.MIN_CONTRAST_RATIO})",
            type_on_ground >= ta.MIN_CONTRAST_RATIO,
            f"headline {neutral} on ground {ground} is {type_on_ground:.2f}:1",
        )
        # The accent is a SUBJECT colour and is deliberately NOT held to 4.5:1 — rim light
        # on a molecule is not body text. The floor is blue-orange's 2.58:1, the weakest in
        # the table and the one row whose legibility at 120px was settled by rendering it
        # and looking (rule 18). So the assertion is "no row is worse than the one actually
        # looked at" — a claim about evidence, not a threshold fitted to five numbers.
        check(
            f"{pair}: the subject is no less visible than the row checked by eye "
            f"({shape_on_ground:.2f}:1)",
            shape_on_ground >= ta.contrast("#FF7A1A", "#0B4FD8") - 0.01,
            f"accent {accent} on ground {ground} is {shape_on_ground:.2f}:1",
        )

    check(
        "contrast() is symmetric",
        abs(ta.contrast("#FFFFFF", "#000000") - ta.contrast("#000000", "#FFFFFF")) < 1e-9,
    )
    check(
        "contrast() puts black on white at 21:1, the WCAG maximum",
        abs(ta.contrast("#000000", "#FFFFFF") - 21.0) < 0.01,
        f"{ta.contrast('#000000', '#FFFFFF'):.4f}",
    )
    check(
        "contrast() puts a colour against itself at 1:1",
        abs(ta.contrast("#6A2CC4", "#6A2CC4") - 1.0) < 1e-9,
    )
    # The bug this whole test exists for, pinned as a value: if anyone puts white back in
    # yellow-black's headline column, this is the number they would be shipping.
    check(
        "white on yellow — the shipped-for-weeks pairing — is measurably illegible",
        ta.contrast("#FFFFFF", "#FFD400") < 1.5,
        f"{ta.contrast('#FFFFFF', '#FFD400'):.2f}:1",
    )
    # The one row that cannot use the shared white, recorded as a case so a future tidy-up
    # that "unifies the headline column" fails here instead of on a student's screen.
    check(
        "yellow-black is the row that must not use white, and does not",
        ta.PALETTES["yellow-black"][2] != "#FFFFFF",
        str(ta.PALETTES["yellow-black"]),
    )


def test_palette_is_assigned_not_chosen() -> None:
    """`palette_for` — the fix for a catalogue of near-identical blue cards.

    6 of the 7 covers generated while the row was a free choice came back `blue-orange`.
    That is invisible to every other gate here by construction: this agent only ever sees
    one course, so cross-cover monotony cannot be measured from inside it. Removed by
    making the choice not a choice, which moves the property being tested from "the model
    varies" (unmeasurable) to "the function is a spread hash" (measurable).
    """
    print("palette_for (assignment, not choice)")
    titles = [
        "Neuroscience for Programmers", "Applied Thermodynamics", "CSS Layout in Depth",
        "Organic Chemistry I", "Market Microstructure", "Linear Algebra Done Right",
        "Statistical Inference", "Compilers from Scratch", "Cell Biology",
        "Probability and Randomness", "Distributed Systems", "Digital Signal Processing",
    ]
    rows = [ta.palette_for(t) for t in titles]
    check(
        "every assignment is a row that exists in the table",
        all(r in ta.PALETTES for r in rows),
        str(sorted(set(rows) - set(ta.PALETTES))),
    )
    check(
        "the same title always gets the same row (a regenerate must not reshuffle)",
        rows == [ta.palette_for(t) for t in titles],
    )
    # Whitespace-insensitivity is asserted because the docstring claimed it before the code
    # did: `palette_for` hashed the raw string, so "  Chem " and "Chem" landed on different
    # rows and a spine reformatted by hand would silently repaint the cover.
    check(
        "leading/trailing/internal whitespace and case do not change the row",
        ta.palette_for("  cSs   Layout in   Depth ") == ta.palette_for("CSS Layout in Depth"),
    )
    check(
        f"12 titles reach more than one row ({len(set(rows))} of {len(ta.PALETTES)})",
        len(set(rows)) > 1,
        f"all 12 titles hashed to {rows[0]!r} — the spread is the whole point",
    )
    # A single flat-out assertion on distribution would be a threshold fitted to n=12, so
    # the shape asserted is the weaker true one: no row takes more than half. The real
    # distribution was measured at n=200 (chi-square 2.75 against 4 degrees of freedom).
    worst = max(rows.count(r) for r in set(rows))
    check(
        f"no row takes more than half of a 12-title sample (worst {worst}/12)",
        worst <= 6,
        f"{ {r: rows.count(r) for r in set(rows)} }",
    )


def test_spec_table_matches_the_code() -> None:
    """`PALETTES` and the spec's `TH-PALETTE` table are two copies of one fact.

    The model reads the markdown; the gate reads the dict. Rule 23's divergence in
    miniature, and not hypothetical — the columns were wrong in *both* for three rows, and
    a fix applied to one of them only leaves the model told one thing and checked against
    another. Parsed out of the prose so the two cannot drift silently.

    The table gained two computed columns at the pivot (the ratios), and they get the same
    treatment: a ratio typed by hand into a table the model reads is exactly the kind of
    claim this file exists to execute.
    """
    print("the spec's TH-PALETTE table vs PALETTES")
    if not ta.config.THUMBNAIL_SPEC.exists():
        skipped(f"  ⚠️  SPEC_MISSING — {ta.config.THUMBNAIL_SPEC}")
        return

    rows: dict[str, tuple[str, ...]] = {}
    for line in ta.config.THUMBNAIL_SPEC.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[0] in ta.PALETTES:
            rows[cells[0]] = tuple(cells[1:6])

    check(
        "every row in the code appears in the spec the model reads",
        set(rows) == set(ta.PALETTES),
        f"spec has {sorted(rows)}, code has {sorted(ta.PALETTES)}",
    )
    for pair, cells in rows.items():
        check(
            f"{pair}: ground/accent/headline agree between the spec and the gate",
            tuple(h.upper() for h in cells[:3]) == ta.PALETTES[pair],
            f"spec {cells[:3]} vs code {ta.PALETTES[pair]}",
        )
        ground, accent, neutral = ta.PALETTES[pair]
        for label, claimed, computed in (
            ("neutral-on-ground", cells[3], ta.contrast(neutral, ground)),
            ("accent-on-ground", cells[4], ta.contrast(accent, ground)),
        ):
            try:
                stated = float(claimed.split(":")[0])
            except ValueError:
                check(f"{pair}: the {label} column is a ratio", False, repr(claimed))
                continue
            check(
                f"{pair}: the spec's {label} of {claimed} is what contrast() computes",
                abs(stated - computed) <= 0.01,
                f"spec says {stated}, contrast() says {computed:.4f}",
            )
    check(
        "the table is not a subset — every row carries both ratio columns",
        all(len(c) == 5 and c[3] and c[4] for c in rows.values()),
        str({k: v for k, v in rows.items() if not (v[3] and v[4])}),
    )


# ---------------------------------------------------------------------------
# The vendored skill, and the filter that decides what reaches the model
# ---------------------------------------------------------------------------


def test_load_skill() -> None:
    print("load_skill (the vendored skill)")
    if not ta.config.THUMBNAIL_SKILL.exists():
        skipped(
            "  ⚠️  SKILL_MISSING — the vendored skill is absent, so the filter is\n"
            f"      UNVERIFIED here. Expected at {ta.config.THUMBNAIL_SKILL}"
        )
        return
    text = ta.load_skill()
    check("the diffusion CLI does not reach the prompt", "belt " not in text, "found 'belt '")
    check("no shell fence reaches the prompt", "```" not in text)
    check("the frontmatter's allowed-tools is gone", "allowed-tools" not in text)
    for heading in ta._SKILL_KEEP:
        check(f"kept: {heading}", f"## {heading}" in text)
    for heading in ta._SKILL_DROP:
        check(f"dropped: {heading}", heading not in text)

    check(
        "the colour table survives the filter",
        "Blue + Orange" in text and "3 colors maximum" in text,
    )
    check("the 6-word rule survives the filter", "Max 6 words" in text)

    raw = ta.config.THUMBNAIL_SKILL.read_text(encoding="utf-8")
    headings = {line[3:].strip() for line in raw.splitlines() if line.startswith("## ")}
    unaccounted = headings - set(ta._SKILL_KEEP) - set(ta._SKILL_DROP)
    check(
        "every section in the file is either kept or has a documented reason",
        not unaccounted,
        f"unaccounted for: {sorted(unaccounted)} — read them and update _SKILL_KEEP/_SKILL_DROP",
    )

    # The important behaviour: an upstream rename must fail loudly, not ship a brief with
    # the colour rules quietly missing (rule 21/26). This is also what makes the Dockerfile
    # gate worth running — `_DESIGN` is built at IMPORT time, so a lost heading is a build
    # failure here rather than a crash on the first cover of a five-hour run.
    with tempfile.TemporaryDirectory() as tmp:
        renamed = Path(tmp) / "SKILL.md"
        renamed.write_text(raw.replace("## Color Strategy", "## Colour Strategy"), encoding="utf-8")
        try:
            ta.load_skill(renamed)
            check("a renamed section raises rather than dropping the rules", False, "no exception")
        except RuntimeError as exc:
            check(
                "a renamed section raises rather than dropping the rules",
                "Color Strategy" in str(exc),
                str(exc),
            )


def test_vendored_copy_matches_the_installed_one() -> None:
    print("vendored skill drift")
    installed = HERE.parent / ".agents" / "skills" / "youtube-thumbnail-design" / "SKILL.md"
    if not installed.exists():
        skipped(
            "  ⚠️  INSTALLED_SKILL_ABSENT — `.agents/` is not present (expected inside the\n"
            "      worker image), so the drift check is UNVERIFIED here, not passed."
        )
        return
    check(
        "the vendored copy is byte-identical to the installed one",
        installed.read_bytes() == ta.config.THUMBNAIL_SKILL.read_bytes(),
        "re-run the `cp` in PROVENANCE.md, or record why they differ",
    )


# ---------------------------------------------------------------------------
# The prompt/gate coupling — rule 26: a rule stated in a prompt and enforced
# nowhere is a regression no test catches, and the reverse (enforced but never
# stated) is feedback the generator cannot act on.
# ---------------------------------------------------------------------------

# Every ID the code can emit or name, and the IDs the spec's LIVE sections describe, must
# be the same set. This is the pivot's own risk written as a case: 25 rules were retired at
# once, and the two failure directions are a spec still demanding something no gate checks
# (rule 26) and a gate emitting an ID the model cannot look up (rule 24 — feedback naming
# a rule that is not in the brief is feedback nobody can act on).
_ID_RE = re.compile(r"TH-[A-Z]+(?:-[A-Z]+)*")
_RETIRED_HEADING = "## Retired rules"


def _spec_halves() -> tuple[str, str]:
    text = ta.config.THUMBNAIL_SPEC.read_text(encoding="utf-8")
    head, _, tail = text.partition(_RETIRED_HEADING)
    return head, tail


def test_spec_ids_match_the_code() -> None:
    print("spec IDs vs code IDs")
    if not ta.config.THUMBNAIL_SPEC.exists():
        skipped(f"  ⚠️  SPEC_MISSING — {ta.config.THUMBNAIL_SPEC}")
        return
    live, retired_half = _spec_halves()
    check(
        "the spec still has a retired-rules table to split on",
        bool(retired_half),
        f"no {_RETIRED_HEADING!r} heading — a retirement with no record is rule 26's defect",
    )

    source = (HERE / "thumbnail_agent.py").read_text(encoding="utf-8")
    code_ids = set(_ID_RE.findall(source))
    live_ids = set(_ID_RE.findall(live))
    # The first column of the retired table only. IDs mentioned in a retired row's PROSE
    # are deliberately not collected: several rows explain themselves by naming the live
    # rule that took over ("now held by TH-SATURATION"), which is the record working.
    retired_ids = {
        cells[0].strip().strip("`")
        for line in retired_half.splitlines()
        if line.strip().startswith("|")
        for cells in [line.strip().strip("|").split("|")]
        if cells and cells[0].strip().strip("`").startswith("TH-")
    }

    check(
        f"every ID the code emits is described in a live section ({len(code_ids)} IDs)",
        code_ids <= live_ids,
        f"emitted but not in the brief: {sorted(code_ids - live_ids)} — the model is told "
        "to fix a rule it cannot look up (rule 24)",
    )
    check(
        "every ID the spec still demands is one the code can act on",
        live_ids <= code_ids,
        f"stated but enforced nowhere: {sorted(live_ids - code_ids)} — either gate it or "
        "move it to the retired table (rule 26)",
    )
    check(
        f"no retired ID is still live in the code ({len(retired_ids)} retired)",
        not (retired_ids & code_ids),
        f"both retired and emitted: {sorted(retired_ids & code_ids)}",
    )
    check(
        "and no retired ID is still demanded by a live section",
        not (retired_ids & live_ids),
        f"retired but still in the brief: {sorted(retired_ids & live_ids)}",
    )
    print(f"     live={len(live_ids)} retired={len(retired_ids)} code={len(code_ids)}")


def test_spec_and_gate_agree() -> None:
    """One assertion per enforced number. See the module docstring for why."""
    print("prompt/gate agreement")
    d = ta._DESIGN
    check(
        f"the brief states the word cap the gate enforces ({ta.MAX_TEXT_WORDS})",
        f"at most {ta.MAX_TEXT_WORDS} words" in d.lower() or f"{ta.MAX_TEXT_WORDS} words" in d,
    )
    check(
        f"the brief states the saturation floor ({ta.MIN_MEAN_SATURATION})",
        str(ta.MIN_MEAN_SATURATION) in d,
    )
    check(
        f"the brief states the advisory contrast ratio ({ta.MIN_CONTRAST_RATIO})",
        f"{ta.MIN_CONTRAST_RATIO}:1" in d,
    )
    check(
        f"the brief states the dimension floor ({ta.MIN_PNG_WIDTH}x{ta.MIN_PNG_HEIGHT})",
        f"{ta.MIN_PNG_WIDTH}×{ta.MIN_PNG_HEIGHT}" in d
        or f"{ta.MIN_PNG_WIDTH}x{ta.MIN_PNG_HEIGHT}" in d,
    )
    check(
        f"the brief states the aspect tolerance (±{ta.ASPECT_TOLERANCE:.0%})",
        f"{ta.ASPECT_TOLERANCE:.0%}" in d,
    )
    check(
        f"the brief states the byte advisory ({ta.MAX_PNG_BYTES // 1024 // 1024} MB)",
        f"{ta.MAX_PNG_BYTES // 1024 // 1024} MB" in d,
    )
    check(
        f"the brief states the attempt budget the loop actually uses ({ta.MAX_ATTEMPTS})",
        f"{ta.MAX_ATTEMPTS} attempts" in d,
    )
    check(
        f"the brief names the aspect ratio that is requested ({ta.ASPECT_RATIO})",
        ta.ASPECT_RATIO in d,
    )
    check(
        "the brief names the image model whose default it documents",
        orr.DEFAULT_IMAGE_MODEL in d,
        f"_DESIGN does not mention {orr.DEFAULT_IMAGE_MODEL}",
    )
    check(
        "the brief names the vision model that reads the cover back",
        orr.DEFAULT_VISION_MODEL in d,
        f"_DESIGN does not mention {orr.DEFAULT_VISION_MODEL}",
    )
    # The negative direction, and the reason it is here: the SVG spec kept a rule for
    # months after its gate was deleted. Any of these strings in a LIVE section means the
    # model is being told to author a document nobody parses.
    live = _spec_halves()[0] if ta.config.THUMBNAIL_SPEC.exists() else ""
    for dead in ("Return the SVG document only", "<svg", "viewBox", "text-anchor", "font-family="):
        check(
            f"no live section instructs the model to author SVG ({dead!r})",
            dead not in live,
            f"found {dead!r} in a live section — the model would return a document the "
            "image endpoint cannot use",
        )
    check(
        "the brief does NOT state a hue cap, because the gate has none",
        not hasattr(ta, "MAX_HUE_FAMILIES"),
        "a cap came back without the calibration that removed it (it never fired on 37 covers)",
    )


BRIEF = {
    "title": "Economics for Developers: Model Markets in Code",
    "description": "Build market simulations.",
    "audience": "Developers",
    "duration": "45-55 hours",
    "modules": ["Scarcity", "Supply and demand"],
}

# The shape `load_brief` actually returns now. Kept separate from BRIEF, which stays as the
# THIN case on purpose: a spine with titles and no `key_concepts` is real (2 of the 36 on
# this machine), and `render_curriculum` has to render it rather than print nothing.
RICH_BRIEF = {
    **BRIEF,
    "objectives": ["Build a supply-demand simulator", "Model a price ceiling"],
    "prerequisites": ["Basic Python"],
    "curriculum": [
        {
            "title": "Scarcity",
            "description": "Where economics starts.",
            "concepts": ["Opportunity cost", "Production Possibility Frontier (PPF)"],
            "builds": "a resource allocator that forces trade-offs",
            "why": "every later model assumes it",
            "stuck": "why a fever helps rather than harms",
            "seeds": ["a night-shift cleaning crew"],
        },
        {
            "title": "Supply and demand",
            "description": "",
            "concepts": ["Demand: law of demand, demand curves, determinants of demand"],
            "builds": "",
            "why": "",
            "stuck": "",
            "seeds": [],
        },
    ],
    "concepts": [
        "Opportunity cost",
        "Production Possibility Frontier (PPF)",
        "Demand: law of demand, demand curves, determinants of demand",
    ],
    "trimmed": [],
}


def test_build_prompt() -> None:
    print("build_prompt")
    first = ta.build_prompt(BRIEF)
    check("the course title reaches the prompt", BRIEF["title"] in first)
    check("module titles reach the prompt", "Supply and demand" in first)
    # Split on the HEADING, not on the bare word: the spec's TH-GROUND section now says
    # "the COURSE block" twice, so `split("COURSE")[1]` is a 900-char slice of the spec and
    # this assertion silently stopped looking at the course block at all.
    check(
        "the word cap is repeated beside the title, where it gets broken",
        f"at most {ta.MAX_TEXT_WORDS} words" in first.split("\nCOURSE\n")[1],
    )
    check(
        "the curriculum is labelled as the material the subject comes from",
        "the material the subject must come" in first,
    )
    # This block used to end "None of this text goes ON the cover — only the HEADLINE is
    # painted", and that sentence is now WRONG rather than merely stale: `TH-LABELS` paints
    # curriculum text. Pinned as absent in both directions, because leaving it in would tell
    # the model to declare labels in one paragraph and forbid them two lines later, and an
    # image model resolves a contradiction however it likes.
    check(
        "the blanket 'none of this goes on the cover' ban is gone",
        "None of this text goes ON the cover" not in first,
    )
    check(
        "and it is replaced by the checked-label contract, not by silence",
        "ONLY text allowed on the cover besides the headline" in first
        and "checked, as substrings" in first,
    )
    assigned = ta.palette_for(BRIEF["title"])
    ground, accent, neutral = ta.PALETTES[assigned]
    check(
        f"the assigned row's three hexes reach the prompt ({assigned})",
        all(h in first for h in (ground, accent, neutral)),
        f"missing from the prompt: {[h for h in (ground, accent, neutral) if h not in first]}",
    )
    check(
        "and the row is stated as not the model's to change",
        "not yours to change" in first,
    )
    # Asserted on the correction block's own opener, not on the word "rejected": the brief
    # itself contains that word (it explains what the last batch of covers was rejected
    # FOR), so a loose marker fails on turn one and reports a substring collision as a
    # prompt-assembly bug. That mistake was made once here already.
    check(
        "the first turn carries no correction section",
        "Fix exactly these problems" not in first and "PREVIOUS ART DIRECTION" not in first,
    )
    check(
        "the reply format is the LAST thing the model reads",
        first.rindex(ta._REPLY_FORMAT.strip()) > first.rindex(ta._ART_RULES.strip()),
    )

    previous = "A neuron in cross-section, lit from behind, deep indigo field."
    retry = ta.build_prompt(BRIEF, "", ['TH-TITLE: the picture reads "SUPPLYY"'], previous)
    check("the retry names the problem verbatim", 'reads "SUPPLYY"' in retry)
    check(
        "the retry carries the previous art direction to revise",
        "PREVIOUS ART DIRECTION" in retry and previous in retry,
    )
    check("the retry still carries the full brief", ta._DESIGN in retry)
    check(
        "the retry says what kind of edit is even possible on this medium",
        "cannot edit the picture" in retry,
        "a correction turn that thinks it can move pixels will try to",
    )


def test_render_curriculum() -> None:
    """The labels, pinned.

    Rule 26 is the whole reason these are assertions rather than prose: the two "do NOT
    paint" clauses are the only thing standing between the model and the most concrete
    sentences in the brief, which describe exactly what `TH-SUBJECT` and `TH-STOCK` forbid.
    A future edit that tidies the prompt and drops a clause is a regression no other test
    here would see.
    """
    print("render_curriculum")
    block = ta.render_curriculum(RICH_BRIEF)
    check("each module is numbered and titled", "1. Scarcity" in block)
    check("the concepts reach the prompt", "Opportunity cost" in block and "PPF" in block)
    check("concepts are labelled as what the module teaches", "teaches:" in block)
    check("what a module builds is labelled", "builds: a resource allocator" in block)
    check("the struggle hook is labelled as a place to get stuck", "students get stuck on:" in block)
    check("the analogies are labelled as analogies", "taught with the analogies:" in block)
    check(
        "and the analogies carry the clause that says not to paint them",
        "Do NOT paint" in block and "TH-SUBJECT forbids metaphors" in block,
    )
    check(
        "and the stuck-on lines carry the clause that says not to paint the desk",
        "TH-STOCK forbids painting a person" in block,
    )
    # Negative direction: a warning about a field that is absent would be noise the model has
    # to reconcile against a brief that never mentions it.
    thin = ta.render_curriculum(
        {
            "modules": ["Only a title"],
            "curriculum": [
                {
                    "title": "Only a title",
                    "description": "",
                    "concepts": ["Orbitals"],
                    "builds": "",
                    "why": "",
                    "stuck": "",
                    "seeds": [],
                }
            ],
        }
    )
    check(
        "no analogy warning when the spine has no analogies",
        "Do NOT paint" not in thin and "Orbitals" in thin,
    )
    check(
        "a spine with no curriculum at all still renders its titles",
        "Supply and demand" in ta.render_curriculum(BRIEF),
    )
    check(
        "and a spine with nothing at all says so rather than printing an empty list",
        ta.render_curriculum({}) == "  (none listed)",
    )

    full = ta.build_prompt(RICH_BRIEF)
    check("course-level objectives reach the prompt", "Build a supply-demand simulator" in full)
    check("prerequisites reach the prompt", "Basic Python" in full)
    check(
        "an abridged brief says it was abridged",
        "abridged to fit" in ta.build_prompt({**RICH_BRIEF, "trimmed": ["seeds"]}),
        "a cut brief that reads as a whole one makes the model treat an absent field as an "
        "absent fact (rule 21)",
    )
    check(
        "and an un-abridged one does not",
        "abridged to fit" not in full,
    )


def test_load_brief() -> None:
    print("load_brief")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "course_spine.json"
        p.write_text(
            json.dumps(
                {
                    "course_title": "Economics for Developers",
                    "course_description": "Build simulations.",
                    "target_audience": "Developers",
                    "estimated_total_duration": "45-55 hours",
                    "modules": [
                        {"module_title": "Scarcity"},
                        {"module_title": "Supply and demand"},
                    ],
                }
            )
        )
        brief = ta.load_brief(p)
        check("the title is read", brief["title"] == "Economics for Developers")
        check("modules are read", brief["modules"] == ["Scarcity", "Supply and demand"])

        # An older planner shape. Tolerated because a spine that names its modules
        # differently should cost a different key lookup, not a diagnosis.
        p.write_text(json.dumps({"course_title": "Chem", "checkpoints": [{"title": "Orbitals"}]}))
        check("`checkpoints`/`title` are accepted too", ta.load_brief(p)["modules"] == ["Orbitals"])

        p.write_text(json.dumps({"course_title": "Bare"}))
        bare = ta.load_brief(p)
        check(
            "a spine with no modules still loads",
            bare["title"] == "Bare" and bare["modules"] == [],
        )

        p.write_text(json.dumps({}))
        check(
            "a title-less spine falls back to its directory name",
            ta.load_brief(p)["title"] == Path(tmp).name,
        )

        p.write_text(
            json.dumps({"course_title": "Big", "modules": [{"module_title": f"M{i}"} for i in range(30)]})
        )
        check(
            f"the module list is capped at {ta.MAX_MODULES}",
            len(ta.load_brief(p)["modules"]) == ta.MAX_MODULES,
        )

        # ---- the checkpoint trio, at BOTH depths ------------------------------------
        #
        # Measured across the 34 real spines here: 32 nest it under `terminal_checkpoint`, 2 put
        # it at the module's own top level next to `milestone_title`. Reading one depth
        # yields an empty checkpoint for the other shape, which looks exactly like a spine
        # that has none — so both are cases, and the flat one is preferred when both exist.
        p.write_text(json.dumps({
            "course_title": "Nested",
            "learning_objectives": ["Ship it"],
            "prerequisites": ["Basic Python"],
            "modules": [{
                "module_title": "Innate response",
                "module_description": "Macrophages and neutrophils.",
                "key_concepts": ["Phagocytosis", "Cytokines"],
                "narrative_seeds": ["a night-shift cleaning crew"],
                "terminal_checkpoint": {
                    "proof_of_competency": "trace one infection end to end",
                    "why_it_matters": "it is the first line of defence",
                    "struggle_hook": "why a fever helps rather than harms",
                },
            }],
        }))
        nested = ta.load_brief(p)
        row = nested["curriculum"][0]
        check(
            "the trio is found under `terminal_checkpoint`",
            row["builds"].startswith("trace one infection")
            and row["why"].startswith("it is the first")
            and row["stuck"].startswith("why a fever"),
            repr(row),
        )
        check("key_concepts are read", row["concepts"] == ["Phagocytosis", "Cytokines"])
        check("narrative_seeds are read", row["seeds"] == ["a night-shift cleaning crew"])
        check("module_description is read", row["description"] == "Macrophages and neutrophils.")
        check("course-level objectives are read", nested["objectives"] == ["Ship it"])
        check("course-level prerequisites are read", nested["prerequisites"] == ["Basic Python"])
        check(
            "the flat concept union is what a citation will be checked against",
            nested["concepts"] == ["Phagocytosis", "Cytokines"],
        )

        p.write_text(json.dumps({
            "course_title": "Flat",
            "checkpoints": [{
                "milestone_title": "Orbitals",
                "key_concepts": ["Aufbau principle"],
                "proof_of_competency": "fill a shell diagram",
                "why_it_matters": "bonding follows from it",
                "struggle_hook": "why 4s fills before 3d",
            }],
        }))
        flat = ta.load_brief(p)["curriculum"][0]
        check(
            "the trio is found at the module's own top level too",
            flat["builds"] == "fill a shell diagram"
            and flat["why"] == "bonding follows from it"
            and flat["stuck"] == "why 4s fills before 3d",
            repr(flat),
        )
        check("`milestone_title` is the title", flat["title"] == "Orbitals")

        p.write_text(json.dumps({
            "course_title": "Both",
            "modules": [{
                "module_title": "M",
                "struggle_hook": "the flat one",
                "terminal_checkpoint": {"struggle_hook": "the nested one"},
            }],
        }))
        check(
            "when both depths carry it, the flat one wins",
            ta.load_brief(p)["curriculum"][0]["stuck"] == "the flat one",
        )

        # ---- the bound, and HOW it is given up -------------------------------------
        #
        # Uniform by field across every module, never by truncating the module list: the
        # later modules are exactly where a course's distinctive material lives, so dropping
        # the tail would hide half a course while reporting a whole brief.
        long_seed = "x" * ta.MAX_SEED_CHARS
        p.write_text(json.dumps({
            "course_title": "Huge",
            "modules": [{
                "module_title": f"M{i}",
                "module_description": "d" * ta.MAX_MODULE_DESC,
                "key_concepts": ["c" * ta.MAX_CONCEPT_CHARS] * ta.MAX_CONCEPTS_PER_MODULE,
                "narrative_seeds": [long_seed] * ta.MAX_SEEDS_PER_MODULE,
                "terminal_checkpoint": {
                    "proof_of_competency": "p" * ta.MAX_CHECKPOINT_CHARS,
                    "why_it_matters": "w" * ta.MAX_CHECKPOINT_CHARS,
                    "struggle_hook": "s" * ta.MAX_CHECKPOINT_CHARS,
                },
            } for i in range(30)],
        }))
        huge = ta.load_brief(p)
        rendered = ta.render_curriculum(huge)
        check(
            f"an oversized spine is trimmed to the bound ({ta.MAX_CURRICULUM_CHARS} chars)",
            len(rendered) <= ta.MAX_CURRICULUM_CHARS * 1.2,
            f"{len(rendered)} chars",
        )
        check("and it says which fields it gave up", bool(huge["trimmed"]), repr(huge["trimmed"]))
        check(
            f"every one of the {ta.MAX_MODULES} kept modules still contributes",
            len(huge["curriculum"]) == ta.MAX_MODULES
            and all(r["concepts"] for r in huge["curriculum"]),
            "the trim dropped whole modules instead of shrinking each one",
        )
        check(
            "the analogies are the first thing given up, because TH-SUBJECT forbids painting one",
            huge["trimmed"][0] == "seeds",
            repr(huge["trimmed"]),
        )

        # A generated spine can be any shape at all, and a thinner brief is a worse cover
        # while a traceback is no cover.
        p.write_text(json.dumps({
            "course_title": "Ragged",
            "modules": [
                {"module_title": "A", "key_concepts": "a bare string, not a list"},
                {"module_title": "B", "key_concepts": ["ok", None, "", 7]},
                {"module_title": "C", "terminal_checkpoint": None},
                "not a dict at all",
                {"key_concepts": ["untitled but real"]},
                {},
            ],
        }))
        ragged = ta.load_brief(p)
        check(
            "a ragged spine loads without raising, keeping what is usable",
            [r["title"] for r in ragged["curriculum"]] == ["A", "B", "C", ""],
            repr([r["title"] for r in ragged["curriculum"]]),
        )
        check(
            "a bare string where a list was expected is read as one item",
            ragged["curriculum"][0]["concepts"] == ["a bare string, not a list"],
        )
        check(
            "nulls and non-strings inside a list are dropped, not crashed on",
            ragged["curriculum"][1]["concepts"] == ["ok"],
        )


# The real corpus. This is the case that would have caught reading only one checkpoint
# depth, and it is the only one here that sees a spine no one wrote for a test.
def test_load_brief_against_every_real_spine() -> None:
    print("load_brief vs the real spines on this machine")
    roots = [HERE.parent.parent, HERE.parent.parent.parent]
    spines: list[Path] = []
    synthetic: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("course_spine.json"):
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            # `output/covers-review/spines/*` are HAND-WRITTEN harness fixtures, not planner
            # output: they carry module titles and no `key_concepts` at all, which is exactly
            # why the 10 covers generated from them are not a baseline for this change.
            # Counting them here would report the corpus as having modules with no concepts
            # and blame the planner for a file I wrote.
            if "covers-review" in rp.parts:
                synthetic.append(rp.parent.name)
                continue
            spines.append(rp)
    if not spines:
        # Loudly, and counted: the worker image carries no planner output, so this section
        # cannot run there and must not read as a pass (rule 21).
        skipped(
            "  ⚠️  CORPUS_SKIPPED — no course_spine.json found under\n"
            f"      {roots[0]} or {roots[1]}. The 36-spine check did NOT run; the local\n"
            "      run is its only gate."
        )
        return

    over, empty, modules, concepts, checkpoints, bad = [], [], 0, 0, 0, []
    for p in spines:
        try:
            b = ta.load_brief(p)
        except Exception as exc:  # noqa: BLE001 — a raise on real input IS the finding
            bad.append(f"{p.name}: {exc}")
            continue
        block = ta.render_curriculum(b)
        if len(block) > ta.MAX_CURRICULUM_CHARS * 1.2:
            over.append(f"{p.parent.name}: {len(block)}")
        for r in b["curriculum"]:
            modules += 1
            if not r["concepts"]:
                empty.append(p.parent.name)
            concepts += len(r["concepts"])
            if r["builds"] or r["why"] or r["stuck"]:
                checkpoints += 1
    check(f"every one of the {len(spines)} spines loads without raising", not bad, "; ".join(bad[:3]))
    check(
        "no spine renders past the bound",
        not over,
        f"over MAX_CURRICULUM_CHARS: {over[:5]}",
    )
    check(
        f"every module dict yields at least one concept ({modules} modules, {concepts} concepts)",
        not empty,
        f"modules with no key_concepts: {sorted(set(empty))[:5]}",
    )
    check(
        f"the checkpoint trio is found on most modules ({checkpoints}/{modules})",
        checkpoints > modules * 0.8,
        "reading only one of the two depths is what this number catches",
    )
    print(f"     {len(spines)} spines · {modules} modules · {concepts} concepts"
          + (f" · {len(synthetic)} synthetic fixture(s) excluded: {sorted(synthetic)}"
             if synthetic else ""))


# ---------------------------------------------------------------------------
# parse_art_direction — the reply the whole loop hangs off
# ---------------------------------------------------------------------------

_ART = (
    "A single neuron in cross-section, painted as a glowing filament against a deep "
    "indigo field, rim-lit from behind, shallow depth of field. The words HOW NEURONS "
    "FIRE sit in the calm upper-left."
)


def _reply(
    headline: str = "HOW NEURONS FIRE",
    art: str = _ART,
    *,
    marker: str = "PROMPT:",
    subject: str = "a neuron in cross-section",
    source: str = "Opportunity cost",
    # The default `MARKS:` is satisfiable by `_ART` on purpose — "glowing" is in the art
    # direction above, so `check_marks` passes and every pre-existing case here keeps
    # asserting what it was written to assert instead of turning into a TH-MARKS rejection.
    # That is the fixture bug shape this file has hit twice (a case passing on the wrong
    # defect), so the coupling is stated rather than left to be rediscovered.
    marks: str = "the glowing bands along the filament",
    # Omitted by DEFAULT, which is the opposite convention to `marks` above and is
    # deliberate. `parse_art_direction` treats "no brief and none of the three lines" as the
    # pre-galleries contract, so leaving them out is what keeps every case in this section
    # asserting the thing it was written to assert instead of becoming a `TH-FORMAT`
    # rejection. The integration section, which DOES pass a brief, goes through `_full()`
    # below — where all three are mandatory and omitting one is the failure being tested.
    style: str | None = None,
    layout: str | None = None,
    labels: str | None = None,
) -> str:
    lines = []
    if subject is not None:
        lines.append(f"SUBJECT: {subject}")
    if source is not None:
        lines.append(f"SOURCE: {source}")
    if marks is not None:
        lines.append(f"MARKS: {marks}")
    if style is not None:
        lines.append(f"STYLE: {style}")
    if layout is not None:
        lines.append(f"LAYOUT: {layout}")
    if labels is not None:
        lines.append(f"LABELS: {labels}")
    lines.append(f"HEADLINE: {headline}")
    return "\n".join(lines) + f"\n{marker}\n{art}\n"


def test_parse_art_direction() -> None:
    """Forgiving about decoration, strict about substance.

    Every rejection here costs one Claude call and NO image call, which is the reason it is
    a parse rather than a best-effort read: a silently wrong headline makes the
    transcription gate compare the picture against a string nobody asked for, and that
    fails four times and ships a text-free cover for no reason at all.
    """
    print("parse_art_direction")
    direction = ta.parse_art_direction(_reply())
    subject, source, marks, headline, art = direction[:5]
    check(
        "a well-formed reply parses into the five original fields",
        (subject, source, marks, headline, art)
        == (
            "a neuron in cross-section",
            "Opportunity cost",
            "the glowing bands along the filament",
            "HOW NEURONS FIRE",
            _ART,
        ),
    )
    # `ArtDirection` is a NamedTuple with `style`/`layout`/`labels` appended LAST, so every
    # positional index in this file still means what it meant. That ordering is the whole
    # reason ~10 cases below did not have to be rewritten, and it is asserted rather than
    # assumed — a future field inserted in the middle would silently re-point `[3]` at the
    # art direction and every headline case here would start passing on the wrong string.
    check(
        "the five original fields keep their positions 0-4",
        (direction.subject, direction.source, direction.marks, direction.headline,
         direction.art) == tuple(direction[:5]),
    )
    # A reply with no STYLE/LAYOUT/LABELS lines and no brief is the OLD contract, and it
    # still parses — that is what keeps the pre-existing cases in this section meaningful
    # rather than turning them all into TH-FORMAT rejections. The defaults are the
    # single-subject, unlabelled path: byte-identical prompts to the four covers that work.
    check(
        "and with no brief and no new lines, the new fields default to today's behaviour",
        (direction.style, direction.layout, direction.labels) == ("", ta.SINGLE_SUBJECT, ()),
        f"{direction.style!r} {direction.layout!r} {direction.labels!r}",
    )

    check(
        "decoration around the headline is stripped, not rejected",
        ta.parse_art_direction(_reply('**"HOW NEURONS FIRE"**'))[3] == "HOW NEURONS FIRE",
        ta.parse_art_direction(_reply('**"HOW NEURONS FIRE"**'))[3],
    )
    check(
        "a markdown-quoted marker still parses",
        ta.parse_art_direction(
            "> SUBJECT: a neuron\n> SOURCE: Opportunity cost\n> MARKS: the glowing bands\n"
            "> HEADLINE: HOW NEURONS FIRE\n> PROMPT:\n" + _ART
        )[3]
        == "HOW NEURONS FIRE",
    )
    check(
        "internal whitespace in the headline is collapsed",
        ta.parse_art_direction(_reply("HOW   NEURONS\tFIRE"))[3] == "HOW NEURONS FIRE",
    )
    fenced = _reply(art="").rstrip() + f"\n```\n{_ART}\n```\n"
    check(
        "a fenced prompt is unwrapped rather than refused, and the fence does not survive",
        ta.parse_art_direction(fenced)[4] == _ART,
        repr(ta.parse_art_direction(fenced)[4][:60]),
    )

    def rejects(label: str, reply: str, needle: str) -> None:
        try:
            ta.parse_art_direction(reply)
        except ta.ArtDirectionError as exc:
            check(label, needle in str(exc), f"raised, but said: {exc}")
        else:
            check(label, False, "parsed when it should have been rejected")

    rejects(
        "no HEADLINE marker is rejected",
        f"SUBJECT: a neuron\nSOURCE: Opportunity cost\nPROMPT:\n{_ART}",
        "no `HEADLINE:` line",
    )
    rejects(
        "no MARKS marker is rejected",
        _reply(marks=None),
        "no `MARKS:` line",
    )
    rejects("an empty headline is rejected", _reply('""'), "empty")
    rejects(
        f"a headline over the {ta.MAX_TEXT_WORDS}-word cap is rejected before any image call",
        _reply("HOW NEURONS FIRE AND WHY IT MATTERS TODAY"),
        f"over the {ta.MAX_TEXT_WORDS} cap",
    )
    rejects(
        "no PROMPT marker is rejected",
        "SUBJECT: a neuron\nSOURCE: Opportunity cost\nHEADLINE: HOW NEURONS FIRE\n" + _ART,
        "no `PROMPT:`",
    )
    rejects(
        "art direction too short to be a picture is rejected",
        _reply(art="HOW NEURONS FIRE, nice and blue."),
        "too short to be a picture",
    )
    # The structural one. An image model paints only what the prompt asks for, so a prompt
    # that never mentions the headline produces no text — and the gate then fails four
    # times on a picture nobody asked to carry any.
    rejects(
        "art direction that never mentions the headline is rejected",
        _reply(art=_ART.replace("HOW NEURONS FIRE", "the title")),
        "never mentions the headline",
    )
    check(
        "the mention test is case-insensitive, so a lowercase restatement is accepted",
        ta.parse_art_direction(_reply(art=_ART.replace("HOW NEURONS FIRE", "how neurons fire")))[3]
        == "HOW NEURONS FIRE",
    )

    # ---- the commitment lines ---------------------------------------------------------
    rejects("no SUBJECT marker is rejected", _reply(subject=None), "no `SUBJECT:` line")
    rejects("no SOURCE marker is rejected", _reply(source=None), "no `SOURCE:` line")
    rejects("an empty SUBJECT is rejected", _reply(subject='""'), "`SUBJECT:` line is empty")
    check(
        "decoration around the commitment lines is stripped too",
        ta.parse_art_direction(_reply(subject="**a neuron**", source='"Opportunity cost"'))[:2]
        == ("a neuron", "Opportunity cost"),
    )
    # The ordering case, and it is about naming the right defect: a reply with a bad citation
    # AND no PROMPT: marker must report the missing marker, because "your citation is wrong"
    # sends the next turn after the wrong thing entirely.
    rejects(
        "a reply that is unusable AND miscited reports the unusable part first",
        "SUBJECT: x\nSOURCE: harmony\nHEADLINE: HOW NEURONS FIRE\n" + _ART,
        "no `PROMPT:`",
    )


def test_check_source() -> None:
    """`TH-GROUND`'s hard half — deterministic, and run before any image is bought.

    That placement is the point: `ArtDirectionError` costs one text call and zero image
    calls, so the check that can reject a *subject* belongs on this side of the spend, while
    `MAX_ATTEMPTS = 4` image renders sit on the other.
    """
    print("check_source — the citation gate")

    def accepts(label: str, source: str, brief: dict = RICH_BRIEF) -> None:
        try:
            ta.check_source(source, brief)
        except ta.ArtDirectionError as exc:
            check(label, False, f"rejected a real citation: {exc}")
        else:
            check(label, True)

    def refuses(label: str, source: str, needle: str, brief: dict = RICH_BRIEF) -> None:
        try:
            ta.check_source(source, brief)
        except ta.ArtDirectionError as exc:
            check(label, needle in str(exc), f"raised, but said: {exc}")
        else:
            check(label, False, "accepted a citation that is not in the curriculum")

    accepts("a key concept, quoted exactly", "Opportunity cost")
    accepts("a module title", "Supply and demand")
    accepts("case differences are noise", "OPPORTUNITY COST")
    accepts("so is whitespace, including a line break", "Opportunity\n  cost")
    # The measured reason this is a substring match and not equality. Real `key_concepts` are
    # compound clauses, and a model citing the specific part it chose is doing the right
    # thing — rejecting it would burn a retry and teach it to quote a whole clause instead.
    accepts(
        "a precise citation inside a compound concept is accepted",
        "law of demand",
    )
    accepts("a module title inside a longer phrase in the list", "determinants of demand")

    refuses(
        "an invented citation is rejected",
        "harmony",
        "does not appear in this course's curriculum",
    )
    refuses(
        "and the rejection names the fix rather than the failure (rule 24)",
        "harmony",
        "copy it into SOURCE",
    )
    check(
        "the rejection quotes real citations to choose from",
        "Opportunity cost" in _refusal("harmony"),
        _refusal("harmony"),
    )
    # The separator collision, from the first REAL run of this gate: the reply cited
    # `SOURCE: Class Object · Instance Object`, two adjacent concepts joined by the ` · `
    # that `render_curriculum` prints between them. Both halves are real, so the generic
    # refusal ("does not appear in this curriculum") would have been a false statement the
    # model could not act on. It still fails — one subject, one citation — but by naming
    # what actually went wrong.
    refuses(
        "a citation spanning the ` · ` separator is rejected as two entries, not as invented",
        "Opportunity cost · Production Possibility Frontier (PPF)",
        "copies 2 separate entries",
    )
    refuses(
        "and it offers each half by itself, so one turn is enough to fix",
        "Opportunity cost · Production Possibility Frontier (PPF)",
        "`Opportunity cost`",
    )
    # Not everything with a `·` in it is a collision: if only one half is real the citation
    # was still invented, and the generic message is the right one.
    refuses(
        "a `·` with an invented half falls back to the invented-citation message",
        "Opportunity cost · harmony",
        "does not appear in this course's curriculum",
    )
    refuses("a citation too short to carry information is rejected", "AI", "too short")
    refuses("an empty citation is rejected", "   ", "too short")

    # Fails OPEN, loudly: a spine with no titles and no concepts is a thin input, not a bad
    # cover, and refusing every cover for such a course would make the gate the defect
    # (rule 21, and fail-open-vs-closed is per path, rule 31).
    accepts("a spine with nothing to check against fails open", "anything at all", {})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ta.check_source("anything at all", {})
    check(
        "and says out loud that the gate did not run",
        "gate did not run" in out.getvalue(),
        out.getvalue(),
    )


def _refusal(source: str) -> str:
    try:
        ta.check_source(source, RICH_BRIEF)
    except ta.ArtDirectionError as exc:
        return str(exc)
    return ""


# The 8 concepts of `python_v0` module 1, in order — the real `teaches:` line from the run
# that produced this test. Kept verbatim rather than paraphrased, because the assertion
# below is about a byte-for-byte collision between a message and a line of a prompt.
_PY_MODULE_1 = [
    "Namespace",
    "Built-in Namespace",
    "Global Namespace",
    "Local Namespace",
    "Scope",
    "Built-in Scope",
    "Global Scope",
    "Local Scope",
]


def _wide_brief(depth: int = 8, modules: int = 10) -> dict:
    """A brief shaped like `python_v0`: many modules, each with its own concept line."""
    curriculum = [
        {
            "title": f"Module {m}",
            "description": "",
            "concepts": (
                _PY_MODULE_1[:depth]
                if m == 1
                else [f"m{m} concept {i}" for i in range(depth)]
            ),
            "builds": "",
            "why": "",
            "stuck": "",
            "seeds": [],
        }
        for m in range(1, modules + 1)
    ]
    return {
        **RICH_BRIEF,
        "curriculum": curriculum,
        "modules": [r["title"] for r in curriculum],
        "concepts": [c for r in curriculum for c in r["concepts"]],
    }


def test_citation_sample() -> None:
    """The examples a refusal quotes must not be a line the model can paste back.

    Measured, on the run this test comes from. `check_source` refused
    `SOURCE: Namespace · Built-in Namespace · Global Namespace · …` — eight concepts joined
    by the ` · ` that only separates them in the list — and it was RIGHT to: that is eight
    citations, not one, and the model corrected itself on the next turn. The defect was one
    level back. The example list in the *previous* message was `brief["concepts"][:8]`, and
    because `load_brief` walks modules in order, those eight were all of module 1 — byte-
    identical to its `teaches:` line. A message written to name the fix (rule 24) had handed
    over the failure as the thing to copy from.

    So the assertion is not "the sample has 8 items". It is that the sample is not
    reproducible by pasting one line of the prompt.
    """
    print("_citation_sample — the examples a refusal quotes")

    wide = _wide_brief()
    sample = ta._citation_sample(wide)
    check("eight examples are offered", len(sample) == 8, f"got {len(sample)}")

    owners = [
        next(i for i, r in enumerate(wide["curriculum"], 1) if c in r["concepts"])
        for c in sample
    ]
    check(
        "the eight come from eight DIFFERENT modules",
        len(set(owners)) == 8,
        f"modules {owners}",
    )

    # The regression, stated as the incident rather than as the rule: with the old slice this
    # is exactly `' · '.join(_PY_MODULE_1)` and the check below fails.
    joined = " · ".join(sample)
    pasteable = [
        i
        for i, r in enumerate(wide["curriculum"], 1)
        if joined in " · ".join(r["concepts"])
    ]
    check(
        "the sample is not a contiguous run of any single `teaches:` line",
        not pasteable,
        f"reproducible by pasting module {pasteable}'s line: {joined!r}",
    )
    check(
        "and specifically not module 1's, which is what the model pasted back",
        joined != " · ".join(_PY_MODULE_1),
        joined,
    )

    # The old behaviour, pinned as the thing that WAS wrong, so this cannot silently revert.
    old = wide["concepts"][:8]
    check(
        "the front-slice it replaces really was one module's line",
        old == _PY_MODULE_1,
        f"fixture no longer reproduces the incident: {old}",
    )

    # Both refusals quote it, not just the helper — the call sites are the point.
    try:
        ta.check_source("harmony", wide)
    except ta.ArtDirectionError as exc:
        msg = str(exc)
    else:
        msg = ""
    check(
        "TH-GROUND's refusal quotes examples from beyond module 1",
        "m2 concept 0" in msg or "m3 concept 0" in msg,
        msg,
    )
    try:
        ta.check_labels("harmony", wide, "hub-spoke")
    except ta.ArtDirectionError as exc:
        msg = str(exc)
    else:
        msg = ""
    check(
        "TH-LABELS' refusal quotes examples from beyond module 1",
        "m2 concept 0" in msg or "m3 concept 0" in msg,
        msg,
    )

    # A module with one concept each must still spread, and a short course must not pad.
    thin = _wide_brief(depth=1, modules=3)
    check(
        "one concept per module still yields one per module",
        ta._citation_sample(thin) == ["Namespace", "m2 concept 0", "m3 concept 0"],
        ta._citation_sample(thin),
    )

    # The fallbacks, unchanged — a spine with no `curriculum` rows is thin, not broken, and
    # the four spines on disk include two with zero key concepts anywhere.
    check(
        "no curriculum rows falls back to the flat concept list",
        ta._citation_sample({"concepts": ["a", "b"], "modules": ["m"]}) == ["a", "b"],
    )
    check(
        "no concepts anywhere falls back to module titles",
        ta._citation_sample({"curriculum": [], "concepts": [], "modules": ["m1", "m2"]})
        == ["m1", "m2"],
    )
    check("an empty brief yields no examples rather than raising", ta._citation_sample({}) == [])
    check(
        "the cap is honoured on a course far wider than it",
        len(ta._citation_sample(_wide_brief(depth=9, modules=40))) == 8,
    )


def test_check_marks() -> None:
    """`TH-MARKS` — the permission is only worth having if something checks it was used.

    The measured defect this closes: the prompt asked for a split-flap price board "with no
    digits, letters, or symbols printed on any flap", i.e. a price board with no prices. The
    appended clause no longer bans those markings, but a permission nothing checks is a rule
    living in prose (rule 26), so the reply has to commit to the markings in a machine-read
    field and the prompt has to contain them.

    Every case here is a rejection that costs one text call and ZERO image calls — the same
    placement argument as `check_source`, and the reason `test_generate_thumbnail_*` asserts
    the call count rather than only the message.
    """
    print("check_marks — TH-MARKS")

    def accepts(label: str, marks: str, art: str = _ART) -> None:
        try:
            ta.check_marks(marks, art)
        except ta.ArtDirectionError as exc:
            check(label, False, f"rejected: {exc}")
        else:
            check(label, True)

    def refuses(label: str, marks: str, needle: str, art: str = _ART) -> None:
        try:
            ta.check_marks(marks, art)
        except ta.ArtDirectionError as exc:
            check(label, needle in str(exc), f"raised, but said: {exc}")
        else:
            check(label, False, "accepted markings the prompt never asks for")

    board = (
        "A split-flap price board filling the frame, each flap struck with a crisp white "
        "numeral, lit by a single warm lamp above it, deep shadow behind."
    )
    accepts("markings named in MARKS and painted in PROMPT", "crisp numerals on each flap", board)
    accepts("the default fixture's markings are in its art direction", "the glowing bands")
    # Lenient about paraphrase on purpose: a false positive burns a turn to teach the model a
    # wording, while a false negative costs nothing that the picture does not already show.
    accepts(
        "one subject-bearing word is enough — this is a paraphrase check, not a phrase match",
        "white numerals stamped into every single flap of the board",
        board,
    )
    # `none` is the compliant answer for the four covers that actually work: a crate of
    # oranges and a stack of coins read as themselves with nothing written on them.
    accepts("`none` is accepted for an object that reads as itself", "none")
    accepts(
        "and `none` plus the explanation the reply format asks for is still `none`",
        "none — a crate of oranges reads as itself",
        "A crate of ripe oranges at a night market under a bare bulb, "
        "the words HOW NEURONS FIRE in the calm upper-left, painterly.",
    )
    accepts("case and decoration around `none` are noise", "**None.**")

    refuses("an empty MARKS line is rejected", "   ", "is empty")

    # --- branch 1: the markings are named nowhere in the prompt -------------------------------
    # Note what this art direction does NOT contain: any word of the MARKS phrase, and any
    # negation. It exercises the lenient positive test on its own.
    silent = (
        "A split-flap board filling the frame, lit by one warm lamp from above, HOW NEURONS "
        "FIRE in the calm upper-left, deep shadow behind it, painterly."
    )
    refuses(
        "markings named but absent from the prompt are rejected",
        "crisp white numerals",
        "TH-MARKS",
        silent,
    )

    # --- branch 2: the prompt names them and then takes them away ------------------------------
    # The hole the lenient test has, and the shape of the real failure rather than a
    # hypothetical one: "on each flap" is satisfied by an art direction that says "flaps",
    # so the object gets drawn and its markings get blanked, and the positive test passes.
    # `_MARK_NEGATIONS` is what catches it — calibrated on the 21 real art directions on disk
    # at 1 hit / 0 false positives, the hit being this exact cover.
    negated = (
        "A split-flap board filling the frame, its flaps converged flat and blank with no "
        "digits, letters, or symbols printed on any flap, HOW NEURONS FIRE in the calm "
        "upper-left, deep shadow behind it, painterly."
    )
    check(
        "the lenient positive test alone would ACCEPT the real failing prompt",
        # Not a redundant assertion — it is the evidence that branch 2 is load-bearing. If
        # this ever starts failing, the negation scan has become dead code.
        any(t in negated.lower() for t in ta._ground_terms("crisp white numerals on each flap")),
    )
    refuses(
        "so a prompt that negates the markings it named is rejected too",
        "crisp white numerals on each flap",
        "TH-MARKS",
        negated,
    )
    refuses(
        "and the refusal quotes the negating phrase it found, not a generic complaint",
        "crisp white numerals on each flap",
        "'no digits'",
        negated,
    )
    accepts(
        "`no texture` is not `no text` — word boundaries, and the reason `no text` is not "
        "in the list at all (it fired on the WORKING supply-and-demand cover)",
        "crisp white numerals on each flap",
        "A split-flap board, each flap showing a crisp white numeral, against a calm dusk "
        "sky with soft ambient glow and no texture in it.",
    )

    # Rule 24: the message has to name a fix the next turn can act on. "Your markings are
    # missing" is not one; "describe them as something painted" is. Asserted on BOTH branches,
    # because two messages that give different advice for the same defect is the divergence
    # this project keeps paying for.
    for needle in (
        "a price board with no prices on it",
        "each flap showing a crisp numeral",
        "non-lexical",
    ):
        refuses(
            f"and the silent refusal carries {needle!r}, so the next turn knows what to write",
            "crisp white numerals",
            needle,
            silent,
        )
        refuses(
            f"and the contradiction refusal carries {needle!r} as well",
            "crisp white numerals on each flap",
            needle,
            negated,
        )


def test_check_headline() -> None:
    """`TH-WORDS`' second half — the card has to say which course it is for.

    Measured failure: `Economics for Developers` shipped a cover reading `SUPPLY MEETS
    DEMAND`. Short, spelled right, legible, and a student scanning a catalogue cannot tell
    which course the card belongs to. Checked pre-image beside `SOURCE` and `MARKS`.
    """
    print("check_headline — TH-WORDS")
    econ = {"title": "Economics for Developers"}

    def accepts(label: str, headline: str, brief: dict = econ) -> None:
        try:
            ta.check_headline(headline, brief)
        except ta.ArtDirectionError as exc:
            check(label, False, f"rejected a headline that names the course: {exc}")
        else:
            check(label, True)

    def refuses(label: str, headline: str, needle: str, brief: dict = econ) -> None:
        try:
            ta.check_headline(headline, brief)
        except ta.ArtDirectionError as exc:
            check(label, needle in str(exc), f"raised, but said: {exc}")
        else:
            check(label, False, "accepted a headline that names no course")

    accepts("the title itself", "ECONOMICS FOR DEVELOPERS")
    accepts("a shortened form of the title", "ECONOMICS, DEMYSTIFIED")
    accepts("one subject word is enough", "ECONOMICS IN ONE HOUR")
    # `ECONOMIST` against `economics` diverges at the 8th character, so neither is a prefix of
    # the other and prefix matching alone refuses a perfectly good headline. That is what
    # `_SHARED_STEM` is for, and this case is the reason it exists — measured while writing
    # this test, not anticipated.
    accepts("a derived form of the course's word, past where the prefix rule can see", "THINK LIKE AN ECONOMIST")
    check(
        "and that really is past the prefix rule, so the case is not passing for another reason",
        not any(
            a.startswith(b) or b.startswith(a)
            for a in ta._ground_terms("THINK LIKE AN ECONOMIST")
            for b in ta._ground_terms("Economics for Developers")
        ),
    )
    # The morphological near-misses, which is why this is prefix matching on top of
    # `_ground_terms`' plural fold rather than equality. Both are the course's own word.
    accepts(
        "a plural/singular difference is not a different word",
        "THE LIFE OF A STAR",
        {"title": "The Life Cycle of Stars"},
    )
    accepts(
        "and neither is a suffix on the course's own word",
        "COMPOUNDING, VISUALISED",
        {"title": "Compound Interest"},
    )
    accepts(
        "a course whose title word appears only in the subtitle position still passes",
        "PYTHON CLASSES, DEMYSTIFIED",
        {"title": "Master Python Classes"},
    )

    refuses(
        "the measured failure fires: SUPPLY MEETS DEMAND for Economics for Developers",
        "SUPPLY MEETS DEMAND",
        "shares no word with the course title",
    )
    refuses(
        "and the refusal offers the course's own words rather than only naming the defect",
        "SUPPLY MEETS DEMAND",
        "economic",
    )
    # Fails OPEN, loudly: a course called `Go` has no word long enough to carry subject
    # meaning, and refusing every cover for it would make the gate the defect (rule 21).
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ta.check_headline("LEARN TO SHIP", {"title": "Go"})
    check(
        "a title with no subject-bearing word fails open and says so",
        "gate did not run" in out.getvalue(),
        out.getvalue(),
    )
    accepts("and that path raises nothing", "LEARN TO SHIP", {"title": "Go"})


def test_art_rules_point_at_the_artifact() -> None:
    """The prompt rules, pinned in BOTH directions — including the sentence that is gone.

    This is the change that answers "I am not able to recognise it", and it is a change to
    prose, which is the class of change no test catches unless a test is written for it
    (rule 26). Cause 2 was three rules whose intersection was "invent a prop": `TH-GROUND`
    forced an abstract concept, `TH-SUBJECT` banned diagrams and metaphors, and `TH-STOCK`
    banned the field's own obvious object. The corpus says the last of those is simply wrong
    — all four covers that work draw the field's obvious artifact — so the ban is asserted
    ABSENT here, not merely replaced.
    """
    print("art rules — the artifact formula")
    # Whitespace-normalised, and that is not a convenience. Asserting a flat substring against a
    # hand-wrapped triple-quoted constant makes the test fail when a sentence moves across a line
    # break — five of these did on the first run, all of them false alarms about prose that was
    # present and correct. A gate that cries wolf on re-wrapping is a gate someone deletes.
    def flatten(text: str) -> str:
        return " ".join(text.split())

    rules = flatten(ta._ART_RULES)
    reply = flatten(ta._REPLY_FORMAT)
    prompt = flatten(ta.build_prompt(RICH_BRIEF))

    check(
        "TH-GROUND picks the topic and defers the object to rule 2",
        "then do rule 2 with it" in rules,
        "grounding must choose the TOPIC; rule 2 chooses the OBJECT",
    )
    check(
        "TH-SUBJECT states the artifact formula as a question the model can answer",
        "physically handle, trade, read, or build with" in rules,
    )
    for row, verdict in (
        ("a crate of oranges at a night market", "works"),
        ("a stack of gold coins", "works"),
        ("an invented split-flap board", "unrecognisable"),
        ("an invented brass vault door", "unrecognisable"),
    ):
        check(
            f"the measured evidence table carries {row!r} → {verdict}",
            row in rules,
        )
    check(
        "and it says which half of that table is the instruction",
        "the field's OBVIOUS artifact, drawn plainly" in rules,
    )
    # The unblocking. The supply/demand cross and the printed score were both forbidden by a
    # flat ban on diagrams, and a score IS the artifact a music student reads.
    check(
        "a diagram is allowed when the diagram is the artifact",
        "A diagram IS allowed when the diagram is the artifact" in rules
        and "printed score" in rules,
    )
    check(
        "while a diagram as the picture's own structure is still refused",
        "boxes and arrows floating on a background" in rules,
    )

    # ---- the sentence that caused this, asserted ABSENT --------------------------------
    for gone in (
        "not a beaker but the molecule",
        "obvious object for the field",
        "not the field's obvious",
    ):
        check(
            f"TH-STOCK no longer bans the field's own subject matter ({gone!r} is gone)",
            gone not in rules,
            "this ban is what left the model with nothing recognisable to draw",
        )
    check(
        "TH-STOCK still bans the register it should have banned all along",
        all(x in rules for x in ("a person at a laptop", "hands typing", "lens flare")),
    )
    check(
        "and it says out loud what it does NOT ban, so it is not re-tightened by accident",
        "does NOT ban" in rules and "The obvious object IS the right answer" in rules,
    )

    # ---- the palette direction (cause 3's prompt half) ---------------------------------
    check(
        "the palette is applied in a stated direction, not just named",
        "carry the bright accent colour" in rules and "the field BEHIND it" in rules,
    )
    check(
        "and the measured failure is named rather than described in the abstract",
        "Do not name the dark colour as the subject's material" in rules,
    )
    check(
        "the direction is repeated where the hexes are, not only in the rules",
        "is what the SUBJECT is made of" in prompt and "near-black" in prompt,
    )

    # ---- the marks permission, from the rules' side ------------------------------------
    check(
        "the model is told not to write its own exclusion of markings",
        "Do NOT write your own exclusion of markings" in rules
        and "no digits on the flaps" in rules,
    )
    check(
        "and the reply format asks for MARKS above HEADLINE",
        reply.index("MARKS:") < reply.index("HEADLINE:"),
    )
    check(
        "MARKS says it is machine-checked before any picture is bought",
        "Machine-checked before any picture is generated" in reply,
    )
    check(
        "and it offers `none` for an object that reads as itself",
        "`none`" in reply and "crate of oranges" in reply,
    )

    # ---- the one hardcoded style, retired -----------------------------------------------
    # The plan asked for this sentence to be pinned ABSENT. It cannot be: deleting the record
    # of a retired rule is itself rule 26's regression, so it survives in both prompts as a
    # QUOTED retirement. What is asserted instead is the framing — that wherever the sentence
    # appears, the paragraph around it says it is over and names what replaced it. An
    # unframed occurrence is the style system silently coming back.
    for text, label in ((rules, "_ART_RULES"), (flatten(ta._DESIGN), "the spec")):
        occurrences = [
            para
            for para in text.split("  ")
            if "painterly digital illustration" in para
        ]
        for para in occurrences:
            check(
                f"{label}: the retired one-style sentence appears only as a retired rule",
                "TH-STYLE" in text
                and any(w in para or w in text for w in ("used to", "Until this rule", "Replaced")),
                para[:200],
            )
    check(
        "_ART_RULES now sends the model to the galleries instead of naming one medium",
        "TH-STYLE / TH-LAYOUT" in rules and "from the two galleries" in rules,
    )
    # Asserted against the COMPOSED prompt, not `_ART_RULES`: the capitalised headings live in
    # `_GALLERIES` and `_REPLY_FORMAT`, and what matters is that they reach the string the model
    # actually reads. An assertion aimed at the wrong constant fails for the wrong reason — which
    # is what this one did on its first run.
    check(
        "and the two galleries themselves reach the prompt the model reads",
        "STYLE GALLERY" in prompt and "LAYOUT GALLERY" in prompt,
    )
    check(
        "and the reply format asks for all three new fields, above HEADLINE",
        max(reply.index("STYLE:"), reply.index("LAYOUT:"), reply.index("LABELS:"))
        < reply.index("HEADLINE:"),
    )
    check(
        "LABELS says it is checked against the curriculum before any picture is bought",
        "machine-checked against the curriculum" in reply and "must be curriculum text" in reply,
    )
    check(
        "and it says `none` is an acceptable answer, so a single-subject cover is never "
        "forced to invent labels",
        "always an acceptable answer" in reply,
    )


def test_ground_advisory() -> None:
    """`TH-GROUND`'s advisory half — the finished picture against the commitment, for free.

    Free because `CRITIQUE_PROMPT` already asks the vision model to name what it sees, and
    the question stays blind: the model is never told what was asked for, so its naming is
    independent evidence and the comparison happens in code.
    """
    print("ground_advisory")
    good = (
        "SUBJECT: yes - a macrophage engulfing a rod-shaped bacterium\n"
        "STOCK: yes - none\nTRUE: yes - no factual claim\n"
    )
    bad = (
        "SUBJECT: yes - a gold blob swallowing a white pill\n"
        "STOCK: yes - none\nTRUE: yes - no factual claim\n"
    )
    committed = ("a macrophage caught mid-phagocytosis", "Phagocytosis")
    check(
        "the demo failure fires: committed a macrophage, got a blob and a pill",
        (ta.ground_advisory(*committed, bad) or "").startswith("TH-GROUND:"),
        repr(ta.ground_advisory(*committed, bad)),
    )
    check(
        "and the advisory quotes both the commitment and what was seen, so it is readable",
        "macrophage" in (ta.ground_advisory(*committed, bad) or "")
        and "white pill" in (ta.ground_advisory(*committed, bad) or ""),
    )
    check(
        "a picture that shows what was asked for is clean",
        ta.ground_advisory(*committed, good) is None,
        repr(ta.ground_advisory(*committed, good)),
    )
    check(
        "a plural in the transcription is not a different word",
        ta.ground_advisory(
            "a macrophage", "Phagocytosis",
            "SUBJECT: yes - two macrophages on a vessel wall\nSTOCK: yes - none\nTRUE: yes - none\n",
        ) is None,
    )
    check(
        "an overlap on a stopword is not evidence — 'the picture shows' matches nothing",
        (ta.ground_advisory(
            "a macrophage", "Phagocytosis",
            "SUBJECT: no - an abstract picture that shows some generic shapes\n",
        ) or "").startswith("TH-GROUND:"),
    )
    check(
        "a match on the SOURCE alone is enough, since the subject may be worded freely",
        ta.ground_advisory(
            "a split-flap board mid-turn", "Market equilibrium and price signals",
            "SUBJECT: yes - a mechanical price board showing market equilibrium\n",
        ) is None,
    )
    # The KNOWN false positive, pinned rather than described. Word overlap cannot tell
    # "painted the wrong thing" from "painted the right thing and the critique used other
    # words" — a neuron in cross-section IS a myelinated axon. This case exists so that
    # anyone tempted to promote TH-GROUND out of advisory has to delete an assertion that
    # says why they should not (rule 24: a judge of unmeasured precision inside a retry loop
    # once flagged 76% of this project's diagrams). Precision on 10 hand-sampled covers is
    # what would justify it, and that measurement does not exist.
    check(
        "the same thing in different words ALSO fires — the advisory is not precise",
        (ta.ground_advisory(
            "a neuron in cross-section", "Resting membrane potential",
            "SUBJECT: yes - a myelinated axon\nSTOCK: yes - none\nTRUE: yes - none\n",
        ) or "").startswith("TH-GROUND:"),
    )
    # An unanswered SUBJECT is already reported by parse_critique as "not evaluated, not
    # passed". Reporting the same silence again under a second rule ID would double-count it.
    check(
        "an unanswered critique is not turned into a ground failure",
        ta.ground_advisory("a macrophage", "Phagocytosis", "the image looks fine to me") is None,
    )
    check(
        "a verdict with no explanation after it is not a ground failure either",
        ta.ground_advisory("a macrophage", "Phagocytosis", "SUBJECT: yes\nSTOCK: yes\n") is None,
    )
    check(
        "and a run with no commitment at all says nothing rather than guessing",
        ta.ground_advisory("", "", bad) is None,
    )


def test_compose_image_prompt() -> None:
    """The clauses the retry loop must not be able to erode.

    Assembled in code rather than asked for in the reply format, because they are the
    transcription gate's PRECONDITION: the gate compares by exact equality, so a stray
    caption or watermark fails it exactly as hard as a misspelling. Leaving them to a
    generation turn to remember each time is rule 26's failure by construction.
    """
    print("compose_image_prompt")
    out = ta.compose_image_prompt("HOW NEURONS FIRE", _ART, PAIR)
    check("the art direction is carried through unedited", _ART in out)
    check("the headline is named as the text to paint", '"HOW NEURONS FIRE"' in out)
    check(
        "and spelled out a second time as a letter-for-letter instruction",
        out.count("HOW NEURONS FIRE") >= 3,
        f"appears {out.count('HOW NEURONS FIRE')} time(s)",
    )
    check("the headline hex for the assigned row is named", N in out, f"{N} not in the prompt")
    for exclusion in ("watermark", "caption", "signature", "lorem ipsum", "no border"):
        check(f"the exclusions cover {exclusion!r}", exclusion in out.lower())
    check(
        "no negative-prompt syntax is used, because the endpoint has none",
        "negative_prompt" not in out,
    )
    check(
        "every row composes without a KeyError",
        all(ta.compose_image_prompt("X", _ART, p) for p in ta.PALETTES),
    )

    # ---- the split clause, BOTH directions -------------------------------------------
    # This is the causal fix for "I am not able to recognise it", and it is a change to a
    # PROMPT, which is the class of change no test catches unless a test is written for it
    # (rule 26). So both halves are pinned: what the ban still covers, and what it no longer
    # covers. Asserted on `_EXCLUSIONS` itself rather than on the composed prompt, because
    # `_TEXT_CLAUSE` legitimately says "and no other words" about the headline and would
    # satisfy a loose search over the whole string.
    check(
        "the exclusion is scoped to text ADDED to the picture, not to all markings",
        "ADDED" in ta._EXCLUSIONS,
        ta._EXCLUSIONS,
    )
    for gone in ("hidden in the artwork", "no marks", "no numbers", "no digits"):
        check(
            f"and it no longer bans {gone!r} — the clause that blanked the price board",
            gone not in ta._EXCLUSIONS.lower(),
            ta._EXCLUSIONS,
        )
    check(
        "the subject's own markings are asked for positively, in the composed prompt",
        "PART OF THE SUBJECT are wanted" in out,
    )
    for wanted in ("digits on a price board", "notation on a score", "engraving on a coin"):
        check(f"the permission names {wanted!r} as an example", wanted in out)
    # The permission used to carry a blur mandate — "anywhere the object would carry writing,
    # paint it too small and blurred to read as words" — which these two assertions pinned. It
    # is GONE, and its absence is pinned instead, because it was measured doing damage on 4 of
    # 5 live covers (4 Sep 2026): `economics`' split-flap price boards read `GRAD`/`GRADO`
    # instead of prices, and on `recursion` the model obeyed the mandate by blurring the
    # largest text in the frame — the headline — and shipped with no title after 4 attempts.
    #
    # What replaced it is a *preference*, not a rule, and the difference is the point: an
    # image model asked for prose on an object invents letters and paints gibberish
    # (`immune-system-single`'s vial read `FUSMIEEISNATEMET`), which is cosmetic and recorded
    # in `report["marks_seen"]` rather than gated. Gating it is exactly what cost two covers
    # their headline.
    check(
        "the blur mandate is GONE — it is what took the headline down with the small print",
        "too small and blurred to read as words" not in out,
        out,
    )
    check(
        "the subject's markings are now asked for CRISPLY, so a price board shows prices",
        "crisply and legibly" in out,
        out,
    )
    check(
        "figures over words survives as a preference, which is what limits gibberish",
        "Prefer figures, symbols and notation over words" in out,
        out,
    )
    # The count bound, and it is pinned because it came from a measurement rather than a worry.
    # The two covers of the third live run differ in this one dimension: `economics` painted 3
    # marks and every one is correct (`3.20/kg`, `B-27`, `LOT 04`); `python-oop` painted **20**
    # and every one is gibberish (`STANETATG`, `PYITINBER`, `ANPYSTIRRY`, `11:60`), on a cover
    # whose headline was perfect. Legibility does not degrade gradually with quantity, so the
    # quantity is what the prompt asks for. Still a preference and not a threshold — a
    # `marks_seen` token count is gateable, but calibrating one on 4 covers is rule 25's trap,
    # and the vision critique already names the defect precisely.
    check(
        "and the marks are bounded in NUMBER — 3 right marks beat 20 invented ones",
        "Keep them FEW" in out and "not every surface annotated" in out,
        out,
    )
    check(
        "the frame clause survives the split rather than being lost with it",
        ta._FRAME_CLAUSE in out and "letterboxing" in out,
    )
    # The fallback is the one path that must still ban everything: its own check is
    # `normalise_text(seen) != NO_TEXT`, so a painted numeral there is a FAILED render, not a
    # recognisable one. Pinned as a deliberate asymmetry, not an oversight.
    check(
        "the text-free clause is deliberately NOT given the marks permission",
        "PART OF THE SUBJECT" not in ta._NO_TEXT_CLAUSE
        and "no numbers" in ta._NO_TEXT_CLAUSE,
        ta._NO_TEXT_CLAUSE,
    )
    # The fallback clause replaces both of the above and must not smuggle the headline back
    # in: it is asked for on a path whose whole purpose is a picture with no writing on it.
    check(
        "the text-free clause names no headline and asks positively",
        "no writing of any kind" in ta._NO_TEXT_CLAUSE
        and "extend the illustration" in ta._NO_TEXT_CLAUSE,
    )


# ---------------------------------------------------------------------------
# The two galleries — the change the rejected covers are the reason for
# ---------------------------------------------------------------------------

_HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")


def test_galleries_are_closed_over_what_is_on_disk() -> None:
    """Every vendored file is either allowed or declined WITH A REASON — never neither.

    The pair of maps is the whole guard here, and it guards in both directions. A style
    added upstream on the next `npx skillfish add` lands in neither map and fails this case,
    so it cannot arrive unreviewed; a style deleted from the allow-list without a recorded
    reason fails it too, which is rule 26 (a rule dropped silently is a regression no test
    catches). The reasons live beside the list in the source for the same reason
    `_SKILL_DROP` does: the alternative is that they live in someone's memory of a session.
    """
    print("galleries (closed over the vendored trees)")
    style_dir = ta.config.THUMBNAIL_STYLES / "references" / "styles"
    layout_dir = ta.config.THUMBNAIL_LAYOUTS / "references" / "layouts"
    check("the vendored style references are on disk", style_dir.is_dir(), str(style_dir))
    check("the vendored layout references are on disk", layout_dir.is_dir(), str(layout_dir))

    on_disk = {p.stem for p in style_dir.glob("*.md")}
    named = set(ta.STYLE_GALLERY) | set(ta.STYLES_DECLINED)
    check(
        f"every one of the {len(on_disk)} style files is either allowed or declined",
        on_disk <= named,
        f"unreviewed: {sorted(on_disk - named)}",
    )
    check(
        "and nothing is named that is not on disk — a kept style must resolve to a file",
        set(ta.STYLE_GALLERY) <= on_disk,
        f"named but absent: {sorted(set(ta.STYLE_GALLERY) - on_disk)}",
    )
    check(
        "allowed and declined are disjoint, so a style cannot be both",
        not (set(ta.STYLE_GALLERY) & set(ta.STYLES_DECLINED)),
        f"in both: {sorted(set(ta.STYLE_GALLERY) & set(ta.STYLES_DECLINED))}",
    )
    check(
        "every declined style carries a reason long enough to be one",
        all(len(v) > 30 for v in ta.STYLES_DECLINED.values()),
        str({k: v for k, v in ta.STYLES_DECLINED.items() if len(v) <= 30}),
    )

    # Layouts, same shape, with the one deliberate exception: `single-subject` is OURS.
    layouts_on_disk = {p.stem for p in layout_dir.glob("*.md")}
    layout_named = set(ta.LAYOUT_GALLERY) | set(ta.LAYOUTS_DECLINED)
    check(
        f"every one of the {len(layouts_on_disk)} layout files is allowed or declined",
        layouts_on_disk <= layout_named,
        f"unreviewed: {sorted(layouts_on_disk - layout_named)}",
    )
    check(
        "every kept layout except `single-subject` resolves to a file",
        set(ta.LAYOUT_GALLERY) - {ta.SINGLE_SUBJECT} <= layouts_on_disk,
        f"named but absent: {sorted(set(ta.LAYOUT_GALLERY) - {ta.SINGLE_SUBJECT} - layouts_on_disk)}",
    )
    # `single-subject` is the path all four working covers took, so its presence in the
    # gallery is a regression assertion and not bookkeeping: drop it and "informative"
    # becomes mandatory, which is the change that made these covers worse the last time.
    check(
        "`single-subject` IS offered, and has no file of its own",
        ta.SINGLE_SUBJECT in ta.LAYOUT_GALLERY
        and not (layout_dir / f"{ta.SINGLE_SUBJECT}.md").exists(),
    )
    check(
        "layouts allowed and declined are disjoint",
        not (set(ta.LAYOUT_GALLERY) & set(ta.LAYOUTS_DECLINED)),
    )

    # `infographic` ships its own 17 styles and they are declined WHOLESALE — rule 23. The
    # concrete form of the risk is measurable and is asserted rather than described: two
    # files with one name and different contents.
    other = ta.config.THUMBNAIL_LAYOUTS / "references" / "styles"
    if other.is_dir():
        overlap = {p.stem for p in other.glob("*.md")} & set(ta.STYLE_GALLERY)
        differs = [
            n
            for n in sorted(overlap)
            if (other / f"{n}.md").read_bytes() != (style_dir / f"{n}.md").read_bytes()
        ]
        check(
            "the two skills' style galleries overlap by name and DISAGREE by bytes, which "
            "is why only one of them owns the dimension",
            bool(differs),
            f"overlap={sorted(overlap)} differs={differs}",
        )

    # The selection table is REBUILT rather than pasted, because the skill's own table sends
    # you to a declined style in 11 of its 20 rows. This is the assertion that our rebuild
    # did not reintroduce one: a signal row naming a style `check_style` refuses is a retry
    # loop built out of our own documentation.
    signalled = [v for _, v in ta._STYLE_SIGNALS]
    check(
        "every content signal points at a KEPT style",
        all(v in ta.STYLE_GALLERY for v in signalled),
        str([v for v in signalled if v not in ta.STYLE_GALLERY]),
    )
    check(
        "and the gallery tables the model reads name every option, so a choice is never "
        "withheld",
        all(k in ta._GALLERIES for k in ta.STYLE_GALLERY)
        and all(k in ta._GALLERIES for k in ta.LAYOUT_GALLERY),
    )
    # Asserted against the table's KEYS rather than against the whole string, and the
    # difference is not pedantry: a naive substring search fails on `retro`, whose one-line
    # description is "halftone dots, vintage badges, aged print texture". The word `vintage`
    # in a description is prose; `vintage` as an option is a value `check_style` refuses.
    # The `->` filter drops the content-signal rows, which share the table indent but whose
    # first token is a signal phrase rather than a name; their targets are checked by the
    # `_STYLE_SIGNALS` assertion above instead.
    offered = {
        ln.split()[0]
        for ln in ta._GALLERIES.splitlines()
        if ln.startswith("  ") and "->" not in ln
    }
    leaked = sorted(
        (set(ta.STYLES_DECLINED) | set(ta.LAYOUTS_DECLINED)) & offered
    )
    check(
        "no declined name is OFFERED as an option in the prompt the model reads",
        not leaked,
        str(leaked),
    )
    check(
        "and the option list the model sees is exactly the two allow-lists",
        offered == set(ta.STYLE_GALLERY) | set(ta.LAYOUT_GALLERY),
        f"extra={sorted(offered - set(ta.STYLE_GALLERY) - set(ta.LAYOUT_GALLERY))} "
        f"missing={sorted(set(ta.STYLE_GALLERY) | set(ta.LAYOUT_GALLERY) - offered)}",
    )


def test_load_style_and_load_layout() -> None:
    """The section filter, and the one thing it must not let through: a second palette.

    `PALETTES` is the single source of colour — `TH-CONTRAST`, `TH-ACCENT`, `TH-FLAT` and
    the headline hex are all computed against the assigned row — so a style file's own hexes
    reaching the same prompt is a contradiction the image model resolves however it likes.
    That is measured here rather than trusted to the drop list, on every kept style.
    """
    print("load_style / load_layout")
    for name in ta.STYLE_GALLERY:
        text = ta.load_style(name)
        check(f"{name}: resolves and is non-empty", bool(text.strip()), repr(text[:60]))
        check(
            f"{name}: carries no hex colour — PALETTES stays the only source of colour",
            not _HEX.search(text),
            str(_HEX.findall(text)),
        )
        check(
            f"{name}: no dropped section reaches the prompt",
            not any(f"{h}:" in text for h in ta._STYLE_DROP),
            str([h for h in ta._STYLE_DROP if f"{h}:" in text]),
        )
    check(
        "an unknown style is a KeyError rather than a missing-file traceback",
        isinstance(_raised(lambda: ta.load_style("watercolor")), KeyError),
    )
    # The `Typography` drop is the one most likely to be undone by someone reading the file
    # and thinking it looks useful — I had it in the keep list myself. So the measurement is
    # pinned: the letterforms the transcription gate has the hardest time reading back are
    # exactly what these sections mandate.
    hand = [
        n
        for n in ta.STYLE_GALLERY
        if any(
            w in (ta.config.THUMBNAIL_STYLES / "references" / "styles" / f"{n}.md")
            .read_text(encoding="utf-8")
            .lower()
            for w in ("hand lettering", "hand-written", "chalk lettering", "bitmap font")
        )
    ]
    check(
        "at least four kept styles mandate hand-lettered or bitmap type in the section "
        "that is dropped — the reason it is dropped",
        len(hand) >= 4,
        str(hand),
    )
    check(
        "and none of that reaches the composed prompt",
        not any(
            w in ta.load_style(n).lower()
            for n in hand
            for w in ("hand lettering", "hand-written", "chalk lettering", "bitmap font")
        ),
    )

    for name in ta.LAYOUT_GALLERY:
        text = ta.load_layout(name)
        if name == ta.SINGLE_SUBJECT:
            check(
                "`single-subject` injects nothing — it MEANS no structure",
                text == "",
                repr(text),
            )
            continue
        check(f"{name}: resolves and is non-empty", bool(text.strip()), repr(text[:60]))
        check(
            f"{name}: carries no hex colour",
            not _HEX.search(text),
            str(_HEX.findall(text)),
        )
        # `Recommended Pairings` is the trap, not noise: every layout file recommends
        # `infographic`'s OWN styles, all 17 of which are declined. Injecting it would have
        # the prompt recommending a value `check_style` then refuses.
        check(
            f"{name}: `Recommended Pairings` does not reach the prompt",
            "Recommended Pairings" not in text,
        )
        check(
            f"{name}: and no declined style is recommended to the model",
            not [d for d in ta.STYLES_DECLINED if d in text],
            str([d for d in ta.STYLES_DECLINED if d in text]),
        )
    check(
        "an unknown layout is a KeyError",
        isinstance(_raised(lambda: ta.load_layout("periodic-table")), KeyError),
    )

    # Rule 26, the whole reason this is a whitelist with a RAISE in it: an upstream rename
    # must fail loudly rather than ship a cover whose design rules are silently absent while
    # every test here stays green. Exercised on a copy, since the vendored files are verbatim.
    with tempfile.TemporaryDirectory() as t:
        broken = Path(t) / "blueprint.md"
        original = (
            ta.config.THUMBNAIL_STYLES / "references" / "styles" / "blueprint.md"
        ).read_text(encoding="utf-8")
        broken.write_text(original.replace("## Visual Elements", "## Visual Language"))
        exc = _raised(
            lambda: ta._load_reference(broken, ta._STYLE_KEEP, ta._STYLE_OPTIONAL, "style")
        )
        check(
            "a renamed required heading RAISES, and the message names the section and the file",
            isinstance(exc, RuntimeError) and "Visual Elements" in str(exc),
            f"got {exc!r}",
        )
        # Absent-but-not-renamed is NOT an error, and that distinction is the measurement:
        # only `chalkboard` has `Design Aesthetic`/`Style Rules`, so a required-heading list
        # written from that one file would raise on every other one.
        thin = Path(t) / "thin.md"
        thin.write_text("# thin\nA thesis line.\n\n## Visual Elements\nboxes and rules\n")
        out = ta._load_reference(thin, ta._STYLE_KEEP, ta._STYLE_OPTIONAL, "style")
        check(
            "an OPTIONAL heading that is simply absent is not an error",
            "boxes and rules" in out and "A thesis line." in out,
            repr(out),
        )


def test_check_style_and_check_layout() -> None:
    """Exact membership, and a refusal that hands back the fix (rule 24).

    Exact rather than fuzzy because the value names a FILE to open, so "close enough" has
    nowhere to go. What makes that affordable is the error: the whole list comes back, so a
    model that guessed a name is one turn from the right one — and the turn costs one text
    call and zero image calls, which is the cheapest retry in the loop.
    """
    print("check_style / check_layout")
    check("a gallery name passes and normalises", ta.check_style("chalkboard") == "chalkboard")
    check(
        "decoration and case are forgiven, because they are not the model's answer",
        ta.check_style(' **"Chalkboard"**. ') == "chalkboard",
        ta.check_style(' **"Chalkboard"**. '),
    )
    # `blueprint` is the one style that was KEPT and then declined on live covers (5 of 5 came
    # back with garbled pseudo-measurements over the subject; one critique read it back as
    # "boxes with gibberish labels" — the original complaint about these covers). It is pinned
    # here rather than left to the generic unknown-name cases above, because the interesting
    # failure is not a typo: it is the model reaching for the *obvious* register for an
    # engineering course and being refused. If it is ever re-admitted, this line says so.
    exc = _raised(lambda: ta.check_style("blueprint"))
    check(
        "a DECLINED style is refused like any other non-member",
        isinstance(exc, ta.ArtDirectionError) and "TH-STYLE" in str(exc),
        f"got {exc!r}",
    )
    check(
        "and the reason it was declined is recorded beside the allow-list, not lost",
        "blueprint" in ta.STYLES_DECLINED
        and "garbled" in ta.STYLES_DECLINED["blueprint"],
        ta.STYLES_DECLINED.get("blueprint", "<absent>"),
    )
    check("a layout name passes", ta.check_layout("hub-spoke") == "hub-spoke")
    check(
        "`single-subject` is a legal LAYOUT answer, not a fallback",
        ta.check_layout(ta.SINGLE_SUBJECT) == ta.SINGLE_SUBJECT,
    )
    for value, rule, gallery in (
        ("watercolor", "TH-STYLE", ta.STYLE_GALLERY),
        ("oil painting", "TH-STYLE", ta.STYLE_GALLERY),
    ):
        exc = _raised(lambda v=value: ta.check_style(v))
        check(
            f"{value!r} is refused as {rule}",
            isinstance(exc, ta.ArtDirectionError) and rule in str(exc),
            f"got {exc!r}",
        )
        check(
            f"and the refusal lists every allowed name, so the fix is one turn away",
            all(k in str(exc) for k in gallery),
            str(exc),
        )
    exc = _raised(lambda: ta.check_layout("periodic-table"))
    check(
        "a DECLINED layout is refused as TH-LAYOUT and not silently accepted",
        isinstance(exc, ta.ArtDirectionError) and "TH-LAYOUT" in str(exc),
        f"got {exc!r}",
    )
    check(
        "the empty answer is refused too rather than defaulting to something",
        isinstance(_raised(lambda: ta.check_style("")), ta.ArtDirectionError),
    )


def test_check_labels() -> None:
    """The words PAINTED on the cover, checked against the curriculum before a cent is spent.

    This is the concrete answer to "the prompt is still not very course based". Today one
    citation steers the subject and then disappears; after this the words a student READS on
    the card are curriculum text, verified verbatim — and verified at the cheapest point in
    the loop, one text call before any image is bought.
    """
    print("check_labels")
    brief = {
        "modules": ["The membrane", "Action potentials"],
        "concepts": [
            "Resting membrane potential",
            "Ion channels: voltage-gated sodium and potassium channels",
            "Refractory period",
        ],
    }
    check(
        "`none` means no labels, and returns the empty tuple",
        ta.check_labels("none", brief) == (),
    )
    # The reply format literally invites "none — one object, lit", so equality here would
    # reject the compliant answer. Same parse `check_marks` already uses.
    check(
        "`none` plus an explanation is still `none`",
        ta.check_labels("none — one object, lit, nothing written on it", brief) == (),
    )
    check(
        "curriculum labels pass and come back as a tuple",
        ta.check_labels("Ion channels | Refractory period", brief)
        == ("Ion channels", "Refractory period"),
        str(ta.check_labels("Ion channels | Refractory period", brief)),
    )
    # Substring, not equality, for the same measured reason `check_source` uses it: real
    # `key_concepts` are compound strings, so a 2-word label out of one is the honest
    # citation and equality would refuse it.
    check(
        "a phrase copied OUT OF a compound concept is accepted (substring, not equality)",
        ta.check_labels("voltage-gated", brief) == ("voltage-gated",),
    )

    def rejects(label: str, value: str, needle: str, b: dict = brief, layout: str = "") -> None:
        exc = _raised(lambda: ta.check_labels(value, b, layout))
        check(
            label,
            isinstance(exc, ta.ArtDirectionError) and needle in str(exc),
            f"got {exc!r}",
        )

    rejects(
        "a label that is not in the curriculum is refused — no invented text on the cover",
        "Synaptic plasticity",
        "does not appear in this course's curriculum",
    )
    rejects(
        "and the refusal quotes real citations, so the fix is one turn away",
        "Synaptic plasticity",
        "Refractory period",
    )
    rejects(
        "a label made only of common words is refused, whatever the substring test says",
        "the and",
        "made only of common words",
    )
    rejects(
        f"more than MAX_LABELS ({ta.MAX_LABELS}) is refused, and the cap is named",
        " | ".join(["Ion channels"] * (ta.MAX_LABELS + 1)),
        f"over the {ta.MAX_LABELS} cap",
    )
    rejects(
        f"a label over {ta.MAX_LABEL_WORDS} words is a caption, and captions are excluded",
        "Ion channels: voltage-gated sodium and potassium channels",
        f"over the {ta.MAX_LABEL_WORDS} cap",
    )
    rejects("an empty LABELS line is refused rather than read as `none`", "  ", "is empty")
    # The one cross-field check, and it is a contradiction rather than a preference:
    # `single-subject` MEANS one object with nothing written on it.
    rejects(
        "labels declared against `single-subject` are refused as TH-LAYOUT",
        "Ion channels",
        "TH-LAYOUT",
        brief,
        ta.SINGLE_SUBJECT,
    )
    check(
        "while `LABELS: none` with `single-subject` is the ordinary, expected pair",
        ta.check_labels("none", brief, ta.SINGLE_SUBJECT) == (),
    )

    # Fail OPEN, loudly, on a spine with nothing to check against — same path and same
    # reason as `check_source` (rules 21 and 31): this is a read-only audit of our own reply,
    # and a thin spine is a thin input rather than a bad cover.
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        got = ta.check_labels("Anything at all", {"modules": [], "concepts": []})
    check(
        "an empty corpus fails OPEN — the labels are kept",
        got == ("Anything at all",),
        str(got),
    )
    check(
        "and says out loud that the gate did not run",
        "TH-LABELS" in out.getvalue() and "did not run" in out.getvalue(),
        out.getvalue(),
    )


def test_compose_image_prompt_with_style_and_labels() -> None:
    """The labelled path, and the assertion that the UNLABELLED one did not move.

    The second half matters more than the first. All four covers on disk that work took the
    single-subject, unlabelled path, so its prompt has to stay byte-identical — a change
    that improves the labelled cover and quietly reworded the other one would be invisible
    to every other case here, and it is the shape of the change that made these covers worse
    the last time.
    """
    print("compose_image_prompt (style, layout, labels)")
    plain = ta.compose_image_prompt("HOW NEURONS FIRE", _ART, PAIR)
    check(
        "every new argument defaults to today's behaviour, byte for byte",
        ta.compose_image_prompt(
            "HOW NEURONS FIRE", _ART, PAIR, "", ta.SINGLE_SUBJECT, ()
        )
        == plain,
    )
    check(
        "so the unlabelled prompt still bans all added text",
        ta._EXCLUSIONS in plain and ta._MARKS_CLAUSE in plain,
    )
    check(
        "and asks for the subject's own markings crisply, with the blur mandate gone",
        "crisply and legibly" in plain
        and "too small and blurred to read as words" not in plain,
    )

    styled = ta.compose_image_prompt("HOW NEURONS FIRE", _ART, PAIR, "chalkboard")
    check("the chosen style's reference text is injected", "STYLE — chalkboard" in styled)
    check(
        "and it is the FILTERED text, not the file",
        ta.load_style("chalkboard") in styled and not _HEX.search(styled.split("Painted text")[0]),
    )
    check(
        "a style alone does not turn on the labelled clauses",
        ta._EXCLUSIONS in styled and ta._LABELS_CLAUSE.split("{")[0] not in styled,
    )

    labels = ("Ion channels", "Refractory period")
    full = ta.compose_image_prompt(
        "HOW NEURONS FIRE", _ART, PAIR, "editorial-infographic", "structural-breakdown", labels
    )
    check("the chosen layout's reference text is injected", "LAYOUT — structural-breakdown" in full)
    for x in labels:
        check(f"the label {x!r} is asked for by name, quoted", f'"{x}"' in full)
    check(
        "the labels are asked for as LEGIBLE words — the permission this all exists for",
        "large enough to read on a phone" in full and "Spell each one" in full,
    )
    # The permission has to be exactly as wide as the gate that follows it. Both directions,
    # because a permission that widens INTO the gate is the failure this section exists to
    # avoid: a caption or a watermark is still a hard TH-TITLE. What draws that line is no
    # longer a blur instruction (deleted — see `test_marks_permission`) but the ADDED-text
    # exclusion, which is the register `account_transcription` actually judges now.
    check(
        "the labelled prompt still bans every form of ADDED text — the gate's own register",
        ta._EXCLUSIONS_LABELLED in full
        and all(x in full for x in ("no watermark", "no logo", "no signature")),
    )
    check(
        "and the labels are the one exception carved out of figures-over-words",
        "except for the labels named above" in full,
    )
    # The count bound reaches the labelled path too, and it matters MORE there. The one labelled
    # cover a real spine has chosen unforced (`python-oop`, third live run: blueprint,
    # hierarchical-layers, labels Namespace | Scope | Attribute) came back with the headline
    # replaced by `MY-VARIABLE, MBPARNG, GOWRLEE` — the declared labels are the first text to
    # lose legibility in a crowded frame, so this clause says so in as many words.
    check(
        "the count bound applies to the labelled path, where crowding costs the labels first",
        "Keep the rest FEW" in full and "the labels that lose legibility first" in full,
    )
    check(
        "the blanket 'no other words' sentence is gone, so the prompt does not contradict "
        "itself",
        "and no other words" not in full,
    )
    check(
        "but caption, watermark, subtitle and logo are still banned",
        all(w in full for w in ("no subtitle", "no caption", "no watermark", "no logo")),
    )
    check(
        "and the headline is still spelled out letter for letter",
        "Spell it exactly, letter for letter" in full,
    )
    check(
        "the labelled twins are used rather than the originals being edited in place",
        ta._EXCLUSIONS_LABELLED in full and ta._EXCLUSIONS not in full,
    )
    check(
        "the frame clause survives on both paths",
        ta._FRAME_CLAUSE in full and ta._FRAME_CLAUSE in plain,
    )


def test_account_transcription() -> None:
    """The widened TH-TITLE, one case per branch — hard on the headline, soft on the labels.

    The asymmetry is the entire design and it is measured rather than argued: the
    `recursion` cover on disk was hard-failed by the old equality check over its own
    subject's digits, burned all four attempts, and shipped **with no headline at all**. A
    wobbly label is a blemish; a wobbly headline is a dead card.
    """
    print("account_transcription")
    head = "HOW NEURONS FIRE"

    # ---- with no labels, the verdict is the OLD equality check --------------------------
    # This is the regression assertion for the four covers that work: nothing about their
    # path changed, including the gate they passed.
    p, a = ta.account_transcription(head, head)
    check("an exact transcription passes clean", (p, a) == ([], []))
    p, a = ta.account_transcription(head, "how  neurons\nfire")
    check("case and whitespace are transcription noise, not letters", (p, a) == ([], []))
    p, a = ta.account_transcription(head, "HOW NEURONS FIRE MASTERCLASS 2026")
    check(
        "an undeclared word is a HARD TH-TITLE even with the headline correct",
        len(p) == 1 and p[0].startswith("TH-TITLE") and "'MASTERCLASS'" in p[0],
        str(p),
    )
    check("and it is not an advisory", a == [], str(a))
    p, a = ta.account_transcription(head, "HOW NEURNOS FIRE")
    check(
        "a garbled headline is a hard failure, and the finding says what to change",
        len(p) == 1 and "the headline is not in it" in p[0],
        str(p),
    )

    # ---- with labels, the same transcription is accounted for ---------------------------
    labels = ("Ion channels", "Refractory period")
    p, a = ta.account_transcription(head, "ION CHANNELS HOW NEURONS FIRE REFRACTORY PERIOD")
    check(
        "declared labels are what the old gate had no way to allow",
        len(p) == 1,
        str(p),
    )
    p, a = ta.account_transcription(
        head, "ION CHANNELS HOW NEURONS FIRE REFRACTORY PERIOD", labels
    )
    check("with them declared, the labelled cover passes", (p, a) == ([], []), str((p, a)))
    check(
        "the headline is still required as a CONTIGUOUS run, not as scattered words",
        ta.account_transcription(head, "HOW ION CHANNELS NEURONS FIRE", labels)[0] != [],
    )
    # Step 3 — accounted for, but misspelled. This is the branch the whole asymmetry is for.
    p, a = ta.account_transcription(head, "HOW NEURONS FIRE REFRACTROY PERIOD", labels)
    check(
        "a misspelt LABEL is an advisory, not a retry",
        p == [] and len(a) == 1 and a[0].startswith("TH-LABELS"),
        str((p, a)),
    )
    check(
        "and the advisory quotes both spellings and the similarity it measured",
        "'REFRACTROY'" in a[0] and "0." in a[0],
        str(a),
    )
    p, a = ta.account_transcription(head, "HOW NEURONS FIRE MASTERCLASS", labels)
    check(
        "a word that matches NO label is still hard — declaring labels is not a blanket "
        "permission for text",
        len(p) == 1 and "MASTERCLASS" in p[0] and a == [],
        str((p, a)),
    )
    check(
        f"the threshold is stated in one place and is generous by design "
        f"({ta.LABEL_MATCH_RATIO})",
        0.6 <= ta.LABEL_MATCH_RATIO <= 0.85,
        str(ta.LABEL_MATCH_RATIO),
    )

    # ---- the two real transcripts off disk ---------------------------------------------
    # The `recursion` cover is the reason the asymmetry exists, so its own transcripts are
    # the cases: attempt 2's garble must still fail hard (a failing render is not a labelled
    # one), and attempt 3's headline-plus-numerals must still pass unchanged.
    p, _ = ta.account_transcription(
        "RECURSION", "NEN STN NUIT SOT STLE SOC NALY SEAURSION", ("Base case",)
    )
    check(
        "the real garbled render still fails hard, labels or not",
        len(p) == 1 and "the headline is not in it" in p[0],
        str(p),
    )
    p, a = ta.account_transcription("MUSIC THEORY", "MUSIC THEORY 4 3 2 1 6 8", ())
    check(
        "and a headline surrounded by non-lexical figures still passes, unchanged",
        (p, a) == ([], []),
        str((p, a)),
    )


def test_parse_art_direction_galleries() -> None:
    """The three new fields, parsed — and MANDATORY once a brief is in play.

    Absent is a hard failure rather than a silent default, because a silent default is what
    the one hardcoded style WAS: eleven covers of eleven courses in one register, and no
    signal anywhere that a choice had never been made.
    """
    print("parse_art_direction (STYLE / LAYOUT / LABELS)")
    brief = {
        "title": "How Neurons Fire",
        "modules": ["The membrane", "Action potentials"],
        "concepts": ["Ion channels", "Refractory period"],
    }
    art = (
        "An exploded cut-away of a myelinated axon against a deep indigo field, its parts "
        "drawn apart with fine leader lines. The words HOW NEURONS FIRE sit upper-left, and "
        "the parts are labelled Ion channels and Refractory period in small caps."
    )
    # `MARKS:` has to be satisfiable by the art direction above or every case here fails on
    # TH-MARKS instead of on the field it is about — the fixture coupling `_reply` already
    # records for the default reply, one art direction along.
    marks = "the fine leader lines running out to each part"
    reply = _reply(
        art=art,
        marks=marks,
        source="Action potentials",
        style="editorial-infographic",
        layout="structural-breakdown",
        labels="Ion channels | Refractory period",
    )
    d = ta.parse_art_direction(reply, brief)
    check(
        "all three fields parse and normalise",
        (d.style, d.layout, d.labels)
        == ("editorial-infographic", "structural-breakdown", ("Ion channels", "Refractory period")),
        str((d.style, d.layout, d.labels)),
    )

    def rejects(label: str, needle: str, **kw) -> None:
        kw.setdefault("art", art)
        kw.setdefault("marks", marks)
        kw.setdefault("source", "Action potentials")
        kw.setdefault("style", "editorial-infographic")
        kw.setdefault("layout", "structural-breakdown")
        kw.setdefault("labels", "Ion channels | Refractory period")
        exc = _raised(lambda: ta.parse_art_direction(_reply(**kw), brief))
        check(
            label,
            isinstance(exc, ta.ArtDirectionError) and needle in str(exc),
            f"got {exc!r}",
        )

    rejects("a missing STYLE line is refused", "no `STYLE:` line", style=None)
    rejects("a missing LAYOUT line is refused", "no `LAYOUT:` line", layout=None)
    rejects("a missing LABELS line is refused", "no `LABELS:` line", labels=None)
    rejects("an unknown style is refused as TH-STYLE", "TH-STYLE", style="oil painting")
    rejects("a declined layout is refused as TH-LAYOUT", "TH-LAYOUT", layout="jigsaw")
    rejects(
        "a label absent from the curriculum is refused as TH-LABELS",
        "TH-LABELS",
        labels="Synaptic plasticity",
    )
    # The inverse of the headline's own structural check, and it costs the same four
    # attempts: a declared label that is nowhere in the art direction is a word the gate has
    # been told to expect and the picture was never asked to carry.
    rejects(
        "a declared label the PROMPT never asks for is refused before any image is bought",
        "Refractory period",
        art=art.replace("and Refractory period ", ""),
    )
    check(
        "the single-subject, unlabelled reply is still a first-class answer",
        ta.parse_art_direction(
            _reply(source="Action potentials", style="retro", layout=ta.SINGLE_SUBJECT,
                   labels="none"),
            brief,
        ).labels
        == (),
    )


def test_compose_text_free_prompt() -> None:
    """The fallback prompt must not ask for the headline and forbid it in one breath.

    This case exists because the suite found the contradiction rather than because it was
    predicted: the fallback was `art + clause`, and `parse_art_direction` REQUIRES the art
    direction to mention the headline, so the two halves always disagreed. Under the fake
    transport the model kept the words — a text-free path shipping a cover with text.
    """
    print("compose_text_free_prompt")
    prompt, pruned = ta.compose_text_free_prompt("HOW NEURONS FIRE", _ART)
    check("the sentence that asks for the words is pruned", pruned, "nothing was pruned")
    check(
        "and the headline does not survive anywhere in the prompt",
        "HOW NEURONS FIRE" not in prompt.upper(),
        prompt,
    )
    check(
        "while the picture itself survives — this is a prune, not a replacement",
        "neuron in cross-section" in prompt and "rim-lit from behind" in prompt,
        prompt,
    )
    check("the no-text clause is appended", ta._NO_TEXT_CLAUSE in prompt)
    check(
        "the pruning is case-insensitive, because the art may restate the headline in prose",
        "HOW NEURONS FIRE" not in
        ta.compose_text_free_prompt("HOW NEURONS FIRE", _ART.replace("HOW NEURONS FIRE", "how neurons fire"))[0].upper(),
    )

    # The honest-failure direction. A one-sentence art direction that names the headline
    # cannot be pruned at all, and reporting that as a clean text-free render would be the
    # quiet fail-open this file exists to prevent (rule 21).
    single = (
        "A vast dark laboratory bench seen from above with HOW NEURONS FIRE spelled in "
        "glowing filament across the middle of the frame, everything else in shadow."
    )
    prompt, pruned = ta.compose_text_free_prompt("HOW NEURONS FIRE", single)
    check(
        "an unprunable art direction is reported as unpruned rather than silently emptied",
        not pruned and single in prompt,
        f"pruned={pruned}",
    )
    check(
        f"the threshold is the same MIN_ART_CHARS ({ta.MIN_ART_CHARS}) parse_art_direction "
        "uses, so the two cannot disagree",
        len(ta.compose_text_free_prompt("X", "The letter X. " + "A dark bench under a lamp. " * 4)[0])
        > ta.MIN_ART_CHARS,
    )


def test_normalise_text() -> None:
    """Fold transcription noise, preserve every letter — both directions.

    The noise list is measured, not imagined: three of the four bake-off models wrapped the
    headline across lines (`HOW\\nNEURONS\\nFIRE`), so line breaks are the actual noise.
    Preambles and punctuation never appeared once. The quote and dash rows are prophylactic.
    """
    print("normalise_text")
    want = ta.normalise_text("HOW NEURONS FIRE")
    for label, seen in (
        ("line breaks (measured: 3 of 4 models wrapped the headline)", "HOW\nNEURONS\nFIRE"),
        ("runs of spaces", "HOW   NEURONS  FIRE"),
        ("leading and trailing whitespace", "  \n HOW NEURONS FIRE \t "),
        ("case", "How Neurons Fire"),
        ("a non-breaking space", "HOW NEURONS FIRE"),
    ):
        check(f"noise absorbed: {label}", ta.normalise_text(seen) == want, repr(ta.normalise_text(seen)))
    check(
        "a typographic apostrophe matches a typed one",
        ta.normalise_text("LET’S BUILD") == ta.normalise_text("LET'S BUILD"),
    )
    check(
        "an em dash matches a hyphen",
        ta.normalise_text("STATE—MACHINES") == ta.normalise_text("STATE-MACHINES"),
    )

    # LETTERS ARE NOT NOISE. This is the whole discriminating power of the gate, and it was
    # measured before the gate was built: a decoy differing by two letters was rejected by
    # the vision model 4 times out of 4.
    for label, seen in (
        ("a two-letter misspelling", "HOW NEURONS FIRES"),
        ("a one-letter misspelling", "HOW NEURONS FIRF"),
        ("a dropped word", "HOW NEURONS"),
        ("an extra word — an invented caption", "HOW NEURONS FIRE COURSE"),
        ("a watermark appended", "HOW NEURONS FIRE SHUTTERSTOCK"),
    ):
        check(f"NOT absorbed: {label}", ta.normalise_text(seen) != want, repr(ta.normalise_text(seen)))
    check(
        "the sentinel for a text-free image survives normalisation unchanged",
        ta.normalise_text(orr.NO_TEXT) == orr.NO_TEXT,
    )
    check(
        "and an empty transcription is not silently equal to the sentinel",
        ta.normalise_text("") != orr.NO_TEXT,
    )


def test_lexical_text() -> None:
    """The TH-TITLE comparison form: strict about letters, tolerant of letterless marks.

    Written from a measured failure, not from a worry. The `recursion` cover under
    `output/covers-review/artifact/` asked for brass linked-list tags "each stamped with a
    numeral and a pointer-hook arrow" — which is what `MARKS` exists to permit and what makes
    a linked list legible — and `transcribe` came back with the headline plus the tag numbers.
    Equality on `normalise_text` failed, four attempts burned, and because the digits are part
    of the *subject* the text-free fallback could not be text-free either: the cover shipped
    with **no headline at all**, which is worse than every defect this gate was built to catch.

    So the two halves of this file were enforcing opposite contracts — the prompt asks for the
    markings, the gate rejected the cover for having them. This is the seam.
    """
    print("lexical_text — TH-TITLE's comparison form")
    want = ta.lexical_text("RECURSION AND DATA STRUCTURES")

    # The measured transcript, verbatim from artifact/results.json.
    check(
        "the measured failure now passes: painted tag numerals are dropped",
        ta.lexical_text("RECURSION AND DATA STRUCTURES\n12\n7\n19\n20") == want,
        repr(ta.lexical_text("RECURSION AND DATA STRUCTURES\n12\n7\n19\n20")),
    )
    check(
        "and the old comparison really did reject it, so this is a fix and not a no-op",
        ta.normalise_text("RECURSION AND DATA STRUCTURES\n12\n7\n19\n20")
        != ta.normalise_text("RECURSION AND DATA STRUCTURES"),
    )
    for label, seen in (
        ("a stray price on a board", "HOW NEURONS FIRE 4.50"),
        ("dial numerals", "HOW NEURONS FIRE 10 20 30 40"),
        ("a lone punctuation token", "HOW NEURONS FIRE +"),
        ("digits before the headline", "12 HOW NEURONS FIRE"),
    ):
        check(
            f"letterless marks are tolerated: {label}",
            ta.lexical_text(seen) == ta.lexical_text("HOW NEURONS FIRE"),
            repr(ta.lexical_text(seen)),
        )

    # The tolerance must not become a hole. Everything with a letter in it still counts, which
    # is the same "non-lexical only" line the prompt draws — so an artwork carrying readable
    # WORDS is still caught, and that is the defect the transcription gate exists for.
    for label, seen in (
        ("an appended watermark", "HOW NEURONS FIRE SHUTTERSTOCK"),
        ("an invented caption", "HOW NEURONS FIRE A COURSE"),
        ("a misspelling", "HOW NEURONS FIRF"),
        ("a dropped word", "HOW NEURONS"),
        ("a word-shaped label in the artwork", "HOW NEURONS FIRE AXON"),
        ("an alphanumeric token — one letter is enough to keep it", "HOW NEURONS FIRE V2"),
    ):
        check(
            f"still rejected: {label}",
            ta.lexical_text(seen) != ta.lexical_text("HOW NEURONS FIRE"),
            repr(ta.lexical_text(seen)),
        )

    # The cost of the tolerance, pinned so nobody discovers it as a surprise. There is no way
    # to be strict about a digit in the HEADLINE while permitting digits on the subject: the
    # transcript does not say where in the frame a glyph sat.
    check(
        "the cost, stated: a digit in the headline can no longer be enforced",
        ta.lexical_text("PYTHON 3 CLASSES") == ta.lexical_text("PYTHON CLASSES"),
    )
    check(
        "but the spell-back gate still sees digits, so the two gates ask different questions",
        ta.spelled_glyphs("PYTHON 3 CLASSES") != ta.spelled_glyphs("PYTHON CLASSES"),
    )
    check(
        "and it still catches the ligature the whole painted-title design rests on",
        ta.spelled_glyphs("CLASSÆS") != ta.spelled_glyphs("CLASSES"),
    )
    check(
        "the text-free sentinel survives, so the fallback's own check still works",
        ta.lexical_text(orr.NO_TEXT) == ta.lexical_text(orr.NO_TEXT) != "",
    )
    check(
        "a render showing ONLY the subject's numerals counts as text-free",
        ta.lexical_text("20 35 8 24") == "",
        "this is the measured second failure — the fallback could not succeed for a "
        "subject whose markings are digits",
    )


def test_require_png() -> None:
    """Fails CLOSED, and the asymmetry with the transcription gate is the point.

    `media_type` is a property of the MODEL, identical on every attempt, so a retry spends
    four image calls to learn one fact (rule 24). Measured: `bytedance-seed/seedream-4.5`
    answers a request identical to flux's with `image/jpeg`.
    """
    print("_require_png")
    check("a PNG passes", ta._require_png("image/png", "m") is None)
    for media in ("image/jpeg", "image/webp", "", "application/octet-stream"):
        try:
            ta._require_png(media, "bytedance-seed/seedream-4.5")
            check(f"{media or 'an unlabelled type'!r} is refused", False, "no exception")
        except orr.OpenRouterError as exc:
            check(
                f"{media or 'an unlabelled type'} is refused, naming the model and the fix",
                "seedream" in str(exc) and "OPENROUTER_IMAGE_MODEL" in str(exc),
                str(exc),
            )
    check(
        "the refusal says nothing was written, because the .png key would be a lie",
        "nothing was written" in str(
            _raised(lambda: ta._require_png("image/jpeg", "m"))
        ),
    )


def _raised(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — the value under test
        return exc
    return None


# ---------------------------------------------------------------------------
# openrouter — the parses, tested against recorded bodies. No key, no network.
# ---------------------------------------------------------------------------

_TINY_PNG = None  # built in test_png_decoder's helpers; set below


def test_parse_image_response() -> None:
    print("openrouter.parse_image_response")
    png = _make_png([[(11, 79, 216)] * 4 for _ in range(3)], 0)
    b64 = base64.b64encode(png).decode()

    # The recorded shape, verbatim from a real reply: top-level keys are exactly
    # ['created', 'data', 'usage'] and each data item exactly ['b64_json', 'media_type'].
    good = {
        "created": 1748372400,
        "data": [{"b64_json": b64, "media_type": "image/png"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 4175, "cost": 0.045},
    }
    raw, media = orr.parse_image_response(good)
    check("a recorded success parses to the exact bytes", raw == png and media == "image/png")

    check(
        "an unlabelled image is sniffed from the PNG signature rather than guessed",
        orr.parse_image_response({"data": [{"b64_json": b64}]}) == (png, "image/png"),
    )
    check(
        "a JPEG label is reported rather than corrected — the caller decides",
        orr.parse_image_response(
            {"data": [{"b64_json": base64.b64encode(b"\xff\xd8\xff\xe0junk").decode(),
                       "media_type": "image/jpeg"}]}
        )[1] == "image/jpeg",
    )

    def rejects(label: str, payload: dict, needle: str) -> None:
        exc = _raised(lambda: orr.parse_image_response(payload))
        check(
            label,
            isinstance(exc, orr.OpenRouterError) and needle in str(exc),
            f"got {exc!r}",
        )

    # This is the case the function exists for. The docs do not describe the
    # content-policy refusal shape, so anything that is not an image must be a NAMED
    # failure rather than falling through as a success with zero bytes.
    rejects("an empty data list is a named failure", {"created": 1, "data": []}, "carried no image")
    rejects("a missing data key is a named failure", {"created": 1}, "carried no image")
    rejects(
        "a refusal-shaped body reports its own text, so the reason is readable",
        {"data": [], "error": {"message": "flagged by content moderation"}},
        "content moderation",
    )
    rejects("a non-object data[0] is a named failure", {"data": ["not an object"]}, "not an object")
    rejects(
        "a URL-returning variant is named rather than treated as absent",
        {"data": [{"url": "https://example.invalid/x.png", "media_type": "image/png"}]},
        "b64_json",
    )
    rejects("invalid base64 is a named failure", {"data": [{"b64_json": "!!!not base64!!!"}]}, "base64")
    rejects("zero decoded bytes is a named failure", {"data": [{"b64_json": ""}]}, "b64_json")
    # The label and the bytes can disagree, and the one that decides whether a browser
    # renders the cover is the bytes.
    rejects(
        "image/png with non-PNG bytes is refused, not trusted",
        {"data": [{"b64_json": base64.b64encode(b"\xff\xd8\xff\xe0junk").decode(),
                   "media_type": "image/png"}]},
        "PNG signature",
    )


def test_parse_chat_response() -> None:
    print("openrouter.parse_chat_response")
    check(
        "a plain string completion is returned stripped",
        orr.parse_chat_response(
            {"choices": [{"message": {"content": "  HOW NEURONS FIRE \n"}}]}
        ) == "HOW NEURONS FIRE",
    )
    check(
        "content parts are joined, for providers that return them",
        orr.parse_chat_response(
            {"choices": [{"message": {"content": [
                {"type": "text", "text": "HOW "},
                {"type": "thinking", "text": "ignore me"},
                {"type": "text", "text": "NEURONS FIRE"},
            ]}}]}
        ) == "HOW NEURONS FIRE",
    )
    for label, payload, needle in (
        ("no choices", {"choices": []}, "no `choices`"),
        ("a missing choices key", {"id": "x"}, "no `choices`"),
        ("an empty completion", {"choices": [{"message": {"content": "   "}}]}, "no text"),
        ("a null completion", {"choices": [{"message": {"content": None}}]}, "no text"),
    ):
        exc = _raised(lambda p=payload: orr.parse_chat_response(p))
        check(
            f"{label} is a named failure",
            isinstance(exc, orr.OpenRouterError) and needle in str(exc),
            f"got {exc!r}",
        )
    # Truncation is a DIFFERENT defect with a different fix, and the generic message hid it.
    # This is the real payload shape from a cover run: the model spent the whole `max_tokens`
    # budget on a `reasoning` block deciding which curriculum entry to cite, so `content` was
    # null and "the vision model returned no text" was true and useless.
    truncated = {
        "choices": [{
            "finish_reason": "length",
            "native_finish_reason": "max_tokens",
            "message": {"role": "assistant", "content": None,
                        "reasoning": "I need to fix the SOURCE field for TH-GROUND since"},
        }]
    }
    exc = _raised(lambda: orr.parse_chat_response(truncated))
    check(
        "a completion truncated before any text names max_tokens, not 'no text'",
        isinstance(exc, orr.OpenRouterError) and "max_tokens" in str(exc)
        and "finish_reason=length" in str(exc),
        f"got {exc!r}",
    )
    check(
        "and when reasoning was produced it names the off switch, NOT a bigger cap",
        "reasoning" in str(exc) and "'enabled': False" in str(exc)
        and "Raise max_tokens" not in str(exc),
        str(exc),
    )
    # The other branch, and the reason there are two: "raise max_tokens" was the whole message
    # once, and that advice was followed three times (2000 → 4000 → 8000) while the thinking
    # grew to fill each ceiling. With no reasoning block the cap genuinely IS the lever, so the
    # message has to be able to say either thing (rule 24 — a fix must be doable by the thing
    # named). Both directions pinned, because one message covering two defects is how the first
    # one hid.
    no_thought = {
        "choices": [{"finish_reason": "length",
                     "message": {"role": "assistant", "content": None}}]
    }
    exc2 = _raised(lambda: orr.parse_chat_response(no_thought))
    check(
        "a truncation with 0 chars of reasoning names max_tokens instead",
        "Raise max_tokens" in str(exc2) and "'enabled': False" not in str(exc2),
        str(exc2),
    )
    # 2000 → 4000 → 8000, and each step was a real truncation rather than a precaution. 4000
    # was sized against the unlabelled prompt; the styled run of 4 Sep 2026 hit
    # `finish_reason=length` twice in five covers with 3929 and 3486 chars of `reasoning` and
    # no content, each costing one of `MAX_ATTEMPTS = 4`. The reply now carries STYLE, LAYOUT
    # and up to six LABELS with citations, so the turn is simply bigger — a cap sized against
    # one prompt is not sized against a larger one.
    check(
        "the art-direction cap is 8000, above the 4000 the labelled turn exhausted twice",
        inspect.signature(orr.complete_text).parameters["max_tokens"].default == 8000,
        str(inspect.signature(orr.complete_text).parameters["max_tokens"].default),
    )
    # An empty completion is NOT "the image has no text". Conflating them would let a
    # broken vision call silently pass a cover whose headline is misspelled — the exact
    # shape of a gate that fails open where it must fail on its own reading.
    check(
        "an empty completion is an error, never the text-free sentinel",
        orr.NO_TEXT not in str(
            _raised(lambda: orr.parse_chat_response({"choices": [{"message": {"content": ""}}]}))
        ),
    )
    check(
        "the transcription prompt asks for the sentinel it compares against",
        orr.NO_TEXT in orr.TRANSCRIBE_PROMPT,
    )
    check(
        "and it names the ADDED-text register the gate judges, watermark included",
        all(w in orr.TRANSCRIBE_PROMPT for w in ("watermark", "caption", "logo wordmark")),
    )
    # The two-group split, which is where the discrimination between "added on top" and
    # "part of the depicted thing" now lives. It is NOT available to a string rule — that is
    # the whole reason it is asked of the model looking at the pixels. Measured cost of not
    # having it, 4 Sep 2026: incidental markings hard-failed TH-TITLE on 4 of 5 live covers
    # (`'Ø09'`, `'19068G'`, `'GRADO'`) and 2 of those 5 shipped with no headline at all.
    check(
        "the prompt asks for TWO groups, and MARKS is the one that is not judged",
        "TEXT:" in orr.TRANSCRIBE_PROMPT and "MARKS:" in orr.TRANSCRIBE_PROMPT,
    )
    for example in ("stamped", "etched", "Dial figures", "part numbers"):
        check(
            f"MARKS is described concretely enough to sort by — {example!r}",
            example in orr.TRANSCRIBE_PROMPT,
        )
    check(
        "and it still forbids correcting spelling, in BOTH groups",
        "do not correct spelling" in orr.TRANSCRIBE_PROMPT,
    )
    for label, reply, want in (
        ("a well-formed two-line reply",
         "TEXT: HOW NEURONS FIRE\nMARKS: 12 mV 3.4", ("HOW NEURONS FIRE", "12 mV 3.4")),
        ("a text-free cover with markings",
         f"TEXT: {orr.NO_TEXT}\nMARKS: 501S B2", ("", "501S B2")),
        ("a headline and a bare object",
         "TEXT: RECURSION\nMARKS: NONE", ("RECURSION", "")),
        ("lower-case keys and padding",
         "  text :  RECURSION \n  marks : none ", ("RECURSION", "")),
        ("a reply that omits MARKS entirely", "TEXT: RECURSION", ("RECURSION", "")),
        ("a reply that omits TEXT entirely", "MARKS: 09 11 38", ("", "09 11 38")),
        ("both sentinels", f"TEXT: {orr.NO_TEXT}\nMARKS: {orr.NO_MARKS_SEEN}", ("", "")),
    ):
        check(
            f"parse_transcription handles {label}",
            orr.parse_transcription(reply) == want,
            f"{reply!r} -> {orr.parse_transcription(reply)!r}, wanted {want!r}",
        )
    # Fail-CLOSED, and the direction is the decision. An unrecognised reply is treated as all
    # ADDED text, which is exactly the strict pre-split behaviour: a garbled transcription then
    # fails TH-TITLE and costs an attempt. Reading it as "no text" would pass a cover whose
    # headline was never checked — the shape of a gate failing open on its own reading.
    check(
        "an unformatted reply degrades to the strict pre-split behaviour, not to a pass",
        orr.parse_transcription("The image says RECURSION.") == ("The image says RECURSION.", ""),
        repr(orr.parse_transcription("The image says RECURSION.")),
    )
    # Asserted against the SOURCE, because `transcribe` passes the budget positionally into
    # `ask_about_image` rather than taking it as a parameter — a signature probe here would
    # raise `KeyError` and read as the test being broken rather than the cap being wrong.
    check(
        "the read-back budget was raised with the split — two lines, not one",
        "max_tokens=500" in inspect.getsource(orr.transcribe),
        inspect.getsource(orr.transcribe),
    )


def test_art_direction_turn_disables_thinking() -> None:
    """The art-direction turn sends `reasoning: {"enabled": false}`, and the vision calls none.

    Three caps were tried before this — 2000, 4000, 8000 — and at each one the turn came back
    `content: null` with `finish_reason=length`: 3929 and 3486 chars of `reasoning` at 4000,
    **7897 at 8000** (`python-oop`, 4 Sep 2026), each costing one of `MAX_ATTEMPTS = 4`.
    Thinking grew to fill whatever ceiling it was given.

    A `reasoning: {"max_tokens": N}` partition was tried next, and **it is silently ignored by
    OpenRouter for this model** — one probe, same prompt, `anthropic/claude-sonnet-5`: asking
    for 2000 billed **6233** reasoning tokens, while `{"enabled": false}` billed **0** and
    returned 1432 completion tokens of content. So the off switch is what works and the bound is
    not, which is why this test's predecessor — asserting `{"max_tokens": ART_REASONING_TOKENS}`
    and that the number sat above Anthropic's 1024 minimum — pinned a contract the API does not
    honour. It was written from an argument; this one is written from the measurement (rule 25).

    The second half is unchanged and is a real trap rather than a formality: the vision calls run
    on 500 and 600 tokens, both **below the 1024 minimum thinking budget**, so a `reasoning`
    block leaking onto them could make a working gate return 400. Asserted on the wire body,
    because that is the only place the difference exists.
    """
    print("art-direction thinking (off by measurement, and not sent to the vision calls)")
    bodies: list[dict] = []

    async def fake_post(path, body, timeout):
        bodies.append(body)
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"cost": 0.001, "prompt_tokens": 10, "completion_tokens": 2},
        }

    saved = orr._post
    orr._post = fake_post
    try:
        asyncio.run(orr.complete_text("write me an art direction"))
        asyncio.run(orr.transcribe(b"\x89PNG"))
        asyncio.run(orr.spell_back(b"\x89PNG"))
    finally:
        orr._post = saved

    art, trans, spell = bodies
    check(
        "thinking is OFF by default — the only setting measured to be honoured",
        art.get("reasoning") == {"enabled": False},
        repr(art.get("reasoning")),
    )
    check(
        "and OPENROUTER_ART_THINKING defaults off, so the default path is the measured one",
        orr.ART_THINKING is False,
        str(orr.ART_THINKING),
    )
    # The escape hatch is asserted on the source rather than by re-running with the env var set:
    # `ART_THINKING` is read at import time, so flipping it in-process would require reloading
    # the module and would re-bind the `_post` this test just patched.
    check(
        "with it on, the parameter is omitted entirely rather than set to enabled=true",
        "None if ART_THINKING else" in inspect.getsource(orr.complete_text),
        inspect.getsource(orr.complete_text)[-400:],
    )
    for label, body in (("transcribe", trans), ("spell_back", spell)):
        check(
            f"{label} sends NO reasoning block — its budget is under the 1024 minimum",
            "reasoning" not in body and body["max_tokens"] < 1024,
            f"reasoning={body.get('reasoning')!r} max_tokens={body['max_tokens']}",
        )


def test_book_records_cost_and_tokens() -> None:
    """`usage.cost` is returned inline and must be BOOKED, not printed.

    This is the one thing OpenRouter gives that Bedrock does not (rule 28: a direct call
    that prices nothing books $0.00), so the risk is the opposite one — a real number
    arriving and being dropped. Rule 27's corollary: grep for whether an accumulator is
    ever read. It is, by `generate_thumbnail`'s report.
    """
    print("openrouter._book")
    ta.usage.reset()
    cost = orr._book(
        {"usage": {"prompt_tokens": 12, "completion_tokens": 7291, "cost": 0.045}}
    )
    snap = ta.usage.snapshot()
    check("the returned cost is the per-call figure", abs(cost - 0.045) < 1e-9, str(cost))
    check(
        "cost, both token counts and the call all reach the accumulator",
        abs(snap["total_cost"] - 0.045) < 1e-9
        and snap["input_tokens"] == 12
        and snap["output_tokens"] == 7291
        and snap["api_calls"] == 1,
        str(snap),
    )
    # A response with no usage block must book the call without inventing a price.
    orr._book({"data": []})
    snap = ta.usage.snapshot()
    check(
        "a usage-less response books a call and no phantom cost",
        abs(snap["total_cost"] - 0.045) < 1e-9 and snap["api_calls"] == 2,
        str(snap),
    )
    ta.usage.reset()


def test_missing_key_is_named() -> None:
    """The failure most likely to actually happen, and the reason it names three files.

    The cover phase is advisory, so a key missing on ONE launch path degrades to "no
    cover" with nothing loud anywhere else. `workers/phases/thumbnail.test.py` asserts the
    phase surfaces this string; this asserts the string says where to look.
    """
    print("openrouter._key")
    old = os.environ.get("OPENROUTER_API_KEY")
    try:
        for value in ("", "   "):
            os.environ["OPENROUTER_API_KEY"] = value
            exc = _raised(orr._key)
            check(
                f"an {'empty' if not value else 'all-whitespace'} key raises rather than "
                "sending a Bearer header with nothing after it",
                isinstance(exc, orr.OpenRouterError),
                repr(exc),
            )
            check(
                "and the message names the three env-construction sites to check",
                "routes/courses.py" in str(exc) and "_build_container_env" in str(exc),
                str(exc),
            )
        os.environ["OPENROUTER_API_KEY"] = "  sk-or-test  "
        check("a key is returned stripped", orr._key() == "sk-or-test")
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
        if old is not None:
            os.environ["OPENROUTER_API_KEY"] = old


def test_resolve_text_model() -> None:
    """The `MODEL` trap, as cases — the one defect in this file's history that shipped.

    `workers/phases/thumbnail.py` reads `MODEL` from the worker's environment and forwards
    it, and `curriculum.py` forwards it at four more sites. In a worker `MODEL` is
    `global.anthropic.claude-sonnet-5` — a **Bedrock** name, which OpenRouter answers with
    HTTP 400 "model not found". Every cover, on every launch path.

    Asserted three ways because the interesting property is not the return value alone: the
    substitution must be *audible*, or an operator who really did set
    `OPENROUTER_TEXT_MODEL` to something and is being ignored has nothing to read.
    """
    print("resolve_text_model (the MODEL trap)")

    # `None` is included because `thumbnail.py` forwards `os.getenv("MODEL", "")` but a
    # caller in a test or a REPL can pass nothing at all, and `"".strip()` and `None` must
    # not take different branches.
    for arg, label in (("", "empty"), (None, "None"), ("   ", "whitespace")):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = ta.resolve_text_model(arg)
        check(
            f"an {label} model falls back to the default, silently",
            got == orr.DEFAULT_TEXT_MODEL and buf.getvalue() == "",
            f"{got!r} / printed {buf.getvalue()!r}",
        )

    # The real production value, not an invented one.
    for bedrock in ("global.anthropic.claude-sonnet-5",
                    "anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "us.anthropic.claude-opus-5"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = ta.resolve_text_model(bedrock)
        check(
            f"{bedrock!r} is not sent to OpenRouter",
            got == orr.DEFAULT_TEXT_MODEL,
            got,
        )
        out = buf.getvalue()
        check(
            "and the substitution is printed, naming both the ignored value and the knob",
            bedrock in out and "OPENROUTER_TEXT_MODEL" in out and orr.DEFAULT_TEXT_MODEL in out,
            repr(out),
        )

    for ok in ("anthropic/claude-sonnet-5", "openai/gpt-5.1", "  google/gemini-3-pro  "):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = ta.resolve_text_model(ok)
        check(
            f"a vendor/model name is passed through: {ok!r}",
            got == ok.strip() and buf.getvalue() == "",
            f"{got!r} / printed {buf.getvalue()!r}",
        )

    # The reason this function exists rather than a validation error: the default itself must
    # survive it. A name that is already correct going in must come out unchanged, or the
    # translation would be the thing that breaks the configured case.
    check(
        "the default is a fixed point",
        ta.resolve_text_model(orr.DEFAULT_TEXT_MODEL) == orr.DEFAULT_TEXT_MODEL,
    )
    check(
        "and it is OpenRouter-shaped, so nothing in this path holds a Bedrock name",
        "/" in orr.DEFAULT_TEXT_MODEL and ta.DEFAULT_MODEL == orr.DEFAULT_TEXT_MODEL,
        f"{orr.DEFAULT_TEXT_MODEL!r} / {ta.DEFAULT_MODEL!r}",
    )


def test_no_anthropic_import() -> None:
    """The defect that made the cover phase unloadable in production, pinned.

    `workers/Dockerfile` launches the worker as
    `uv run --directory /app/ontology-engine python /app/workers/entrypoint.py`, and
    `phases/thumbnail.py` imports this module **in-process**. That venv has `httpx` and not
    `anthropic`, so `from svg_agent import _llm_call_async` failed with
    `No module named 'anthropic'` and the phase reported `##PHASE:thumbnail:failed##` on
    every course, whatever the key — fail-open, so nothing else complained.

    A source-level assertion rather than an import probe, deliberately: the laptop that runs
    this suite *has* `anthropic` installed, so importing successfully here proves nothing
    about the venv where it matters. What can be checked anywhere is that the module names
    neither package.
    """
    print("no anthropic/svg_agent import (the production interpreter)")
    src = (HERE / "thumbnail_agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src, filename="thumbnail_agent.py")
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    for banned in ("anthropic", "svg_agent", "boto3", "botocore"):
        check(
            f"thumbnail_agent does not import {banned}",
            banned not in imported,
            f"imports: {sorted(imported)} — that package is absent from the venv the worker "
            "process actually runs under, and this module is imported in-process",
        )
    check(
        "and openrouter.py is likewise httpx-only",
        "anthropic" not in {
            (a.name.split(".")[0] if isinstance(n, ast.Import) else "")
            for n in ast.walk(ast.parse((HERE / "openrouter.py").read_text(encoding="utf-8")))
            if isinstance(n, ast.Import)
            for a in n.names
        },
    )


# ---------------------------------------------------------------------------
# The PNG decoder. Fixtures are BUILT here, one per filter type, so the
# unfilter is exercised with no browser, no Pillow and no checked-in binary.
# ---------------------------------------------------------------------------


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def _make_png(pixels: list[list[tuple[int, int, int]]], filter_type: int) -> bytes:
    """Encode RGB pixels with one PNG filter applied to every row."""
    height, width = len(pixels), len(pixels[0])
    raw = bytearray()
    prev = [0] * (width * 3)
    for row in pixels:
        flat = [c for px in row for c in px]
        line = bytearray()
        for i, x in enumerate(flat):
            a = flat[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            if filter_type == 0:
                line.append(x & 0xFF)
            elif filter_type == 1:
                line.append((x - a) & 0xFF)
            elif filter_type == 2:
                line.append((x - b) & 0xFF)
            elif filter_type == 3:
                line.append((x - (a + b) // 2) & 0xFF)
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line.append((x - pred) & 0xFF)
        raw += bytes([filter_type]) + line
        prev = flat
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )


def _make_palette_png(width: int, height: int, palette: list[tuple[int, int, int]]) -> bytes:
    """A VALID colour-type-3 PNG — an encoding the decoder declines by design.

    Not a truncated or corrupt file: `png_scanlines` reads IDAT before IEND, so chopping
    the tail off a good PNG still decodes (measured — that fixture passed). A palette PNG
    is the real shape of "an encoding this cannot read", and it must be declined rather
    than misread as RGB. More reachable since the pivot, not less: the bytes now come from
    a third party rather than from Chrome.
    """
    raw = bytearray()
    for y in range(height):
        raw += bytes([0]) + bytes((x + y) % len(palette) for x in range(width))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
        + _chunk(b"PLTE", bytes(c for px in palette for c in px))
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )


def test_png_decoder() -> None:
    print("png_scanlines / png_probe")
    # A gradient, so a wrong predictor cannot accidentally reproduce it.
    varied = [[((x * 7 + y * 3) % 256, (x * 13) % 256, (y * 5) % 256) for x in range(9)] for y in range(6)]
    flat = [[(238, 242, 246)] * 9 for _ in range(6)]
    with tempfile.TemporaryDirectory() as tmp:
        for ft in range(5):
            p = Path(tmp) / f"f{ft}.png"
            p.write_bytes(_make_png(varied, ft))
            w, h, ch, rows = ta.png_scanlines(p)
            decoded = [
                [tuple(line[i : i + ch]) for i in range(0, len(line), ch)] for line in (rows or [])
            ]
            check(
                f"filter type {ft} unfilters to the exact pixels",
                (w, h, ch) == (9, 6, 3) and decoded == varied,
                f"got {w}x{h} ch={ch}, first row {decoded[0] if decoded else None}",
            )

        p = Path(tmp) / "flat.png"
        p.write_bytes(_make_png(flat, 4))
        check("a uniform PNG is reported as uniform", ta.png_probe(p) == (9, 6, False), str(ta.png_probe(p)))

        p = Path(tmp) / "varied.png"
        p.write_bytes(_make_png(varied, 4))
        check("a PNG with content is reported as varied", ta.png_probe(p) == (9, 6, True))

        # Uniform except for ONE pixel in the last row: the case a first-row-only check
        # would pass, which is the whole point of scanning every row.
        nearly = [[(238, 242, 246)] * 9 for _ in range(6)]
        nearly[5][8] = (0, 0, 0)
        p = Path(tmp) / "nearly.png"
        p.write_bytes(_make_png(nearly, 0))
        check("one differing pixel in the last row still counts as content", ta.png_probe(p)[2] is True)

        p = Path(tmp) / "not.png"
        p.write_bytes(b"this is not a png")
        exc = _raised(lambda: ta.png_probe(p))
        check("a non-PNG raises rather than returning a verdict", isinstance(exc, RuntimeError), repr(exc))


# ---------------------------------------------------------------------------
# _measure_png / _check_png — the pixel gates, on built fixtures so the floors
# are pinned by cases rather than by a shell command someone ran once.
# ---------------------------------------------------------------------------

FIX_W, FIX_H = 128, 72


def _rgb(h: str) -> tuple[int, int, int]:
    h = ta._norm_hex(h).lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _cover(ground: str, blocks: list[tuple[str, int, int, int, int]]) -> bytes:
    """A fixture cover: a flat ground plus `(hex, x, y, w, h)` blocks. Filter type 0.

    128x72 is 16:9 and deliberately far under the `TH-SIZE` floor, so it is the wrong tool
    for the dimension gates and the right one for everything else. `_big_cover` below is
    the one that clears the floor.
    """
    px = [[_rgb(ground)] * FIX_W for _ in range(FIX_H)]
    for colour, x, y, w, h in blocks:
        rgb = _rgb(colour)
        for yy in range(y, min(y + h, FIX_H)):
            for xx in range(x, min(x + w, FIX_W)):
                px[yy][xx] = rgb
    return _make_png(px, 0)


def _vary(n: int) -> bytes:
    """The n-th distinguishable cover. Same shape, different dimensions, so a test can say
    WHICH render's bytes are on disk instead of trusting the log line above them."""
    return _big_cover(width=1280 + 16 * (n - 1), height=720 + 9 * (n - 1))


def _big_cover(
    ground: str = G,
    accent: str = A,
    width: int = 1280,
    height: int = 720,
    accent_frac: float = 0.5,
) -> bytes:
    """A cover that clears every hard gate: 16:9, over the floor, saturated, not flat.

    Built row-wise straight to bytes rather than through `_cover`'s pixel lists, which
    would allocate ~920k tuples for one fixture. Used by the `generate_thumbnail` cases,
    where the point is the loop's control flow and the PNG only has to be acceptable.

    `accent_frac` is the accent block's side as a fraction of each axis, so it covers
    `accent_frac ** 2` of the canvas — 0.5 gives the original 25%. It exists because a
    fixture's **proportions** are part of the population it claims to stand for, not just its
    colours: the near-white fixture below was written as "the shape of the rejected covers"
    with a 25% dark block and measured 0.114 mean saturation, while the six real covers
    measure 0.030-0.059, because real dark type covers a few percent of a page rather than a
    quarter of it. That gap was invisible while the floor was 0.35 (both numbers are under it)
    and became a failure the moment the floor moved into the space between them — a fixture
    passing for the wrong reason, which is the shape rule 18 keeps finding.
    """
    g, a = bytes(_rgb(ground)), bytes(_rgb(accent))
    aw = max(1, int(width * accent_frac))
    ah = max(1, int(height * accent_frac))
    x0, y0 = (width - aw) // 2, (height - ah) // 2
    plain = g * width
    band = g * x0 + a * aw + g * (width - x0 - aw)
    raw = b"".join(
        b"\x00" + (band if y0 <= y < y0 + ah else plain)
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def test_saturation_floor_is_sited_in_the_measured_gap() -> None:
    """The 0.35 -> 0.10 re-siting, pinned so it cannot drift back unmeasured.

    0.35 was calibrated before the style gallery existed, on covers with light or mid
    grounds. `chalkboard` and `dark-atmospheric` put a large neutral dark area on the canvas,
    the statistic is a mean over the canvas, and two good chalkboard covers measured 0.13 and
    0.22 — rejected, and the retry made the model try to leave the style. Re-measured over 57
    covers (`covers-review/sat_probe.py`): pale 0.03-0.06, painted 0.13-0.84, SVG-era 0.78-0.92.

    So both bounds are asserted, not just the value. A floor above PAINTED_FLOOR rejects good
    covers; a floor below PALE_CEILING re-admits the founding complaint. Anyone moving this
    number has to move a measurement with it.
    """
    print("TH-SATURATION (the re-sited floor)")
    PALE_CEILING, PAINTED_FLOOR = 0.06, 0.13

    check(
        f"the floor clears the pale population it must reject ({PALE_CEILING} < "
        f"{ta.MIN_MEAN_SATURATION})",
        ta.MIN_MEAN_SATURATION > PALE_CEILING,
    )
    check(
        f"the floor sits under the painted population it must not reject "
        f"({ta.MIN_MEAN_SATURATION} <= {PAINTED_FLOOR})",
        ta.MIN_MEAN_SATURATION <= PAINTED_FLOOR,
    )
    check(
        "the advisory band is non-empty and above the hard floor",
        ta.MIN_MEAN_SATURATION < ta.ADVISORY_SATURATION,
    )
    check(
        "the old floor is kept as the band's top rather than deleted (rule 26)",
        ta.ADVISORY_SATURATION == 0.35,
        f"ADVISORY_SATURATION={ta.ADVISORY_SATURATION}",
    )

    with tempfile.TemporaryDirectory() as tmp:
        # A dark neutral ground with a warm subject: the chalkboard shape. Chosen to land
        # near 0.20 — the MIDDLE of the band and the range the two real chalkboard covers
        # measured (0.13 and 0.22) — rather than wherever the default accent happens to put
        # it. The first attempt at this fixture measured 0.33, passing for the right reason
        # but one accent tweak away from drifting out of the band it is meant to demonstrate.
        dark = Path(tmp) / "dark.png"
        dark.write_bytes(_big_cover("#35363a", "#b07a4d"))
        m = ta._measure_png(dark)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            problems = ta._check_png(dark)
        printed = buf.getvalue()

        check(
            f"a dark-ground cover measures inside the band ({m['mean_saturation']:.2f})",
            ta.MIN_MEAN_SATURATION <= m["mean_saturation"] < ta.ADVISORY_SATURATION,
            f"{m['mean_saturation']:.3f} is outside "
            f"[{ta.MIN_MEAN_SATURATION}, {ta.ADVISORY_SATURATION}) — pick another fixture",
        )
        check(
            "and it is NOT a hard failure — this is the case the old floor got wrong",
            not any(p.startswith("TH-SATURATION") for p in problems),
            "; ".join(problems),
        )
        check(
            "but the band still prints, so re-siting did not discard the signal",
            "TH-SATURATION" in printed and "advisory band" in printed,
            printed,
        )
        check(
            "the advisory names the styles it is expected on, so it is not read as a defect",
            "chalkboard" in printed,
            printed,
        )

        # Above the band: no saturation line at all, hard or advisory.
        vivid = Path(tmp) / "vivid.png"
        vivid.write_bytes(_big_cover())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ta._check_png(vivid)
        check(
            "a saturated cover gets no saturation line at all",
            "TH-SATURATION" not in buf.getvalue(),
            buf.getvalue(),
        )


def test_saturation_floor_against_the_real_rejected_corpus() -> None:
    """The pale population as FILES, not as a synthetic fixture.

    `test_check_png_separates_the_two_populations` builds a near-white cover and asserts it
    fails. That pins the shape; it does not pin that the shape matches what was actually
    rejected. These are the six covers the floor was written for, so the claim "0.03-0.06,
    and they still fail at 0.10" is checked against them or it is checked against nothing.

    Skips LOUDLY when the corpus is absent (rule 21) — it is generated output and does not
    ship in the worker image, exactly like the SVG corpus's `CORPUS_SKIPPED` banner.
    """
    print("TH-SATURATION vs the real rejected covers")
    corpus = ta.Path(__file__).resolve().parent.parent / "output/thumbnails/rejected-original"
    pngs = sorted(corpus.glob("*.png")) if corpus.is_dir() else []
    if not pngs:
        skipped(
            "  REJECTED_CORPUS_ABSENT — no PNGs under output/thumbnails/rejected-original/, so "
            "the pale population is pinned only by the synthetic fixture. This is generated "
            "output and is not in the image; the local run is its only gate"
        )
        return

    measured = []
    for png in pngs:
        m = ta._measure_png(png)
        if m and m.get("mean_saturation") is not None:
            measured.append((m["mean_saturation"], png.name))
    check(f"all {len(pngs)} rejected covers decode", len(measured) == len(pngs),
          f"{len(measured)}/{len(pngs)}")
    if not measured:
        return

    worst = max(measured)
    check(
        f"the whole population still fails the re-sited floor (ceiling {worst[0]:.3f} < "
        f"{ta.MIN_MEAN_SATURATION}, on {worst[1]})",
        worst[0] < ta.MIN_MEAN_SATURATION,
        f"{worst[1]} measures {worst[0]:.3f}",
    )
    for sat, name in measured:
        check(
            f"{name} is a hard TH-SATURATION failure ({sat:.3f})",
            any(p.startswith("TH-SATURATION") for p in ta._check_png(corpus / name)),
        )


def test_accent_and_saturation_are_complementary_not_redundant() -> None:
    """The reason TWO pixel statistics exist, pinned on the population that splits them.

    `MIN_MEAN_SATURATION`'s comment claims it "cannot see the failure that prompted
    `MIN_ACCENT_SHARE`", and after the saturation floor was re-sited that claim carries the
    whole justification for keeping both — a reader looking at 0.10 and 2% has no other way
    to know they are not two spellings of "is it colourful". Measured on the six real
    rejected covers: they score HIGH on saturation-per-lit-pixel terms and LOW on accent,
    which is what "complementary" means concretely.

    This is the assertion that stops someone deleting one of them as a duplicate. It uses
    the real corpus for the reason the test above does, and skips the same way (rule 21).
    """
    print("TH-ACCENT vs TH-SATURATION: complementary, not redundant")
    corpus = ta.Path(__file__).resolve().parent.parent / "output/thumbnails/rejected-original"
    pngs = sorted(corpus.glob("*.png")) if corpus.is_dir() else []
    if not pngs:
        skipped(
            "  REJECTED_CORPUS_ABSENT — the complementarity claim in MIN_ACCENT_SHARE's "
            "comment is unpinned without these files. Generated output, not in the image; "
            "the local run is its only gate"
        )
        return

    with tempfile.TemporaryDirectory() as tmp:
        # A vivid cover with no bright-saturated pool: high saturation, low accent. Both
        # colours are deeply saturated navy/blue and both sit well under ACCENT_MIN_LUM, so
        # this is the SVG-era shape measured at 0.0-1.4% accent against 0.85-0.92 saturation
        # — the cell that proves one statistic cannot stand in for the other.
        dark_vivid = Path(tmp) / "dark_vivid.png"
        dark_vivid.write_bytes(_big_cover("#101a2e", "#12386e", accent_frac=0.9))
        m = ta._measure_png(dark_vivid)
        check("a vivid-but-unlit cover is measurable", bool(m) and m.get("readable"))
        if m:
            check(
                f"it clears the saturation floor ({m['mean_saturation']:.2f} >= "
                f"{ta.MIN_MEAN_SATURATION})",
                m["mean_saturation"] >= ta.MIN_MEAN_SATURATION,
                f"{m['mean_saturation']:.3f}",
            )
            check(
                f"and STILL fails the accent floor ({m['accent_share'] * 100:.1f}% < "
                f"{ta.MIN_ACCENT_SHARE * 100:.0f}%) — so accent catches what saturation "
                "waves through",
                m["accent_share"] < ta.MIN_ACCENT_SHARE,
                f"{m['accent_share'] * 100:.2f}%",
            )
            check(
                "the two thresholds read different measured keys, so neither is a rename "
                "of the other",
                ta.MIN_MEAN_SATURATION != ta.MIN_ACCENT_SHARE
                and {"mean_saturation", "accent_share"} <= set(m),
            )
        # Advisory, not a problem — the asymmetry that is the whole reason this floor was
        # left where it is while the saturation one moved.
        check(
            "a low-accent cover is NOT a hard failure",
            not any(p.startswith("TH-ACCENT") for p in ta._check_png(dark_vivid)),
        )

    # And the converse, so this is a claim about both directions rather than one cell: the
    # pale rejected corpus fails saturation, which is the failure accent was NOT written for.
    fails_sat = [
        p.name
        for p in pngs
        if any(x.startswith("TH-SATURATION") for x in ta._check_png(p))
    ]
    check(
        f"the pale corpus is caught by saturation, not accent ({len(fails_sat)}/{len(pngs)})",
        len(fails_sat) == len(pngs),
        f"missed: {sorted(set(p.name for p in pngs) - set(fails_sat))}",
    )


def test_check_png_separates_the_two_populations() -> None:
    """The calibration, as cases. See the module docstring."""
    print("_check_png (the calibration)")
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.png"
        good.write_bytes(_big_cover())
        m = ta._measure_png(good)
        problems = ta._check_png(good)
        check("a saturated 16:9 cover over the floor passes every hard gate", not problems,
              "; ".join(problems))
        check(
            f"its saturation clears the floor with room ({m['mean_saturation']:.2f} "
            f">= {ta.MIN_MEAN_SATURATION})",
            m["mean_saturation"] >= ta.MIN_MEAN_SATURATION,
        )

        # Known-bad: the shape of all 22 rejected SVG covers — a near-white ground with
        # legible dark type. Measured on the real files: saturation 0.030-0.059, which is what
        # `accent_frac` is for. At the default 0.5 this fixture is a quarter dark and measures
        # 0.114 — 2x the real ceiling, and a fixture 2x off the population it names is not a
        # regression test for that population. `test_saturation_floor_against_the_real_
        # rejected_corpus` checks the same claim against the actual files.
        bad = Path(tmp) / "bad.png"
        bad.write_bytes(_big_cover("#eef2f6", "#12161c", accent_frac=0.2))
        problems = ta._check_png(bad)
        check(
            "the rejected covers' shape fails TH-SATURATION",
            any(p.startswith("TH-SATURATION") for p in problems),
            str(problems),
        )
        check(
            "the finding names the fix and the words to use, not just the number",
            any("saturated, vivid, high-chroma" in p for p in problems),
            str(problems),
        )
        check(
            "and it is phrased as something a correction turn can act on (rule 24)",
            all("Chrome" not in p and "font-size" not in p for p in problems),
            str(problems),
        )


def test_check_png_dimension_gates() -> None:
    """`TH-ASPECT` and `TH-SIZE` — a ratio and a floor, never an equality.

    No model on this endpoint accepts a pixel size, so the exact figure is the model's own
    grid: 1536x864, 1824x1024, 2560x1440 and 2752x1536 came back for one identical
    request. An equality assertion would fail on every model change, which is why the SVG
    era's exact `1920x1080` could not survive the pivot.
    """
    print("_check_png (TH-ASPECT / TH-SIZE)")
    with tempfile.TemporaryDirectory() as tmp:
        def problems_for(w: int, h: int) -> list[str]:
            p = Path(tmp) / f"c{w}x{h}.png"
            p.write_bytes(_big_cover(width=w, height=h))
            return ta._check_png(p)

        check("exactly 16:9 over the floor is clean", not problems_for(1280, 720))
        # The two real models that are NOT exactly 16:9. Both must pass: a cover is not
        # less usable for being 0.8% wide, and failing them would reject two of the four
        # models that spell correctly.
        for w, h, name in ((1824, 1024, "flux.2-pro"), (2752, 1536, "gemini-3-pro-image")):
            check(
                f"{w}x{h} ({name}, {w / h:.4f}) is inside the ±{ta.ASPECT_TOLERANCE:.0%} tolerance",
                not any(p.startswith("TH-ASPECT") for p in problems_for(w, h)),
                str(problems_for(w, h)),
            )
        square = problems_for(1280, 1280)
        check(
            "a square cover is flagged TH-ASPECT",
            any(p.startswith("TH-ASPECT") for p in square),
            str(square),
        )
        check(
            "and the finding says it is NOT fixable in the art direction (rule 24)",
            any("not fixable in the art direction" in p and "OPENROUTER_IMAGE_MODEL" in p
                for p in square),
            str(square),
        )
        small = problems_for(640, 360)
        check(
            f"under the og:image floor of {ta.MIN_PNG_WIDTH}x{ta.MIN_PNG_HEIGHT} is flagged TH-SIZE",
            any(p.startswith("TH-SIZE") for p in small),
            str(small),
        )
        check(
            "TH-SIZE names the tier and the model, the two things that can change it",
            any("resolution" in p and "OPENROUTER_IMAGE_MODEL" in p
                for p in small if p.startswith("TH-SIZE")),
            str(small),
        )
        check(
            "a 640x360 cover is 16:9, so TH-SIZE fires ALONE — the two gates are independent",
            not any(p.startswith("TH-ASPECT") for p in small),
            str(small),
        )


def test_check_png_advisories_are_not_returned() -> None:
    """The demotions, asserted as behaviour rather than trusted to a comment.

    `TH-CONTRAST`, `TH-BYTES` and the hue count were hard gates in the SVG era and were
    measured at the pivot to have NEVER FIRED on 37 real covers — while firing on the
    painted covers that work: 3 of 4 exceed 2 MB and 3 of 4 carry more than 3 hue
    families. Keeping them would have made the new medium unshippable on evidence the old
    medium never generated (rule 25's trap, from the inside). So they must be measured,
    printed, and NOT returned — a returned finding costs an image call.
    """
    print("_check_png (the demoted advisories)")
    with tempfile.TemporaryDirectory() as tmp:
        # Two blues of similar luminance: saturated, but nothing legible standing off it.
        low = Path(tmp) / "low.png"
        low.write_bytes(_big_cover(G, "#3C78E6"))
        m = ta._measure_png(low)
        check(
            f"a cover with nothing standing off its ground measures low contrast "
            f"({m['contrast_ratio']:.2f}:1)",
            m["contrast_ratio"] < ta.MIN_CONTRAST_RATIO,
            str(m["contrast_ratio"]),
        )
        check(
            "and TH-CONTRAST is NOT returned as a retryable problem",
            not any(p.startswith("TH-CONTRAST") for p in ta._check_png(low)),
            str(ta._check_png(low)),
        )

        # Five hue families, each a fifth of the canvas — the shape 3 of 4 painted covers
        # have, and the reason the cap is gone rather than raised.
        many = Path(tmp) / "many.png"
        many.write_bytes(
            _cover(
                "#E01B24",
                [("#FFD400", 0, 0, 128, 14), ("#00753F", 0, 14, 128, 14),
                 ("#00B7C3", 0, 28, 128, 14), ("#6A2CC4", 0, 42, 128, 14)],
            )
        )
        check(
            f"five hue families are counted as five ({ta._measure_png(many)['hue_families']})",
            ta._measure_png(many)["hue_families"] == 5,
        )
        check(
            "and no TH-HUES finding is produced at all",
            not any(p.startswith("TH-HUES") for p in ta._check_png(many)),
            str(ta._check_png(many)),
        )
        greys = Path(tmp) / "greys.png"
        greys.write_bytes(_cover(G, [("#FFFFFF", 8, 8, 40, 40), ("#111111", 60, 8, 40, 40)]))
        check(
            "black and white on one ground is one hue family, not three",
            ta._measure_png(greys)["hue_families"] == 1,
            str(ta._measure_png(greys)["hue_families"]),
        )

        # TH-BYTES, by moving the ceiling rather than building a 5 MB fixture.
        big = Path(tmp) / "big.png"
        big.write_bytes(_big_cover())
        old = ta.MAX_PNG_BYTES
        try:
            ta.MAX_PNG_BYTES = 10
            check(
                "a file over the size ceiling produces no retryable finding either — "
                "there is no phrasing that makes a diffusion model emit fewer bytes",
                not any(p.startswith("TH-BYTES") for p in ta._check_png(big)),
                str(ta._check_png(big)),
            )
        finally:
            ta.MAX_PNG_BYTES = old

        # Fail open, loudly: an encoding the decoder cannot read must not pass quietly and
        # must not fail a cover either (rule 21/31).
        odd = Path(tmp) / "odd.png"
        odd.write_bytes(_make_palette_png(8, 6, [_rgb(G), _rgb(A), _rgb(N)]))
        m = ta._measure_png(odd)
        check("a palette PNG is reported unreadable, not misread as RGB", not m["readable"], str(m))
        check("and yields no findings rather than a false failure", ta._check_png(odd) == [])
        check("png_probe declines it too rather than guessing", ta.png_probe(odd)[2] is None,
              str(ta.png_probe(odd)))


# ---------------------------------------------------------------------------
# The pivot's load-bearing assumption, executed on four vendors' bytes
# ---------------------------------------------------------------------------

FIXTURES = HERE / "fixtures" / "covers"

# Measured on the downsampled fixtures, which reproduce the originals' whole-canvas
# statistics to within 0.004 saturation and exactly on hue count. `contrast_ratio` is
# deliberately absent: it is not stable under sampling density (see the README beside the
# fixtures), which is a second independent reason TH-CONTRAST cannot be a hard gate.
EXPECTED = {
    "flux2pro":    {"saturation": 0.456, "hues": 4, "dims": (365, 205)},
    "gemini3pro":  {"saturation": 0.573, "hues": 4, "dims": (394, 220)},
    "gptimage2":   {"saturation": 0.854, "hues": 5, "dims": (384, 216)},
    "riverflow25": {"saturation": 0.906, "hues": 3, "dims": (427, 240)},
}


def test_real_cover_fixtures() -> None:
    """`png_scanlines` reads bytes it was not written for. See the module docstring.

    This is the single fact that made the pivot cheap, and it was verified rather than
    assumed: the decoder was written to measure PNGs Chrome had produced and never knew
    that. If a diffusion model's PNG had come back `readable=False`, every pixel gate
    would have died with the browser and there would have been nothing to replace them
    with (there is no Pillow in this venv).
    """
    print("real model output (4 vendors, downsampled)")
    if not FIXTURES.is_dir():
        skipped(
            f"  ⚠️  COVER_FIXTURES_MISSING — {FIXTURES} is absent, so the claim that the\n"
            "      pixel reader handles diffusion-model PNGs is UNVERIFIED here, not passed."
        )
        return
    for name, want in EXPECTED.items():
        path = FIXTURES / f"{name}.png"
        if not path.is_file():
            check(f"{name}: the fixture exists", False, f"missing {path}")
            continue
        m = ta._measure_png(path)
        check(
            f"{name}: a diffusion model's PNG decodes readably (8-bit non-interlaced RGB)",
            m["readable"] and (m["width"], m["height"]) == want["dims"],
            str({k: m[k] for k in ("readable", "width", "height")}),
        )
        check(
            f"{name}: saturation is {want['saturation']:.3f}, well over the "
            f"{ta.MIN_MEAN_SATURATION} floor",
            abs(m["mean_saturation"] - want["saturation"]) < 0.002
            and m["mean_saturation"] >= ta.MIN_MEAN_SATURATION,
            f"measured {m['mean_saturation']:.4f}",
        )
        check(
            f"{name}: {want['hues']} hue families — recorded, not gated",
            m["hue_families"] == want["hues"],
            str(m["hue_families"]),
        )
        # The fixtures are downsampled, so TH-SIZE is the ONE gate they must fail, and it
        # must be the only one. That makes this a two-sided assertion: the painted covers
        # clear every colour floor, and the floor that does fire is the expected one rather
        # than a fixture artefact nobody noticed.
        problems = ta._check_png(path)
        check(
            f"{name}: TH-SIZE is the only hard finding (the fixture is downsampled)",
            [p.split(":")[0] for p in problems] == ["TH-SIZE"],
            str(problems),
        )
    check(
        "all four vendors are represented — one model spelling is not a measurement",
        len([n for n in EXPECTED if (FIXTURES / f"{n}.png").is_file()]) == 4,
    )


def test_bakeoff_originals() -> None:
    """The full-size originals, if they are still on this machine.

    Loudly skipped rather than quietly absent, because these are the files the spec's
    calibration figures were measured from (saturation 0.459-0.910, contrast 12.4-14.5:1,
    1.61-5.56 MB) and the downsampled fixtures cannot pin the contrast column.
    """
    print("bake-off originals (calibration source)")
    src = Path(os.environ.get("BAKEOFF_DIR", "/tmp/bakeoff"))
    names = {
        "flux2pro": "black-forest-labs_flux.2-pro.png",
        "gemini3pro": "google_gemini-3-pro-image.png",
        "gptimage2": "openai_gpt-image-2.png",
        "riverflow25": "sourceful_riverflow-v2.5-pro.png",
    }
    present = {k: src / v for k, v in names.items() if (src / v).is_file()}
    if len(present) != len(names):
        skipped(
            f"  ⚠️  BAKEOFF_ORIGINALS_ABSENT — {len(present)}/{len(names)} found under {src}\n"
            "      (expected inside the worker image, and on any machine but the one that\n"
            "      ran the bake-off). The spec's contrast figures are UNVERIFIED here."
        )
        return
    for short, path in present.items():
        m = ta._measure_png(path)
        check(
            f"{short}: the original decodes readably at full size",
            m["readable"] and m["width"] >= ta.MIN_PNG_WIDTH,
            str({k: m[k] for k in ("readable", "width", "height")}),
        )
        check(
            f"{short}: the fixture's saturation tracks the original's ({m['mean_saturation']:.3f})",
            abs(m["mean_saturation"] - EXPECTED[short]["saturation"]) < 0.005,
            f"original {m['mean_saturation']:.4f} vs fixture {EXPECTED[short]['saturation']}",
        )
        check(
            f"{short}: contrast is over the 4.5:1 advisory ({m['contrast_ratio']:.1f}:1) — "
            "the figure the fixtures cannot pin",
            m["contrast_ratio"] >= ta.MIN_CONTRAST_RATIO,
            str(m["contrast_ratio"]),
        )
        check(
            f"{short}: and the only hard finding, if any, is TH-BYTES-free",
            not ta._check_png(path),
            str(ta._check_png(path)),
        )


# ---------------------------------------------------------------------------
# TH-ACCENT — the threshold, re-derived from the covers it was set from
# ---------------------------------------------------------------------------

REVIEW = HERE.parent / "output" / "covers-review"

# The calibration table from the note above `ACCENT_MIN_LUM`, as (path, accent%, verdict).
# Recorded to 0.1pp because that is the precision the note claims, and because the whole
# point of this case is that the number in the comment and the number the code produces are
# the same number. Ordered worst-verdict-last so a failure reads like the table.
ACCENT_CALIBRATION = (
    ("4-topic-sweep/silk-road.png",          49.4, "works"),
    ("4-topic-sweep/music-theory.png",       14.6, "works"),
    ("4-topic-sweep/compound-interest.png",   8.7, "works"),
    ("1-new-openrouter/supply-and-demand.png", 4.4, "works"),
    ("grounding/after/python-oop.png",         4.0, "unrecognisable"),
    ("grounding/before/python-oop.png",        3.9, "unrecognisable"),
    ("4-topic-sweep/recursion.png",            0.9, "unrecognisable"),
    ("grounding/before/economics.png",         0.8, "unrecognisable"),
    ("grounding/after/economics.png",          0.3, "worst"),
)


def test_accent_share_is_a_measurement() -> None:
    """`TH-ACCENT`'s threshold, re-derived from the nine covers it was set from.

    This is the case that makes 2% a measurement rather than a guess, and it is the case
    that caught the statistic being wrong. The table was calibrated with display luma;
    `_measure_png` was first written comparing against `luminance()` — WCAG relative
    luminance, which linearises — and that collapsed every figure and INTERLEAVED the two
    populations, so no threshold on it separated anything. Nothing else here could see that:
    every gate stayed green, and the advisory simply stopped meaning what its own comment
    said it meant. Rule 25, on my own reuse of a helper that was already in the file.

    Loudly skipped rather than quietly absent, because this corpus is local review output and
    is not in the worker image (rule 21).
    """
    print("accent_share — TH-ACCENT's calibration, re-derived")
    missing = [p for p, _, _ in ACCENT_CALIBRATION if not (REVIEW / p).is_file()]
    if missing:
        skipped(
            f"  ⚠️  ACCENT_CORPUS_MISSING — {len(missing)}/{len(ACCENT_CALIBRATION)} covers\n"
            f"      absent under {REVIEW} (expected inside the worker image, where the\n"
            "      review output does not ship). TH-ACCENT's 2% floor is UNVERIFIED here,\n"
            "      not passed, and the local run is its only gate."
        )
        return

    for rel, want, verdict in ACCENT_CALIBRATION:
        got = ta.accent_share(REVIEW / rel)
        check(
            f"{rel.split('/')[-1]} ({verdict}) measures {want}%",
            got is not None and abs(got * 100 - want) < 0.1,
            f"measured {None if got is None else round(got * 100, 2)}%",
        )

    # The two-sided claim. Not "the gate fires" — that is satisfiable by a gate that fires on
    # everything, which is the shape of the check that once flagged 76% of this project's
    # diagrams.
    fires = [
        rel for rel, _, _ in ACCENT_CALIBRATION
        if ta.accent_share(REVIEW / rel) < ta.MIN_ACCENT_SHARE
    ]
    check(
        f"the {ta.MIN_ACCENT_SHARE * 100:.0f}% floor fires on the three muddiest covers",
        sorted(fires) == sorted(
            ["grounding/after/economics.png", "grounding/before/economics.png",
             "4-topic-sweep/recursion.png"]
        ),
        str(sorted(fires)),
    )
    check(
        "and on NONE of the four that work — an advisory that fires on everything is noise",
        not [rel for rel, _, v in ACCENT_CALIBRATION
             if v == "works" and ta.accent_share(REVIEW / rel) < ta.MIN_ACCENT_SHARE],
    )
    # The honest limit, pinned as an assertion so it cannot be quietly forgotten by someone
    # promoting this to a hard gate. Both python-oop covers clear the floor and both are
    # unrecognisable: what is wrong with them is the SUBJECT, which no pixel statistic
    # reaches. Deleting this case is the cost of claiming otherwise.
    check(
        "the limit is real: both unrecognisable python-oop covers CLEAR the floor",
        all(
            ta.accent_share(REVIEW / rel) >= ta.MIN_ACCENT_SHARE
            for rel in ("grounding/after/python-oop.png", "grounding/before/python-oop.png")
        ),
        "TH-ACCENT separates muddy from not-muddy, not recognisable from unrecognisable",
    )
    # And the margin, stated as a number rather than as "close": 0.4pp between the lowest
    # working cover and the highest failing one. That is why the floor sits at 2% with
    # headroom under the good population instead of on the boundary between them.
    low_ok = min(ta.accent_share(REVIEW / r) for r, _, v in ACCENT_CALIBRATION if v == "works")
    high_bad = max(ta.accent_share(REVIEW / r) for r, _, v in ACCENT_CALIBRATION if v != "works")
    check(
        f"the populations are only {(low_ok - high_bad) * 100:.1f}pp apart, so the floor is "
        "set with headroom rather than on the boundary",
        low_ok > high_bad and ta.MIN_ACCENT_SHARE < low_ok / 2,
        f"lowest working {low_ok * 100:.2f}% vs highest failing {high_bad * 100:.2f}%",
    )

    # `TH-ACCENT` is an advisory, so it must be PRINTED and must not reach the caller as a
    # problem — the same contract every other advisory here has.
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        problems = ta._check_png(REVIEW / "grounding/after/economics.png")
    check(
        "the finding is printed with its measured share",
        "TH-ACCENT" in out.getvalue() and "0.3%" in out.getvalue(),
        out.getvalue(),
    )
    check(
        "and is NOT returned as a problem — advisory means advisory",
        not [p for p in problems if p.startswith("TH-ACCENT")],
        str(problems),
    )
    check(
        "the accent share is printed on every cover, not only on a failing one",
        "accent" in _stats_line(REVIEW / "4-topic-sweep/silk-road.png"),
        _stats_line(REVIEW / "4-topic-sweep/silk-road.png"),
    )


def _stats_line(path: Path) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ta._check_png(path)
    return out.getvalue()


def test_luma_is_not_luminance() -> None:
    """Two brightness functions, and the difference is why the case above exists.

    Written after the collapse: they agree at the endpoints and diverge hard in the
    mid-tones, which is exactly the range a painted cover's subject lives in. Pinned so that
    a future tidy-up cannot merge them back into one — that merge is the bug.
    """
    print("luma vs luminance")
    for r, g, b in ((0, 0, 0), (255, 255, 255)):
        check(
            f"they agree at {(r, g, b)}, which is why the swap looked harmless",
            abs(ta.luma(r, g, b) - ta.luminance(r, g, b)) < 0.01,
        )
    mid = (128, 128, 128)
    check(
        "and diverge by more than 2x on mid-grey, where a painted subject actually sits",
        ta.luma(*mid) > 2 * ta.luminance(*mid),
        f"luma {ta.luma(*mid):.3f} vs luminance {ta.luminance(*mid):.3f}",
    )
    check(
        "a mid orange clears ACCENT_MIN_LUM under luma and fails it under luminance — the "
        "single pixel that voided the calibration",
        ta.luma(255, 122, 26) > ta.ACCENT_MIN_LUM
        and ta.luminance(255, 122, 26) < ta.ACCENT_MIN_LUM,
        f"luma {ta.luma(255, 122, 26):.3f} vs luminance {ta.luminance(255, 122, 26):.3f}",
    )
    check(
        "contrast() still uses the WCAG one, which is what a contrast ratio requires",
        abs(ta.contrast("#FFFFFF", "#000000") - 21.0) < 0.01,
        str(ta.contrast("#FFFFFF", "#000000")),
    )


# ---------------------------------------------------------------------------
# generate_thumbnail — the retry loop and the fallback, against fakes
# ---------------------------------------------------------------------------

# One concept, named once, shared by `_spine` (which puts it in the curriculum) and `_Fake.llm`
# (which cites it). Written as a constant rather than twice as a literal because when the two
# disagree every case here fails identically on `TH-GROUND` — a fixture bug that reads exactly
# like a broken gate.
_SPINE_SOURCE = "Refractory period"


def _full(*a, **kw) -> str:
    """`_reply` plus the three gallery fields, for the paths that pass a brief.

    Every case in this section reaches `parse_art_direction` WITH a brief, where `STYLE:`,
    `LAYOUT:` and `LABELS:` are mandatory rather than optional — so a reply built by
    `_reply` alone is rejected as `TH-FORMAT` before an image is ever requested, and every
    case here would pass on that instead of on what it was written for. The same fixture
    coupling `MARKS:` already carries at `_reply`, one dimension along.

    The defaults are the single-subject, unlabelled path on purpose: `compose_image_prompt`
    appends byte-identical clauses to today's for them, so these cases stay a regression
    test on the four covers that work rather than becoming labelled-layout cases by
    accident. A case that cares about a style or a label passes its own.
    """
    kw.setdefault("style", "vector-illustration")
    kw.setdefault("layout", ta.SINGLE_SUBJECT)
    kw.setdefault("labels", ta.NO_MARKS)
    return _reply(*a, **kw)


class _Fake:
    """Stands in for both OpenRouter calls and the Claude turn. Records what was asked.

    Deliberately not a mock library: what these cases assert is a call COUNT and a control
    path, and the thing most likely to break is the loop, not the plumbing. A fake that
    books through the real `usage` accumulator also proves the report's cost is wired to
    something rather than to a literal.
    """

    # `png=VARY` rather than `png=None`: a distinguishable body per call is what makes
    # "which attempt shipped" answerable from the bytes, and `None` cannot mean that while
    # also being the natural default. It did, briefly, and the fallback case passed for the
    # wrong reason — every call returned identical bytes, so asserting the shipped bytes
    # were the LAST render was satisfied by any of them.
    VARY = object()

    def __init__(self, *, transcripts, replies=None, media_type="image/png", png=None,
                 spellings=None,
                 critique="SUBJECT: yes - a myelinated axon\nSTOCK: yes - none\n"
                          "TRUE: yes - no factual claim"):
        self.transcripts = list(transcripts)
        # The spell-back queue, defaulting to "agrees with the transcription": absent an
        # explicit spelling, `spell_back` spells out whatever `transcribe` last returned, so
        # the glyph gate is consistent with the word gate and every pre-existing case keeps
        # asserting what it was written to assert. A case that cares about the glyph hole
        # queues a spelling that DISAGREES — which is the whole defect, since the two calls
        # disagreeing is the only way `CLASSÆS` is visible.
        self.spellings = list(spellings or [])
        self.spelled = 0
        self.last_transcript = ""
        self.replies = list(replies or [])
        self.media_type = media_type
        self.png = _big_cover() if png is None else png
        self.image_prompts: list[str] = []
        self.claude_prompts: list[str] = []
        # The model each art-direction call was actually given, so a Bedrock name leaking
        # through `resolve_text_model` is visible here and not only in the printed line.
        self.art_models: list[str] = []
        self.transcribed = 0
        # The critique defaults to all-clean so that every pre-existing case keeps asserting
        # what it was written to assert. A case that cares passes its own reply, or an
        # Exception to take the fail-open path.
        self.critique = critique
        self.critiqued: list[bytes] = []

    async def llm(self, prompt, *a, **kw):
        # `(text, cost)`, and the cost is booked — this call is no longer Bedrock (where the
        # cost had to be priced by hand, rule 28) but a third OpenRouter call, and a report
        # whose `total_cost` omitted the art direction would understate every cover.
        self.claude_prompts.append(prompt)
        self.art_models.append(kw.get("model", ""))
        ta.usage.record(cost_usd=0.0074, input_tokens_delta=2100, output_tokens_delta=500, calls=1)
        if self.replies:
            value = self.replies.pop(0)
            # An Exception in the queue is RAISED, the same convention `transcribe` uses: a
            # failed art-direction call is a control path the loop has to handle, and it
            # cannot be expressed as a reply string.
            if isinstance(value, Exception):
                raise value
            return value, 0.0074
        # Cites a concept that IS in `_spine`, so the default path through the loop reaches
        # an image call. A default reply citing something else would make every case here
        # a TH-GROUND rejection, which is the shape of fixture bug that looks like a broken
        # gate.
        return _full(subject="a myelinated axon", source=_SPINE_SOURCE), 0.0074

    async def generate_image(self, prompt, **kw):
        self.image_prompts.append(prompt)
        ta.usage.record(cost_usd=0.045, input_tokens_delta=0, output_tokens_delta=7291, calls=1)
        # A distinguishable body per call, so "which attempt shipped" is answerable from
        # the bytes rather than inferred from the log.
        n = len(self.image_prompts)
        return (
            _vary(n) if self.png is _Fake.VARY else self.png,
            self.media_type,
            0.045,
        )

    async def transcribe(self, image_bytes, **kw):
        self.transcribed += 1
        ta.usage.record(cost_usd=0.004, input_tokens_delta=1200, output_tokens_delta=20, calls=1)
        value = self.transcripts.pop(0) if self.transcripts else "UNREADABLE"
        if isinstance(value, Exception):
            raise value
        self.last_transcript = value
        return value, 0.004

    async def spell_back(self, image_bytes, **kw):
        self.spelled += 1
        ta.usage.record(cost_usd=0.005, input_tokens_delta=1200, output_tokens_delta=60, calls=1)
        value = self.spellings.pop(0) if self.spellings else " ".join(self.last_transcript)
        if isinstance(value, Exception):
            raise value
        return value, 0.005

    async def ask_about_image(self, prompt, image_bytes, **kw):
        # Records the BYTES, not just a count: the critique's whole claim is that it looked
        # at the cover that ships, and only the bytes can prove which render that was.
        self.critiqued.append(image_bytes)
        ta.usage.record(cost_usd=0.005, input_tokens_delta=1400, output_tokens_delta=60, calls=1)
        if isinstance(self.critique, Exception):
            raise self.critique
        return self.critique, 0.005


@contextlib.contextmanager
def _patched(fake: _Fake):
    # All four patches land on `orr`, not on `ta`: the art direction is an OpenRouter call
    # now, and patching `ta._llm_call_async` — which no longer exists — would have raised
    # here rather than silently passing. That is the failure this indirection is worth
    # having.
    saved = (orr.complete_text, orr.generate_image, orr.transcribe, orr.ask_about_image,
             orr.spell_back)
    orr.complete_text, orr.generate_image, orr.transcribe, orr.ask_about_image, \
        orr.spell_back = (
            fake.llm, fake.generate_image, fake.transcribe, fake.ask_about_image,
            fake.spell_back,
        )
    ta.usage.reset()
    try:
        yield fake
    finally:
        (orr.complete_text, orr.generate_image, orr.transcribe,
         orr.ask_about_image, orr.spell_back) = saved
        ta.usage.reset()


def _spine(tmp: Path) -> Path:
    p = tmp / "course_spine.json"
    p.write_text(
        json.dumps(
            {
                "course_title": "How Neurons Fire",
                "course_description": "Membrane potentials from first principles.",
                "target_audience": "Beginners",
                "modules": [
                    {
                        "module_title": "The membrane",
                        "key_concepts": ["Resting membrane potential", "Ion channels"],
                    },
                    {
                        "module_title": "Action potentials",
                        "key_concepts": [_SPINE_SOURCE, "Depolarisation"],
                    },
                ],
            }
        )
    )
    return p


def _run(fake: _Fake, tmp: Path):
    with _patched(fake):
        return asyncio.run(ta.generate_thumbnail(_spine(tmp), tmp / "cover.png"))


def test_parse_critique() -> None:
    print("parse_critique (TH-SUBJECT / TH-STOCK / TH-TRUE)")
    clean = "SUBJECT: yes - a myelinated axon\nSTOCK: yes - none\nTRUE: yes - no factual claim"
    check("a clean critique yields no advisories", ta.parse_critique(clean) == [],
          str(ta.parse_critique(clean)))

    one = "SUBJECT: no - two crossing ropes could illustrate anything\nSTOCK: yes - none\nTRUE: yes - none"
    out = ta.parse_critique(one)
    check("a single no yields exactly one advisory", len(out) == 1, str(out))
    check("it is keyed to the right rule ID and carries the reason",
          out[0].startswith("TH-SUBJECT: ") and "crossing ropes" in out[0], str(out))

    # The measured case that prompted this gate: the two real Economics covers were both an
    # abstract pair of crossed objects with a spark, spelled perfectly, passing every pixel
    # gate. Only a reader of the picture can say so.
    both = ("SUBJECT: no - abstract crossed crystals\n"
            "STOCK: no - generic 'two forces meet' visual metaphor\n"
            "TRUE: yes - no factual claim")
    ids = [a.split(":")[0] for a in ta.parse_critique(both)]
    check("two nos yield two advisories, in rule order", ids == ["TH-SUBJECT", "TH-STOCK"], str(ids))

    for label, reply in (
        ("lowercase keys", "subject: no - generic\nstock: yes - none\ntrue: yes - none"),
        ("an em dash separator", "SUBJECT: no — generic\nSTOCK: yes - none\nTRUE: yes - none"),
        ("a colon separator", "SUBJECT: no: generic\nSTOCK: yes - none\nTRUE: yes - none"),
        ("no separator at all", "SUBJECT: no generic\nSTOCK: yes none\nTRUE: yes none"),
        ("preamble the prompt forbade",
         "Here is my review:\nSUBJECT: no - generic\nSTOCK: yes\nTRUE: yes"),
    ):
        got = [a.split(":")[0] for a in ta.parse_critique(reply)]
        check(f"parsed despite {label}", got == ["TH-SUBJECT"], f"{label}: {got}")

    # The important direction. An unanswered question must NOT read as a pass — a critique
    # that quietly returns nothing is indistinguishable from a clean cover, which is the
    # exact failure this whole gate exists to end (rule 21: fail open, but loudly).
    partial = ta.parse_critique("SUBJECT: yes - an axon")
    check("an unanswered question is reported, not passed", len(partial) == 2, str(partial))
    check("and it says it was not evaluated",
          all("not evaluated, not passed" in a for a in partial), str(partial))
    check("naming the two rules that were skipped",
          sorted(a.split(":")[0] for a in partial) == ["TH-STOCK", "TH-TRUE"], str(partial))

    junk = ta.parse_critique("I'm sorry, I can't help with that.")
    check("an unusable reply yields three advisories, not silence", len(junk) == 3, str(junk))
    check("and quotes what came back so it is debuggable",
          "I'm sorry" in junk[0], junk[0])
    check("an empty reply is three advisories too", len(ta.parse_critique("")) == 3)

    # First line wins, so a model that answers then rambles a second verdict cannot flip it.
    dup = ta.parse_critique("SUBJECT: no - generic\nSUBJECT: yes - fine\nSTOCK: yes\nTRUE: yes")
    check("the first answer for a key wins", len(dup) == 1 and dup[0].startswith("TH-SUBJECT"),
          str(dup))


def test_generate_thumbnail_critique_is_advisory() -> None:
    """The critique must inform and never block, cost an image call, or fail a run."""
    print("generate_thumbnail (the vision critique is advisory)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            critique=("SUBJECT: no - an abstract glow\nSTOCK: no - a lightbulb for an idea\n"
                      "TRUE: yes - no factual claim"),
        )
        report = _run(fake, tmp)
        # Three, not two: the critique names "an abstract glow" for a cover committed to "a
        # myelinated axon", so TH-GROUND fires as well — correctly, and for free. That is the
        # composite this fixture now exercises, and it is why the ID list is asserted rather
        # than a count: TH-GROUND is computed in `generate_thumbnail`, not in
        # `parse_critique`, so only a case that runs the loop can see it at all.
        check("the advisories reach the report",
              [a.split(":")[0] for a in report["advisories"]]
              == ["TH-SUBJECT", "TH-STOCK", "TH-GROUND"],
              str(report["advisories"]))
        # The separation is the point. `thumbnail.py` prints `problems` and ships anyway;
        # these are weaker still, so they must not be counted where a later reader could
        # make them blocking by accident.
        check("and NOT into problems — a generic cover is weaker, not broken",
              report["problems"] == [], str(report["problems"]))
        check("one critique call, on one attempt", len(fake.critiqued) == 1, str(len(fake.critiqued)))
        check("no extra image call was spent on it",
              len(fake.image_prompts) == 1 and report["attempts"] == 1,
              f"images={len(fake.image_prompts)} attempts={report['attempts']}")
        # Rule 29's concern, measured rather than argued: the critique judged the bytes that
        # ship, not an earlier render or a copy.
        check("it judged the bytes that shipped",
              fake.critiqued[0] == Path(report["png"]).read_bytes())
        check("its cost is booked", report["total_cost"] > 0.045 + 0.004, str(report["total_cost"]))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(transcripts=["HOW NEURONS FIRE"],
                     critique=orr.OpenRouterError("502 from the vision model"))
        report = _run(fake, tmp)
        check("a critique outage does not fail the run", Path(report["png"]).is_file())
        check("it is reported as one advisory naming all three rules",
              len(report["advisories"]) == 1 and "could not run" in report["advisories"][0],
              str(report["advisories"]))
        check("and the cover is still clean of problems", report["problems"] == [],
              str(report["problems"]))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(transcripts=["HOW NEURONS FIRE"], critique="SUBJECT: no - generic")
        os.environ["THUMBNAIL_CRITIQUE"] = "0"
        try:
            report = _run(fake, tmp)
        finally:
            del os.environ["THUMBNAIL_CRITIQUE"]
        check("THUMBNAIL_CRITIQUE=0 skips the call entirely — no vision spend",
              fake.critiqued == [], str(len(fake.critiqued)))
        check("and reports no advisories rather than inventing a pass",
              report["advisories"] == [], str(report["advisories"]))
        check("the cover still ships", Path(report["png"]).is_file())


def test_generate_thumbnail_clean_first_attempt() -> None:
    print("generate_thumbnail (clean on attempt 1)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        # Wrapped across lines, which is what 3 of the 4 real models did. So this case is
        # also the normaliser's end-to-end proof: an un-normalised comparison fails here.
        fake = _Fake(transcripts=["HOW\nNEURONS\nFIRE"])
        report = _run(fake, tmp)
        check("no problems on a clean cover", report["problems"] == [], str(report["problems"]))
        check("one attempt, one image call, one transcription",
              report["attempts"] == 1 and len(fake.image_prompts) == 1 and fake.transcribed == 1,
              f"attempts={report['attempts']} images={len(fake.image_prompts)} "
              f"transcribed={fake.transcribed}")
        check("the PNG is written where the caller asked", Path(report["png"]).is_file())
        # A superset, not an equality: `advisories` is read there too, and `subject`/`source`
        # are new here. The phase reads the dict by key, so a rename is invisible to every
        # other case in this file.
        needed = ("png", "problems", "attempts", "total_cost", "input_tokens",
                  "output_tokens", "api_calls", "advisories", "subject", "source",
                  "marks", "accent_share")
        check(
            "every key workers/phases/thumbnail.py reads back is present",
            all(k in report for k in needed),
            f"missing: {[k for k in needed if k not in report]}",
        )
        check(
            "the commitment is reported, so an off-curriculum cover is attributable",
            (report["subject"], report["source"]) == ("a myelinated axon", _SPINE_SOURCE),
            str((report["subject"], report["source"])),
        )
        check(
            "the markings are reported too — the blank-price-board defect is attributable",
            report["marks"] == "the glowing bands along the filament",
            repr(report["marks"]),
        )
        # Measured on the SHIPPED bytes rather than on the last attempt's, and `None` rather
        # than `0.0` when the PNG cannot be read: "unreadable" and "muddy" are different
        # facts and collapsing them would make a decoder failure look like a bad cover.
        check(
            "and the accent share of the shipped bytes, as a number rather than a verdict",
            isinstance(report["accent_share"], float) and 0.0 <= report["accent_share"] <= 1.0,
            repr(report["accent_share"]),
        )
        # The glyph gate runs on the pass path, once, and its cost is booked. It is the one
        # gate the whole painted-title design rests on.
        check(
            "the spell-back gate ran exactly once on a clean cover",
            fake.spelled == 1,
            f"spelled={fake.spelled}",
        )
        check(
            f"cost is booked, not reported as zero (${report['total_cost']:.4f} over "
            f"{report['api_calls']} calls)",
            report["total_cost"] > 0 and report["api_calls"] >= 2,
            str({k: report[k] for k in ("total_cost", "api_calls", "output_tokens")}),
        )
        check("the measured dimensions are reported", (report["width"], report["height"]) == (1280, 720),
              str((report["width"], report["height"])))
        check("the headline and the assigned palette are reported",
              report["headline"] == "HOW NEURONS FIRE" and report["palette"] in ta.PALETTES,
              str((report["headline"], report["palette"])))
        # The sidecar replaces the `.svg` one and is the only record of what was asked for:
        # a PNG cannot be diffed, so a cover that comes back wrong is otherwise undebuggable.
        sidecar = tmp / "cover.prompt.txt"
        check("the composed prompt is written beside the PNG", sidecar.is_file())
        check(
            "and it is the COMPOSED prompt — exclusions included — not the art direction alone",
            "watermark" in sidecar.read_text() and sidecar.read_text() == fake.image_prompts[0],
        )


def test_generate_thumbnail_keeps_failed_attempts() -> None:
    """The failed renders survive when asked for — and are absent when not.

    The gap this closes is in my own method, not in the cover. Every attempt writes to the
    same `out_png` and the next one overwrites it, so at the end of a run only the shipped
    render exists. In this project every real finding came from *opening a PNG* (rule 18), so
    the loop was destroying the one artifact that can explain a failure: `chalkboard`
    transcribed back as `''` twice and "headline missing", "headline mis-lit" and "headline
    unreadable to the vision model" are three different fixes that the message
    `the picture reads ''` cannot distinguish between.

    Both directions are asserted, because the default matters as much as the feature: these
    are unvalidated renders and `OUTPUT_DIR` is a prefix other phases sync (rule 29).
    """
    print("generate_thumbnail (failed attempts are keepable, and off by default)")

    def run_with(env: dict[str, str], transcripts: list[str]) -> tuple[Path, dict, object]:
        tmp = Path(tempfile.mkdtemp())
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            fake = _Fake(transcripts=transcripts, png=_Fake.VARY)
            report = _run(fake, tmp)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        return tmp, report, fake

    # Two failures then a pass — the exact shape of the chalkboard cover.
    fails_then_passes = ["", "", "HOW NEURONS FIRE"]

    tmp, report, _ = run_with({"THUMBNAIL_KEEP_ATTEMPTS": "1"}, fails_then_passes)
    kept = sorted(p.name for p in tmp.glob("cover.attempt*.png"))
    check(
        "each attempt's render is kept beside the cover",
        kept == ["cover.attempt1.png", "cover.attempt2.png", "cover.attempt3.png"],
        str(kept),
    )
    check(
        "and each carries the prompt that produced IT, not the last one",
        sorted(p.name for p in tmp.glob("cover.attempt*.prompt.txt"))
        == ["cover.attempt1.prompt.txt", "cover.attempt2.prompt.txt",
            "cover.attempt3.prompt.txt"],
        str(sorted(p.name for p in tmp.glob("cover.attempt*.prompt.txt"))),
    )
    # The point of keeping them: the FAILED bytes must be the failed bytes, not three copies
    # of what shipped. `png=VARY` gives each render a distinguishable body, which is the only
    # way this assertion can fail if the helper is wired to the wrong variable.
    bodies = [(tmp / n).read_bytes() for n in kept]
    check(
        "the kept renders are three DIFFERENT images, so a failure can be looked at",
        len(set(bodies)) == 3,
        f"{len(set(bodies))} distinct bodies",
    )
    check(
        "the last kept render is byte-identical to the cover that shipped",
        bodies[-1] == Path(report["png"]).read_bytes(),
    )
    check(
        "keeping them does not change what ships",
        report["problems"] == [] and report["attempts"] == 3,
        f"problems={report['problems']} attempts={report['attempts']}",
    )
    shutil.rmtree(tmp, ignore_errors=True)

    # Off by default. Asserted with the env var ABSENT rather than set to "0", because the
    # default is what a worker runs with and a test that sets it to "0" would pass even if the
    # default flipped.
    tmp, report, _ = run_with({}, fails_then_passes)
    check(
        "nothing extra is written by default — one PNG, one sidecar",
        sorted(p.name for p in tmp.iterdir() if p.suffix in (".png", ".txt"))
        == ["cover.png", "cover.prompt.txt"],
        str(sorted(p.name for p in tmp.iterdir())),
    )
    check("and the default is off, read per call", ta.keep_attempts_enabled() is False)
    shutil.rmtree(tmp, ignore_errors=True)

    for value in ("1", "true", "yes"):
        os.environ["THUMBNAIL_KEEP_ATTEMPTS"] = value
        check(f"{value!r} enables it", ta.keep_attempts_enabled() is True)
    for value in ("0", "false", "no", ""):
        os.environ["THUMBNAIL_KEEP_ATTEMPTS"] = value
        check(f"{value!r} leaves it off", ta.keep_attempts_enabled() is False)
    os.environ.pop("THUMBNAIL_KEEP_ATTEMPTS", None)

    # Fails soft: a diagnostic that can fail a run is worse than no diagnostic.
    os.environ["THUMBNAIL_KEEP_ATTEMPTS"] = "1"
    try:
        with tempfile.TemporaryDirectory() as t:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                kept_path = ta._keep_attempt(
                    Path(t) / "nope" / "cover.png", "attempt1", b"x", "p"
                )
            check(
                "an unwritable path is reported and returns None rather than raising",
                kept_path is None and "could not keep" in out.getvalue(),
                out.getvalue()[-200:],
            )
    finally:
        os.environ.pop("THUMBNAIL_KEEP_ATTEMPTS", None)


def test_generate_thumbnail_subject_markings_do_not_cost_the_headline() -> None:
    """The `recursion` regression, end to end — the plan's own named risk, after the fix.

    This is the failure the plan predicted `MARKS` might introduce, and it fired on 1 of the 4
    live covers: the subject's own numerals reached the transcription and the cover lost its
    title. Reproduced here with the measured transcript verbatim, because the whole chain has
    to be asserted rather than just the string function — the second half of the defect was in
    the *fallback*, which could not succeed for a subject whose markings are digits.
    """
    print("generate_thumbnail (subject markings vs the transcription gate)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            # Verbatim from artifact/results.json, attempt 3 of the recursion cover.
            transcripts=["HOW NEURONS FIRE\n12\n7\n19\n20"],
            spellings=["H O W  N E U R O N S  F I R E"],
        )
        report = _run(fake, tmp)
        check(
            "a cover whose subject carries numerals ships on attempt 1 with no TH-TITLE",
            report["attempts"] == 1 and report["problems"] == [],
            f"attempts={report['attempts']} problems={report['problems']}",
        )
        check(
            "one image call, not four — the four wasted renders are the cost this removes",
            len(fake.image_prompts) == 1,
            f"images={len(fake.image_prompts)}",
        )
        check(
            "and the spell-back gate still ran on it, so the tolerance did not skip a check",
            fake.spelled == 1,
        )

    # The other half: a word in the artwork must STILL cost the cover, or the fix has traded a
    # false positive for a hole. Same shape, one letter-bearing token instead of digits.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE SHUTTERSTOCK", "HOW NEURONS FIRE"],
            png=_Fake.VARY,
        )
        report = _run(fake, tmp)
        check(
            "a readable WORD in the artwork is still a TH-TITLE failure and is still retried",
            report["attempts"] == 2 and report["problems"] == [],
            f"attempts={report['attempts']} problems={report['problems']}",
        )
        check(
            "and the correction turn names the extra text rather than the headline's spelling",
            "TH-TITLE" in fake.claude_prompts[1]
            and "SHUTTERSTOCK" in fake.claude_prompts[1],
            fake.claude_prompts[1][-300:],
        )


def test_generate_thumbnail_marks_group_is_not_judged() -> None:
    """The two-group transcription, end to end — the 4 Sep 2026 regression and its fix.

    The case above covers markings that happen to be DIGITS, which `lexical_text` drops. It
    passed while the live run failed, and that gap is the whole reason this second case
    exists: real object markings carry letters. `python-oop` attempt 2 painted its headline
    AND all three declared labels correctly and was rejected over `'19068G' 'XHPVE' '501S'
    'NAW' 'V7'` — a stamped casting. Four of five covers were flagged this way and two shipped
    with no title at all, because the correction turn asked the model to make the subject's
    writing unreadable and it obliged with the largest text in the frame.

    So the discrimination is the vision model's now, and both directions are pinned: writing
    that belongs to the object is recorded and ignored, while text laid OVER the picture still
    costs an attempt. A fix that swallowed the second half would have traded a false positive
    for a hole — the same trade the digit tolerance above is guarded against.
    """
    print("generate_thumbnail (the MARKS group is recorded, never judged)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            # Verbatim from styled/results.json, the python-oop cover: letter-bearing tokens
            # off a stamped casting, which the old whole-frame gate hard-failed.
            transcripts=["TEXT: HOW NEURONS FIRE\nMARKS: 19068G XHPVE 501S NAW V7"],
            spellings=["H O W  N E U R O N S  F I R E"],
        )
        report = _run(fake, tmp)
        check(
            "letter-bearing markings on the subject ship on attempt 1 with no TH-TITLE",
            report["attempts"] == 1 and report["problems"] == [],
            f"attempts={report['attempts']} problems={report['problems']}",
        )
        check(
            "one image call — the three wasted renders are what this removes",
            len(fake.image_prompts) == 1,
            f"images={len(fake.image_prompts)}",
        )
        # Recorded rather than gated, and rule 27's corollary is why it is asserted: a value
        # computed and then read by nothing is not evidence. `marks_seen` is what makes the
        # ten-sample precision check (rule 25) possible later without another live run.
        check(
            "and what was read off the object reaches the report, unjudged",
            report["marks_seen"] == "19068G XHPVE 501S NAW V7",
            repr(report.get("marks_seen")),
        )

    # The other direction. A watermark is ADDED text, the vision model sorts it into TEXT, and
    # it must still cost the cover an attempt — otherwise the split is a hole, not a fix.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=[
                "TEXT: HOW NEURONS FIRE SHUTTERSTOCK\nMARKS: 19068G 501S",
                "TEXT: HOW NEURONS FIRE\nMARKS: 19068G 501S",
            ],
            spellings=["H O W  N E U R O N S  F I R E"],
            png=_Fake.VARY,
        )
        report = _run(fake, tmp)
        check(
            "a watermark sorted into TEXT is still a hard TH-TITLE and is still retried",
            report["attempts"] == 2 and report["problems"] == [],
            f"attempts={report['attempts']} problems={report['problems']}",
        )
        # Scoped to the FINDING, not the whole prompt, and that is not pedantry: the spec
        # quotes these very tokens as the measurement that produced this fix, so a search over
        # the composed prompt finds them in the documentation and fails for the wrong reason.
        # It did, once this section of the spec was written.
        at = fake.claude_prompts[1].index("TH-TITLE: the headline is correct")
        finding = fake.claude_prompts[1][at : at + 500]
        check(
            "the correction names the added word and NOT the object's markings",
            "SHUTTERSTOCK" in finding and "19068G" not in finding and "501S" not in finding,
            finding,
        )
        # The sentence that made the model destroy its own headline. Pinned as absent in the
        # text the model actually receives, because deleting it from the constant and leaving
        # it in the finding would have fixed nothing (rule 26).
        check(
            "and it never asks for the subject's writing to be made unreadable",
            "too small to read" not in fake.claude_prompts[1],
            fake.claude_prompts[1][-400:],
        )


def test_generate_thumbnail_glyph_gate() -> None:
    """`TH-GLYPH` — the hole the word gate cannot see, closed with a second question.

    The measured escape: a shipped cover painted `CLASSÆS`, an Æ ligature where `ES` belonged,
    and `transcribe` returned `MASTER PYTHON CLASSES`. Nothing was broken — a vision model
    asked to read *words* answers with the word it expects, so the transcription was a
    plausible reading of a malformed picture. Only asking for the CHARACTERS makes it visible,
    which is why the two calls exist and why the fake's default is for them to agree.
    """
    print("generate_thumbnail (TH-GLYPH — the ligature the word gate cannot see)")
    lig = "H O W  N E U R O N S  F I R Æ"

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        # The word gate PASSES on both attempts while the FIRST spelling disagrees: exactly
        # the `CLASSÆS` shape, and the case would be satisfied for the wrong reason if the
        # transcription had failed too.
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"] * 2,
            spellings=[lig, "H O W  N E U R O N S  F I R E"],
            png=_Fake.VARY,
        )
        report = _run(fake, tmp)
        check(
            "a malformed character is caught even though the transcription reads correctly",
            len(fake.image_prompts) == 2 and report["problems"] == [],
            f"images={len(fake.image_prompts)} problems={report['problems']}",
        )
        # Asserted on the CORRECTION TURN, which is where the finding has to land to be worth
        # anything: a problem that is printed and not fed back is a log line, not a gate
        # (rule 27's shape — grep for whether the verdict is ever read).
        glyph = fake.claude_prompts[1]
        check(
            "and the finding is fed back to the next turn as a fixable defect",
            "TH-GLYPH" in glyph,
            glyph[-400:],
        )
        # Rule 24: the finding must name a fix the thing it names can perform. "Move the text"
        # cannot fix a ligature, and that is the trap this message was written against.
        check(
            "the finding names the character defect, not a placement one",
            "cannot be fixed by moving the text" in glyph and "ligature" in glyph,
            glyph[-400:],
        )
        check(
            "and it quotes what was spelled against what was wanted",
            "HOWNEURONSFIRÆ" in glyph and "HOWNEURONSFIRE" in glyph,
            glyph[-400:],
        )
        check(
            "the cover that ships is the corrected render, not the malformed one",
            Path(report["png"]).read_bytes() == _vary(2),
        )

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        # TH-GLYPH is a TEXT failure, so it must reach the same fallback TH-TITLE does. A
        # cover whose headline is a malformed word is worse than one with no headline: the
        # correct title is already page text beside the cover, so wrong letters in the picture
        # add nothing and subtract credibility.
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"] * ta.MAX_ATTEMPTS + [orr.NO_TEXT],
            spellings=[lig] * ta.MAX_ATTEMPTS,
            png=_Fake.VARY,
        )
        report = _run(fake, tmp)
        check(
            f"an unfixable ligature retries {ta.MAX_ATTEMPTS} times and then ships text-free",
            len(fake.image_prompts) == ta.MAX_ATTEMPTS + 1
            and Path(report["png"]).read_bytes() == _vary(ta.MAX_ATTEMPTS + 1),
            f"{len(fake.image_prompts)} image call(s)",
        )
        check(
            "the spell-back gate ran on every attempt whose words passed, and not on the "
            "text-free render",
            fake.spelled == ta.MAX_ATTEMPTS,
            f"spelled={fake.spelled}",
        )

    # Same letters, different spacing and case: the comparison folds everything the spelling
    # reply adds and folds NO letter, so this must pass. The normaliser is load-bearing here
    # for the same reason as on the word gate — a real reply came back line-broken.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            spellings=["h-o-w  n e u r o n s\nF, I, R, E."],
        )
        report = _run(fake, tmp)
        check(
            "punctuation, case and line breaks in the spelling are noise, not a defect",
            not [p for p in report["problems"] if p.startswith("TH-GLYPH")],
            str(report["problems"]),
        )
        check("and no retry was bought for it", len(fake.image_prompts) == 1)

    # A dropped or doubled letter is the other half of the same hole, and it is the half a
    # word-level comparison is most likely to forgive.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"] * 2,
            spellings=["H O W  N E U R R O N S  F I R E", "H O W  N E U R O N S  F I R E"],
            png=_Fake.VARY,
        )
        _run(fake, tmp)
        check(
            "a doubled letter is caught too",
            len(fake.image_prompts) == 2 and "TH-GLYPH" in fake.claude_prompts[1],
            f"images={len(fake.image_prompts)}",
        )

    # Fails OPEN, loudly. This is a read-only audit of our own output, and an outage must not
    # turn a correct cover into four wasted image calls and a text-free fallback (rule 21/31).
    # The asymmetry with `_require_png` — which fails closed — is deliberate: that one writes.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            spellings=[orr.OpenRouterError("vision 503")],
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            report = _run(fake, tmp)
        check(
            "a spell-back outage ships the cover rather than failing it",
            report["problems"] == [] and len(fake.image_prompts) == 1,
            str(report["problems"]),
        )
        check(
            "and says out loud that the gate did not run — fail-open, never fail-open quietly",
            "TH-GLYPH_GATE_SKIPPED" in out.getvalue(),
            out.getvalue()[-200:],
        )

    # And the money: a headline the word gate already rejected must NOT buy a second opinion.
    # The finding exists; confirming it would spend $0.005 per attempt to learn nothing.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRES"] * ta.MAX_ATTEMPTS + [orr.NO_TEXT],
            png=_Fake.VARY,
        )
        _run(fake, tmp)
        check(
            "no spell-back call is bought on a cover the word gate already failed",
            fake.spelled == 0,
            f"spelled={fake.spelled}",
        )

    # A HEADLINE SET ON TWO LINES. The image model breaks a long title wherever it likes and
    # `transcribe` already returns that as `\n` — so the *word* gate has always folded it. The
    # question `SPELL_PROMPT` asks did not: "the largest headline text" names something
    # ambiguous on a two-line title, and a model answering with the largest LINE spells a
    # truthful prefix of the right headline. That is a hard TH-GLYPH on a correctly-painted
    # cover: four wasted image calls and a text-free fallback, caused by the wording of the
    # question rather than by anything in the picture.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS\nFIRE"],
            spellings=["H O W  N E U R O N S\nF I R E"],
        )
        report = _run(fake, tmp)
        check(
            "a two-line headline spelled line by line is not a defect",
            not [p for p in report["problems"] if p.startswith("TH-GLYPH")]
            and len(fake.image_prompts) == 1,
            f"problems={report['problems']} images={len(fake.image_prompts)}",
        )

    # And the half that must still fail, or the case above would prove only that the gate had
    # been loosened. A model reading ONE line of a two-line headline drops real letters, and
    # dropped letters are the defect this gate exists for.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"] * 2,
            spellings=["H O W  N E U R O N S", "H O W  N E U R O N S  F I R E"],
            png=_Fake.VARY,
        )
        _run(fake, tmp)
        check(
            "a spelling that stops at the first line is still caught",
            len(fake.image_prompts) == 2 and "TH-GLYPH" in fake.claude_prompts[1],
            f"images={len(fake.image_prompts)}",
        )

    # The prompt itself, pinned. This is the whole fix for the case above: the clause is not
    # reachable through any behaviour the fake can simulate — a fake answers however it is
    # told to — so the only thing that can assert it is the text sent to the model. A rule
    # stated in a prompt and asserted by nothing is what rule 26 is about.
    check(
        "SPELL_PROMPT asks for every line of the headline, not the largest line",
        "two or more lines" in orr.SPELL_PROMPT
        and "as one continuous headline" in orr.SPELL_PROMPT,
        orr.SPELL_PROMPT,
    )
    check(
        "and still asks for characters, not words — the anti-autocomplete clauses survive",
        "one character at a "  # split across the source lines
        "time" in orr.SPELL_PROMPT
        and "do not correct it" in orr.SPELL_PROMPT
        and "not a real word" in orr.SPELL_PROMPT,
        orr.SPELL_PROMPT,
    )
    check(
        "and it excludes the smaller text, so LABELS: never reach the headline gate",
        "Do not spell any smaller text" in orr.SPELL_PROMPT,
        orr.SPELL_PROMPT,
    )


def test_generate_thumbnail_ships_text_free_after_four_failures() -> None:
    """The fallback. It must never raise. See the module docstring."""
    print("generate_thumbnail (4 failures → text-free)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRES"] * ta.MAX_ATTEMPTS + [orr.NO_TEXT],
            png=_Fake.VARY,
        )
        report = _run(fake, tmp)
        check(
            f"{ta.MAX_ATTEMPTS} unreadable headlines plus one text-free render, no exception",
            len(fake.image_prompts) == ta.MAX_ATTEMPTS + 1,
            f"{len(fake.image_prompts)} image call(s)",
        )
        check(
            "the fallback render asks positively for no writing and carries no headline at all",
            "no writing of any kind" in fake.image_prompts[-1]
            and "HOW NEURONS FIRE" not in fake.image_prompts[-1].upper(),
            fake.image_prompts[-1][-160:],
        )
        check(
            "exactly one unresolved problem, and it is TH-TITLE",
            [p.split(":")[0] for p in report["problems"]] == ["TH-TITLE"],
            str(report["problems"]),
        )
        check(
            "the problem string says the cover is degraded, not broken, and says to look at it",
            "degraded, not broken" in report["problems"][0] and "look at it" in report["problems"][0],
            report["problems"][0],
        )
        check(
            f"attempts records the extra render ({ta.MAX_ATTEMPTS + 1})",
            report["attempts"] == ta.MAX_ATTEMPTS + 1, str(report["attempts"]),
        )
        # The shipped bytes must be the text-free render, not the least-bad misspelled one:
        # the correct title is already page text beside the cover, so wrong words in the
        # picture add nothing and subtract credibility.
        shipped = Path(report["png"]).read_bytes()
        check(
            "the bytes on disk are the text-free render, not an earlier attempt",
            shipped == _vary(ta.MAX_ATTEMPTS + 1),
            f"{len(shipped)} bytes",
        )
        check("a PNG exists at all — the phase treats a raise as no cover", Path(report["png"]).is_file())
        # The sidecar is the only record of an un-diffable artifact, so it must describe the
        # render that shipped. It described attempt 4 while the text-free render shipped
        # until the single-write fix.
        check(
            "and the sidecar describes THAT render, not the last attempt",
            (tmp / "cover.prompt.txt").read_text() == fake.image_prompts[-1],
            (tmp / "cover.prompt.txt").read_text()[-120:],
        )


def test_generate_thumbnail_keeps_the_best_when_the_fallback_also_has_text() -> None:
    print("generate_thumbnail (the text-free render is not text-free)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRES"] * (ta.MAX_ATTEMPTS + 1), png=_Fake.VARY
        )
        report = _run(fake, tmp)
        check(
            "two problems: the unreadable headline and the failed fallback",
            [p.split(":")[0] for p in report["problems"]] == ["TH-TITLE", "TH-TITLE"],
            str(report["problems"]),
        )
        check(
            "the second names what the fallback actually read",
            "not text-free either" in report["problems"][1]
            and "HOW NEURONS FIRES" in report["problems"][1],
            report["problems"][1],
        )
        check(
            f"and the shipped cover is the first attempt, not the fresh one "
            f"(attempts={report['attempts']})",
            report["attempts"] == ta.MAX_ATTEMPTS
            and Path(report["png"]).read_bytes() == _vary(1),
            f"attempts={report['attempts']}, {len(Path(report['png']).read_bytes())} bytes",
        )

    # The fallback reads the TEXT group too, and that is a second place the old whole-frame
    # rule was wrong. `economics` (4 Sep 2026) shipped a SECOND TH-TITLE naming `'154 NIZ 25'`
    # — stencilling on a crate in a picture that was correctly free of added text. A crate is
    # not a failed render, so a MARKS-only transcription is a clean fallback.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRES"] * ta.MAX_ATTEMPTS
            + [f"TEXT: {orr.NO_TEXT}\nMARKS: 154 NIZ 25"],
            png=_Fake.VARY,
        )
        report = _run(fake, tmp)
        check(
            "a MARKS-only fallback counts as text-free — one problem, not two",
            [p.split(":")[0] for p in report["problems"]] == ["TH-TITLE"],
            str(report["problems"]),
        )
        check(
            "and the fallback's own markings still reach the report unjudged",
            report["marks_seen"] == "154 NIZ 25",
            repr(report.get("marks_seen")),
        )


def test_generate_thumbnail_transcription_outage_fails_open() -> None:
    """A vision outage must not cost four image calls and a text-free cover.

    The asymmetry with `_require_png` is the whole point and it is per-path, not a style
    (rule 31): the transcription is a read-only audit of our own output, so it fails OPEN
    and loudly; writing a JPEG to a `.png` key is a write, so that fails CLOSED.
    """
    print("generate_thumbnail (TH-TITLE_GATE_SKIPPED)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(transcripts=[orr.OpenRouterError("502 from the vision provider")])
        report = _run(fake, tmp)
        check(
            "the attempt is accepted rather than retried",
            report["attempts"] == 1 and len(fake.image_prompts) == 1,
            f"attempts={report['attempts']} images={len(fake.image_prompts)}",
        )
        check("and no TH-TITLE problem is invented", report["problems"] == [], str(report["problems"]))
        check("a cover still ships", Path(report["png"]).is_file())


def test_generate_thumbnail_bad_reply_costs_no_image_call() -> None:
    print("generate_thumbnail (unusable art direction)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            replies=[
                "I'd be happy to help! Here is a lovely cover idea.",
                # Subject matched to the fake critique's default, so this case reports only
                # the defect it is about; the mismatch is pinned in `test_ground_advisory`.
                _full(subject="a myelinated axon", source=_SPINE_SOURCE),
            ],
        )
        report = _run(fake, tmp)
        check(
            "the malformed reply is retried with NO image call spent",
            len(fake.image_prompts) == 1 and report["attempts"] == 2,
            f"images={len(fake.image_prompts)} attempts={report['attempts']}",
        )
        check(
            "the correction turn is told the format was the problem",
            "TH-FORMAT" in fake.claude_prompts[1],
            fake.claude_prompts[1][:200],
        )
        check("and the cover is clean once the reply parses", report["problems"] == [],
              str(report["problems"]))


def test_generate_thumbnail_off_curriculum_source_costs_no_image_call() -> None:
    """TH-GROUND's hard half, end to end through the loop.

    The point of putting the citation check before the image call is the money: the image is
    the expensive call and `MAX_ATTEMPTS = 4`. So this asserts a call COUNT, not just that the
    retry happened — a check that rejected the reply *after* buying a picture would satisfy
    every other assertion here.
    """
    print("generate_thumbnail (a SOURCE not in this curriculum)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            replies=[
                _full(subject="two crossed crystals", source="Terms of trade"),
                _full(subject="a myelinated axon", source=_SPINE_SOURCE),
            ],
        )
        report = _run(fake, tmp)
        check(
            "the invented citation is retried with NO image call spent",
            len(fake.image_prompts) == 1 and report["attempts"] == 2,
            f"images={len(fake.image_prompts)} attempts={report['attempts']}",
        )
        check(
            "the correction turn names the rule and quotes the citation it rejected",
            "TH-GROUND" in fake.claude_prompts[1] and "Terms of trade" in fake.claude_prompts[1],
            fake.claude_prompts[1][-400:],
        )
        check(
            "and it lists real citations, so the fix is one turn away (rule 24)",
            _SPINE_SOURCE in fake.claude_prompts[1],
            fake.claude_prompts[1][-400:],
        )
        check(
            "the cover that ships is the grounded one",
            report["source"] == _SPINE_SOURCE and report["problems"] == [],
            str((report["source"], report["problems"])),
        )
        check(
            "and the curriculum reached the prompt in the first place",
            "Refractory period" in fake.claude_prompts[0]
            and "the material the subject must come" in fake.claude_prompts[0],
        )


def test_generate_thumbnail_marks_and_headline_cost_no_image_call() -> None:
    """The two new pre-image refusals, end to end, asserted as a CALL COUNT.

    Same argument as the citation gate above and the same reason it is a count rather than a
    message: a check that rejected the reply *after* buying a picture would satisfy every
    other assertion here while spending the expensive call. `MAX_ATTEMPTS = 4` image renders
    sit on the other side of this line.
    """
    print("generate_thumbnail (TH-MARKS / TH-WORDS before the spend)")
    blank_board = (
        "A split-flap price board filling the frame, its flaps converged flat and blank, "
        "lit by one warm lamp, deep shadow behind. The words HOW NEURONS FIRE sit in the "
        "calm upper-left of the frame, in a clear area with nothing behind them."
    )
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            replies=[
                # The measured defect, verbatim in shape: markings named, then a prompt that
                # asks for the object BLANK. This is the price board with no prices, and it is
                # `_MARK_NEGATIONS` that catches it rather than the positive test — "on each
                # flap" is satisfied by "flaps", which is the hole `test_check_marks` pins.
                _full(
                    subject="a split-flap price board",
                    source=_SPINE_SOURCE,
                    marks="crisp white numerals on each flap",
                    art=blank_board,
                ),
                _full(subject="a myelinated axon", source=_SPINE_SOURCE),
            ],
        )
        report = _run(fake, tmp)
        check(
            "markings named but not painted are retried with NO image call spent",
            len(fake.image_prompts) == 1 and report["attempts"] == 2,
            f"images={len(fake.image_prompts)} attempts={report['attempts']}",
        )
        check(
            "the correction turn names TH-MARKS and quotes the markings it rejected",
            "TH-MARKS" in fake.claude_prompts[1]
            and "crisp white numerals" in fake.claude_prompts[1],
            fake.claude_prompts[1][-400:],
        )
        check("and the cover that ships is clean", report["problems"] == [], str(report["problems"]))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        # The other measured failure: `SUPPLY MEETS DEMAND` on a course called `Economics for
        # Developers`. Here the spine's course is `How Neurons Fire`, so a headline about
        # membranes shares nothing with it.
        off = _ART.replace("HOW NEURONS FIRE", "IONS ON THE MOVE")
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            replies=[
                _full("IONS ON THE MOVE", off, subject="a myelinated axon", source=_SPINE_SOURCE),
                _full(subject="a myelinated axon", source=_SPINE_SOURCE),
            ],
        )
        report = _run(fake, tmp)
        check(
            "a headline that names no course is retried with NO image call spent",
            len(fake.image_prompts) == 1 and report["attempts"] == 2,
            f"images={len(fake.image_prompts)} attempts={report['attempts']}",
        )
        check(
            "the correction turn names TH-WORDS and offers the course's own words",
            "TH-WORDS" in fake.claude_prompts[1] and "neuron" in fake.claude_prompts[1].lower(),
            fake.claude_prompts[1][-400:],
        )
        check(
            "and the headline that ships is the one that names the course",
            report["headline"] == "HOW NEURONS FIRE" and report["problems"] == [],
            str((report["headline"], report["problems"])),
        )


def test_generate_thumbnail_gallery_refusals_cost_no_image_call() -> None:
    """The three new refusals, end to end, asserted as a CALL COUNT.

    Same argument as the citation and marks gates: the whole reason a style, a layout and a
    label are checked in the reply rather than in the picture is that the reply costs one
    text call and the picture costs an image call against `MAX_ATTEMPTS = 4`. A check that
    refused after buying a render would satisfy every message assertion here and still be the
    wrong design, so the count is what is pinned.
    """
    print("generate_thumbnail (an unknown style, layout or label)")
    for bad, rule, quoted in (
        ({"style": "watercolor"}, "TH-STYLE", "watercolor"),
        ({"layout": "jigsaw"}, "TH-LAYOUT", "jigsaw"),
        # The label case needs a layout with somewhere to put a label, and an art direction
        # that asks for it — otherwise the reply is refused for the wrong reason and the case
        # passes on a defect it was not written for.
        (
            {
                "layout": "hub-spoke",
                "labels": "Synaptic plasticity",
                "art": _ART + " The label Synaptic plasticity sits beside it.",
            },
            "TH-LABELS",
            "Synaptic plasticity",
        ),
    ):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            fake = _Fake(
                transcripts=["HOW NEURONS FIRE"],
                replies=[
                    _full(subject="a myelinated axon", source=_SPINE_SOURCE, **bad),
                    _full(subject="a myelinated axon", source=_SPINE_SOURCE),
                ],
            )
            report = _run(fake, tmp)
            check(
                f"{rule} is refused with NO image call spent",
                len(fake.image_prompts) == 1 and report["attempts"] == 2,
                f"images={len(fake.image_prompts)} attempts={report['attempts']}",
            )
            check(
                f"the correction turn names {rule} and quotes {quoted!r}",
                rule in fake.claude_prompts[1] and quoted in fake.claude_prompts[1],
                fake.claude_prompts[1][-400:],
            )
            check(
                "and the cover that ships is the one whose choices were legal",
                report["problems"] == [],
                str(report["problems"]),
            )

    # The report keys, which is what `phases/thumbnail.py` reads. Deliberately NOT on the
    # `##PHASE##` marker: `courses.py::_parse_marker` splits the body on `:` before splitting
    # fields on the first `=`, and a style name is fine but a label is arbitrary curriculum
    # text — one colon in it and the marker parse silently loses the rest of the line.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(transcripts=["HOW NEURONS FIRE"])
        report = _run(fake, tmp)
        check(
            "the report records which style and layout were chosen, and the labels painted",
            (report["style"], report["layout"], report["labels"])
            == ("vector-illustration", ta.SINGLE_SUBJECT, []),
            str({k: report.get(k) for k in ("style", "layout", "labels")}),
        )
        check(
            "and the chosen style reached the image prompt, not only the report",
            "STYLE — vector-illustration" in fake.image_prompts[0],
            fake.image_prompts[0][:200],
        )


def test_generate_thumbnail_art_call_failure_is_retried() -> None:
    """A failed art-direction CALL, not a bad reply — and it used to kill the whole phase.

    Measured on a real cover run: one correction turn came back `content: null` with
    `finish_reason: length`, the OpenRouterError propagated out of the loop, and no cover
    shipped even though three of the four calls that run had already succeeded. It belongs on
    the same retry path as an unusable reply, for the same reason: it has cost no image call.
    """
    print("generate_thumbnail (the art-direction call itself fails)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        boom = orr.OpenRouterError(
            "the completion was truncated by max_tokens before any text was emitted "
            "(finish_reason=length)"
        )
        fake = _Fake(
            transcripts=["HOW NEURONS FIRE"],
            replies=[boom, _full(subject="a myelinated axon", source=_SPINE_SOURCE)],
        )
        report = _run(fake, tmp)
        check(
            "the run survives it and ships on the next turn",
            report["attempts"] == 2 and Path(report["png"]).is_file()
            and report["problems"] == [],
            f"attempts={report['attempts']} problems={report['problems']}",
        )
        check(
            "no image call was spent on the failed turn",
            len(fake.image_prompts) == 1,
            str(len(fake.image_prompts)),
        )
        check(
            "and the correction turn is told to answer with the fields and nothing before them",
            "TH-FORMAT" in fake.claude_prompts[1]
            and "no deliberation before them" in fake.claude_prompts[1],
            fake.claude_prompts[1][-300:],
        )

    # Bounded, and never silent: if EVERY turn fails there is no cover, and that is reported
    # rather than absorbed. Fail-open on a read-only audit, fail-loud on producing nothing.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(transcripts=[], replies=[orr.OpenRouterError("provider down")] * 8)
        with _patched(fake):
            exc = _raised(lambda: asyncio.run(
                ta.generate_thumbnail(_spine(tmp), tmp / "cover.png")))
        check(
            "an outage on every attempt raises rather than pretending a cover exists",
            isinstance(exc, RuntimeError) and "no cover was produced" in str(exc),
            repr(exc),
        )
        check(
            "and it spent no image calls doing so",
            len(fake.image_prompts) == 0 and len(fake.claude_prompts) == ta.MAX_ATTEMPTS,
            f"images={len(fake.image_prompts)} art={len(fake.claude_prompts)}",
        )


def test_generate_thumbnail_non_png_fails_closed() -> None:
    print("generate_thumbnail (a JPEG must not reach the .png key)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = _Fake(transcripts=["HOW NEURONS FIRE"], media_type="image/jpeg")
        with _patched(fake):
            exc = _raised(lambda: asyncio.run(ta.generate_thumbnail(_spine(tmp), tmp / "cover.png")))
        check(
            "it raises rather than shipping a mislabelled cover",
            isinstance(exc, orr.OpenRouterError) and "image/png" in str(exc),
            repr(exc),
        )
        check("nothing is written to the output path", not (tmp / "cover.png").exists())
        check(
            "and it costs ONE image call, not four — the encoder is not retryable (rule 24)",
            len(fake.image_prompts) == 1, f"{len(fake.image_prompts)} calls",
        )


def test_generate_thumbnail_flat_cover_is_retried() -> None:
    """`TH-FLAT` is retryable now, and it was not in the SVG era.

    Then it meant the rasteriser had failed silently, which no prompt could fix. Now it
    means the model returned one flat colour — a bad sample, and the next sample is
    likely fine.

    This case also pins the fallback's TH-TITLE guard, and it is why the guard exists: the
    headline here transcribes PERFECTLY on all four attempts and the residual problem is
    TH-FLAT. Before the guard, exhausting the loop entered the text-free branch anyway,
    spent a fifth image call that could not help (a flat cover repainted without a headline
    is still flat), and overwrote `problems` with "no readable headline after 4 attempts" —
    reporting a defect that never happened while discarding the one the gates measured.
    """
    print("generate_thumbnail (TH-FLAT, and the fallback's guard)")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        flat = _big_cover(G, G)
        fake = _Fake(transcripts=["HOW NEURONS FIRE"] * (ta.MAX_ATTEMPTS + 1), png=flat)
        report = _run(fake, tmp)
        check(
            "a single-colour cover is flagged TH-FLAT and retried to the limit",
            any(p.startswith("TH-FLAT") for p in report["problems"])
            and len(fake.image_prompts) == ta.MAX_ATTEMPTS,
            f"{len(fake.image_prompts)} calls, problems {report['problems']}",
        )
        check(
            "the finding asks for a subject and a light source, which a prompt CAN change",
            any("concrete subject with a light source" in p for p in report["problems"]),
            str(report["problems"]),
        )
        check(
            "the REAL finding survives to the report — no TH-TITLE is invented over it",
            [p.split(":")[0] for p in report["problems"]] == ["TH-FLAT"],
            str(report["problems"]),
        )
        check(
            f"and no fifth image call is spent on a render that cannot fix it "
            f"({len(fake.image_prompts)} calls, {fake.transcribed} transcriptions)",
            len(fake.image_prompts) == ta.MAX_ATTEMPTS == fake.transcribed,
            f"{len(fake.image_prompts)} image, {fake.transcribed} vision",
        )
        check("a cover still ships — TH-FLAT is not fatal", Path(report["png"]).is_file())


if __name__ == "__main__":
    test_palette_contrast_is_computed_not_claimed()
    test_palette_is_assigned_not_chosen()
    test_spec_table_matches_the_code()
    test_load_skill()
    test_vendored_copy_matches_the_installed_one()
    test_spec_ids_match_the_code()
    test_spec_and_gate_agree()
    test_build_prompt()
    test_render_curriculum()
    test_load_brief()
    test_load_brief_against_every_real_spine()
    test_parse_art_direction()
    test_check_source()
    test_citation_sample()
    test_check_marks()
    test_check_headline()
    test_art_rules_point_at_the_artifact()
    test_ground_advisory()
    test_compose_image_prompt()
    test_galleries_are_closed_over_what_is_on_disk()
    test_load_style_and_load_layout()
    test_check_style_and_check_layout()
    test_check_labels()
    test_compose_image_prompt_with_style_and_labels()
    test_account_transcription()
    test_parse_art_direction_galleries()
    test_compose_text_free_prompt()
    test_normalise_text()
    test_lexical_text()
    test_require_png()
    test_parse_image_response()
    test_parse_chat_response()
    test_art_direction_turn_disables_thinking()
    test_book_records_cost_and_tokens()
    test_missing_key_is_named()
    test_resolve_text_model()
    test_no_anthropic_import()
    test_png_decoder()
    test_saturation_floor_is_sited_in_the_measured_gap()
    test_saturation_floor_against_the_real_rejected_corpus()
    test_accent_and_saturation_are_complementary_not_redundant()
    test_check_png_separates_the_two_populations()
    test_check_png_dimension_gates()
    test_check_png_advisories_are_not_returned()
    test_real_cover_fixtures()
    test_bakeoff_originals()
    test_accent_share_is_a_measurement()
    test_luma_is_not_luminance()
    test_parse_critique()
    test_generate_thumbnail_clean_first_attempt()
    test_generate_thumbnail_keeps_failed_attempts()
    test_generate_thumbnail_subject_markings_do_not_cost_the_headline()
    test_generate_thumbnail_marks_group_is_not_judged()
    test_generate_thumbnail_glyph_gate()
    test_generate_thumbnail_critique_is_advisory()
    test_generate_thumbnail_ships_text_free_after_four_failures()
    test_generate_thumbnail_keeps_the_best_when_the_fallback_also_has_text()
    test_generate_thumbnail_transcription_outage_fails_open()
    test_generate_thumbnail_bad_reply_costs_no_image_call()
    test_generate_thumbnail_off_curriculum_source_costs_no_image_call()
    test_generate_thumbnail_marks_and_headline_cost_no_image_call()
    test_generate_thumbnail_gallery_refusals_cost_no_image_call()
    test_generate_thumbnail_art_call_failure_is_retried()
    test_generate_thumbnail_non_png_fails_closed()
    test_generate_thumbnail_flat_cover_is_retried()
    print(f"\n{_PASS} passed, {_FAIL} failed"
          + (f", {_SKIPPED_SECTIONS} section(s) skipped" if _SKIPPED_SECTIONS else ""))
    if _SKIPPED_SECTIONS:
        print(
            f"  ⚠️  {_SKIPPED_SECTIONS} section(s) above did NOT run — the installed skill or\n"
            "      the full-size bake-off originals are absent (both are expected to be,\n"
            "      inside the worker image). The pass count is therefore lower than a local\n"
            "      run's by the cases those sections contain, and the local run is their\n"
            "      only gate."
        )
    raise SystemExit(1 if _FAIL else 0)
