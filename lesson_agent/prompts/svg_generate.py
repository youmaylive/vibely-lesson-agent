"""
Prompt for SVG diagram generation.

The design rules themselves live in `prompts/svg_design_spec.md`, loaded from disk
via `config.SVG_DESIGN_SPEC`, exactly as the MLAI format guide is loaded by
`prompts/system.py`. This module only assembles the request around them.

That split is the point of the framework: the spec is versioned, every rule in it
carries an ID, and every rule that can be measured is measured by
`svg_geometry.py`, which cites the same IDs back in its findings. Rules written
into a prompt and never checked do not survive — the old inline "keep labels <= 20
characters" was violated 208 times across 150 generated diagrams.

Spec size is a running cost, not free prose (rule 32's fourth lesson): the whole
file is re-sent on every generation attempt, up to 4 per diagram. Measured
26 Aug 2026 after SD-DEPTH and SD-MOTION landed: **15,304 chars / ~3,826 tokens**,
up from 10,258 / ~2,542. That is **+1,284** against a +900 ceiling I set myself and
then accepted, because the overage was measured rather than argued: 4 diagrams x 4
attempts x 1,284 tokens is ~20.5k input tokens, **$0.06 per lesson** and ~$3 across
a 50-lesson course that already costs ~$64. Trimming the two cookbooks below this
is a false economy — every idiom in them is copy-pasted into real output, and the
alternative to a worked example is a diagram the sanitiser silently blanks.
"""

import hashlib

from config import SVG_DESIGN_SPEC

# Palette names in the same order as the SD-PALETTE table in the spec. A concept
# maps to one deterministically, so a lesson's diagrams are mutually consistent
# across separate generation calls while the corpus as a whole stops being one
# colour scheme — 80 of 150 archived diagrams used only the 7 hexes the old prompt
# hardcoded, because the hexes were *in* the prompt.
PALETTES = ("clinical", "slate", "warm", "indigo", "forest", "ember")


def choose_palette(concept: str) -> str:
    """Pick a palette for a concept — stable across runs and processes.

    `hash()` is salted per interpreter, so it would give a lesson's four diagrams
    four different palettes when they are generated in separate worker processes.
    """
    digest = hashlib.sha256(concept.strip().lower().encode("utf-8")).digest()
    return PALETTES[digest[0] % len(PALETTES)]


def build_svg_generation_prompt(
    concept: str,
    context: str,
    lesson_excerpt: str = "",
    audience: str = "learners",
    feedback: str | None = None,
) -> str:
    """Build the prompt that asks Claude to generate an educational SVG.

    `lesson_excerpt` is the verbatim lesson text surrounding the diagram (the section
    it sits after, including its code blocks). Without it the model invents example
    values that contradict the lesson — a real observed failure was a diagram drawing
    `font-size: 24px` for a lesson that teaches `20px`.
    """
    excerpt_block = ""
    if lesson_excerpt.strip():
        excerpt_block = f"""
## LESSON EXCERPT — THE SOURCE OF TRUTH

This is the actual lesson text the diagram sits inside. The diagram must illustrate
THIS text, using THESE exact examples:

```
{lesson_excerpt.strip()}
```
"""

    spec = SVG_DESIGN_SPEC.read_text(encoding="utf-8")
    palette = choose_palette(concept)

    base = f"""Generate an educational SVG diagram for this concept.

**Concept:** {concept}
**Context:** {context}
**Audience:** {audience}
**Palette to use:** `{palette}` (see the SD-PALETTE table — use this row, not another)
{excerpt_block}
Follow the design spec below. It is not advice: a program measures every text and
shape box in your output against the rules marked (measured), and a diagram that
breaks one is sent back to you with the rule ID and the measured numbers.

Before you place anything, decide two things:
1. **Which SD-TYPE** this concept is. Write the drawing that type calls for.
2. **How wide each label is**, using the SD-TEXT-FIT arithmetic. Size the boxes to
   the labels you actually have.

{spec}
"""

    if feedback:
        base += f"""

## ⚠️ PREVIOUS ATTEMPT FEEDBACK (fix these issues):
{feedback}

Generate an IMPROVED version that addresses all the feedback above.
"""

    return base


def build_svg_review_prompt(
    svg_content: str,
    concept: str,
    context: str,
    lesson_excerpt: str = "",
    craft_notes: str = "",
) -> str:
    """Build the prompt that asks Claude to review/judge a generated SVG.

    GROUNDING is a hard gate, not just another averaged dimension: a diagram that looks
    polished but shows values absent from the lesson used to score 8/10 and ship.

    `craft_notes` are the advisory findings from `svg_geometry.craft_findings` —
    measured facts about fill, shape vocabulary and text balance that the judge
    scores under CRAFT and DENSITY. Those two dimensions exist because nothing was
    judging visual craft at all: the geometric tool only knew "boxes overlap", and
    this prompt used to explicitly tell the reviewer *not* to look at layout.
    """
    excerpt_block = ""
    grounding_dim = ""
    grounding_rule = ""
    grounding_field = ""
    craft_block = ""
    if craft_notes.strip():
        craft_block = (
            "\n**Measured findings from the linter** (facts, not opinions — weigh them "
            "under CRAFT and DENSITY):\n" + craft_notes.strip() + "\n"
        )
    if lesson_excerpt.strip():
        excerpt_block = f"""
**The LESSON EXCERPT the diagram must be faithful to:**
```
{lesson_excerpt.strip()}
```
"""
        grounding_dim = (
            "- **Grounding** (1-10): Does EVERY concrete label, value, identifier and code\n"
            "  fragment in the SVG appear in the LESSON EXCERPT? Go through them one at a time.\n"
            "  Any invented value (e.g. the SVG shows `24px` but the excerpt says `20px`), invented\n"
            "  element name, or example the learner has never seen scores 3 or below.\n"
            "  Generic role words (`property`, `value`, `selector`) are always acceptable.\n"
        )
        grounding_rule = (
            "\n**HARD RULE: if Grounding < 7, VERDICT is FAIL** no matter how high the average is.\n"
            "List every ungrounded item under ISSUES, quoting the SVG text and what the excerpt\n"
            "actually says.\n"
        )
        grounding_field = "GROUNDING: [score]\n"

    return f"""Review this SVG diagram for educational quality.

**Concept it should teach:** {concept}
**Lesson context:** {context}
{excerpt_block}
**The SVG:**
```xml
{svg_content}
```

A geometric linter has already measured every text and shape box in this diagram
exactly. Treat its findings as ground truth and do **not** re-derive coordinates or
guess at pixel positions. Your job on layout is the part it cannot measure: does the
*arrangement* carry meaning?
{craft_block}
Score it 1-10 on each dimension:
- **Relevance** (1-10): Does it specifically illustrate THIS concept (not something generic)?
- **Clarity** (1-10): Can a learner understand it without additional explanation?
- **Labels** (1-10): Are elements properly labeled with concept-specific, correct terms?
- **Accuracy** (1-10): Is the information correct and not misleading? Does it faithfully represent the concept?
  **Check every label against the geometry it points at, in that direction.** No program can
  do this — the drawing is well-formed either way — and it is the defect that has survived
  most often here: a curve labelled "collapses to zero" that descends *away* from the zero
  tick toward -70; an axis whose values increase downward while the caption says a value
  rises; an arrow labelled "out" pointing in. For each labelled quantity, read the axis or
  tick it is measured against and confirm the mark moves the way the words say. A single
  inversion makes the figure teach the opposite of the lesson: cap Accuracy at 3.
- **Craft** (1-10): Does this read as a designed figure or as a default flowchart? Is the
  shape vocabulary suited to the idea, rather than rounded rectangles by reflex?
  **1-3 = uniform rects and arrows only. 8-10 = the form of the drawing itself explains
  the concept.** Be strict: most diagrams land at 4-6, and saying so is useful.
- **Density** (1-10): Information per square pixel. Four boxes each holding one word scores
  3. Penalise emptiness AND clutter. A dense, well-labelled figure scores high; a paragraph
  of prose in a frame does not.
- **Polish** (1-10): Does this look like a designed figure from a good textbook, or like
  default output? Judge tonal depth (gradient-filled surfaces and offset shadows vs flat
  colour), type hierarchy (a clear title, labels and captions at distinct sizes), rounded
  corners, and consistent alignment. **1-3 = every fill is flat, one text size throughout.
  8-10 = you would put this on a slide unedited.** Flat solid fills alone cap this at 4.
{grounding_dim}
**Overall score** = average of the scores above (round to nearest integer).
{grounding_rule}
If overall score < 7, list exactly what's wrong and how to fix it — including layout, when
the problem is what the arrangement means rather than where the pixels are.

Respond in this exact format:
RELEVANCE: [score]
CLARITY: [score]
LABELS: [score]
ACCURACY: [score]
CRAFT: [score]
DENSITY: [score]
POLISH: [score]
{grounding_field}OVERALL: [score]
VERDICT: [PASS or FAIL]
ISSUES: [comma-separated list of issues, or "none"]
"""
