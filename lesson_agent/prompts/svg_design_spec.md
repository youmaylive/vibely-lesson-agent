# SVG Design Spec v1

Every rule here has an ID. When a diagram is rejected you will be told which rule it broke,
by ID, with the measured numbers. Rules marked **(measured)** are checked by a geometric
program that parses your SVG and measures every text and shape box — you cannot talk it out
of a finding, you can only fix the geometry. Rules marked **(advisory)** are judged by a
reviewer.

The measurement is real, so the numbers in this spec are usable: where a rule gives you a
formula, use it before you place anything.

---

## SD-GROUNDING — every fact comes from the lesson (measured against the excerpt by the reviewer)

- Every label, value, identifier, and code fragment MUST appear in the LESSON EXCERPT.
  Do not invent example values, element names, or property values.
- If the excerpt says `20px`, the diagram says `20px` — never a different number.
- If you need a label the excerpt does not provide, use a **generic role name**
  (`property`, `value`, `selector`) rather than inventing a concrete one.
- Do not import examples from your own knowledge of the topic.

A diagram that is beautiful but shows values the learner has never seen in this lesson is
REJECTED. This rule outranks every aesthetic rule below.

---

## SD-TYPE — choose a diagram type, then draw it (advisory)

Do not start drawing boxes. Name the type first, then follow its skeleton. The type is what
determines the shape vocabulary; "use more curves" only produces decoration.

| type | use when | skeleton |
|---|---|---|
| `layered-stack` | one thing sits on top of another | 3–5 full-width bands, bottom = foundation, labels left-aligned inside each band |
| `annotated-cutaway` | internal structure matters | one large central form, 4–6 leader lines to short labels around the edge |
| `timeline-with-bands` | a sequence over time | one horizontal axis with ticks, events as markers on it, translucent bands behind for phases |
| `comparison-columns` | two or three alternatives | parallel columns, a shared row of criteria down the left, same y for comparable cells |
| `cycle` | a repeating loop | 4–6 nodes on a circle, curved arrows between them, centre holds the invariant |
| `decision-tree` | branching on a condition | diamonds for tests, rects for outcomes, edge labels on every branch |
| `part-whole` | composition or proportion | one enclosing outline divided into labelled regions, sized to the real proportions |
| `quantity-plot` | a value changing | two axes with tick labels and units, plotted points, a reference line if the lesson has a threshold |
| `before-after` | a transformation | two states side by side, identical layout, one arrow between them, differences highlighted |
| `anatomy-callout` | naming the parts of a thing | the thing drawn once, large, with 5–8 numbered or lettered callouts |

Draw the *form* of the idea. A `cycle` drawn as five rectangles in a row is the wrong
diagram. Half of previously generated diagrams were 100% rectangles — that is the failure
this rule exists to prevent. → advisory check `SHAPE_MONOTONY` fires when ≥85% of shapes are
one kind.

## SD-STRUCTURE — declare the form, then fill fixed zones (measured)

Diagrams were rejected as "overlapping, not informative, not useful". The cause was not
taste: they were labelled *pictures* with paragraphs beside them, placed at freely chosen
coordinates. Three rules, and the first is checked by the program.

**1. Declare the archetype.** The first line inside `<svg>` is a comment naming the SD-TYPE
you picked. It is stripped before the learner sees it — it exists so the choice is a decision
you made rather than a shape you drifted into.

```xml
<svg viewBox="0 0 1000 700" xmlns="http://www.w3.org/2000/svg" font-family="Arial, sans-serif">
  <!-- archetype: comparison-columns -->
```

A name not in the SD-TYPE table is rejected. When the lesson's subject is an object — a
bathtub, a battery, a pump — you must still pick the *explanatory* form: `before-after` for a
change of state, `comparison-columns` for two regimes, `quantity-plot` for a value over time.
Draw the explanation, not the object.

**2. Place into zones, never at coordinates you chose.** Take these numbers as given.

`viewBox="0 0 1000 700"` — title `y 40-96`, body `y 120-600`, footer `y 620-660`, everything
inside `x 40-960`:

| grid | cell extents |
|---|---|
| 2 columns | `x 60-490`, `x 510-940` |
| 3 columns | `x 60-340`, `x 356-644`, `x 660-940` |
| 4 rows | `y 120-230`, `y 240-350`, `y 360-470`, `y 480-590` |

`viewBox="0 0 900 900"` (radial types) — title `y 40-96`, centre `(450, 500)`, ring radius
`300`, node boxes `170x74` centred on the ring, hub box `260x120` at the centre.

What the grid buys you is that collisions become impossible rather than unlikely, provided:

- Every shape and every label sits **inside one cell**. Nothing straddles a gutter; only a
  connector may cross one.
- **12px inner padding**: text starts at `cell_x1 + 12`, first baseline at `cell_y1 + 28`.
- **Character budget per cell**, already computed with the SD-TEXT-FIT formula so you do not
  have to: at `font-size="15"` a 2-column cell holds **49** characters, a 3-column cell
  **31**, the full width **106**. At `font-size="22"`: **33**, **21**, **72**.
- At most **3 lines** per cell, at 22px line spacing.

**3. Labels, not sentences.** At most **6 words** per `<text>`, and no full stops. A stack of
three or more left-aligned lines at one font size is a paragraph — that belongs in the lesson
body, never in the figure.

Write the **quantity** instead of the sentence. Every diagram carries at least two numbers or
identifiers taken verbatim from the excerpt; they are the reason the figure is worth looking
at rather than reading past:

| instead of | write |
|---|---|
| "The pump moves three sodium ions out and two potassium ions in, so the cell loses one positive charge each cycle." | `Na+ out 3` / `K+ in 2` / `net -1 per cycle` |
| "Without the pump the voltage collapses to zero over several minutes." | `pump off` / `0 mV in ~minutes` |

→ `ARCHETYPE_NOT_DECLARED`, `ARCHETYPE_UNKNOWN` (hard); `PROSE_BLOCK`, `LABEL_TOO_WORDY`
(advisory).

## SD-CANVAS — fill the frame you declared (measured)

- Declare exactly one of: `viewBox="0 0 1000 700"` (landscape — most types) or
  `viewBox="0 0 900 900"` (radial: `cycle`, `part-whole`, `anatomy-callout`).
- Keep every drawn thing inside a **40px inner margin** of that canvas.
- **Fill it.** Spread the drawing edge to edge within the margin and centre it. Content that
  occupies less than 55% of the canvas is floating in empty space.
- Do not enlarge the canvas to make room. If the drawing does not fit, the layout is wrong,
  not the canvas.

→ `CONTENT_OUTSIDE_CANVAS` (hard), `LOW_CANVAS_FILL` / `OFF_CENTER` (advisory).

## SD-TEXT-FIT — compute the width before you write the label (measured)

Text is measured with real Arial advance widths. Use the arithmetic:

> **A label of N characters at font-size F is about `N × 0.55 × F` pixels wide.**
> **A box of width W fits about `W / (0.55 × F)` characters.**

So at `font-size="16"`, a 200px box fits ~22 characters; a 24-character label needs ~211px
plus padding. Size the box from the label, or shorten the label to the box — never guess.

- A box must be **at least 24px wider** than its longest label (12px padding each side).
- For multi-line labels, repeat the **same explicit `x`** on every `<tspan>` and use
  `dy="1.25em"` for each line after the first:
  ```xml
  <text x="300" y="180" text-anchor="middle" font-size="16">
    <tspan x="300">First line</tspan>
    <tspan x="300" dy="1.25em">Second line</tspan>
  </text>
  ```
  Omitting `x` on the second `<tspan>` makes it continue the first line instead of stacking.
- Minimum `font-size` is **12**; use 16 for labels and 22 bold for titles.
- No single line should span more than 60% of the canvas width. Break it.

→ `TEXT_OVERFLOWS_RECT` (hard — a label wider than its own box), `TINY_FONT` / `LONG_LINE`
(advisory).

## SD-ANCHOR — state the anchor on every `<text>` (measured)

Put an explicit `text-anchor="start" | "middle" | "end"` on every `<text>` element (or on a
`<g>` that wraps them), matching the `x` you positioned it at:

- `middle` → `x` is the centre of the box (use for text inside a shape: `x = rectX + width/2`)
- `start` → `x` is the left edge
- `end` → `x` is the right edge

Never rely on the default. Without a stated anchor the checker cannot know where the text
begins, so its horizontal position — and every collision finding about it — is a guess. This
is why the rule is hard despite nothing looking wrong.

→ `MISSING_TEXT_ANCHOR` (hard).

## SD-FONT — declare the typeface once, on the root (measured)

Put `font-family="Arial, sans-serif"` on the root `<svg>` element. Every text width in this
spec — and every measurement the checker makes — is Arial's. If you declare nothing, the
renderer substitutes its own default (a **serif**, in the browser this was tested in), so
every box you sized with the SD-TEXT-FIT arithmetic is the wrong width on screen.

Only `Arial`, `Helvetica`, `Liberation Sans` or plain `sans-serif` are accepted; they share
Arial's advance widths. Do not set a family on individual elements — one declaration on the
root, inherited by everything.

→ `NON_ARIAL_FONT` (hard).

## SD-SPACING — nothing overlaps anything it does not belong to (measured)

- Leave **≥30px** between separate elements.
- A label goes **fully inside** the shape it belongs to, or **≥20px clear** of every shape it
  does not.
- Centre text in a shape with `text-anchor="middle"` and `dominant-baseline="middle"` at the
  shape's exact centre.
- Route arrows **around** labels, not through them.

Deliberate composition is *not* an overlap and is not flagged: a shape fully inside another,
a marker centred on a track, a chip on a translucent band, a label on the background wash,
shapes meeting at a shared edge or corner. You do not need to avoid those.

→ `TEXT_OVERLAP`, `TEXT_SPILL`, `SHAPE_OVERLAP` (hard); `CONNECTOR_CROSSES_TEXT` (advisory).

## SD-MEASURABLE — stay inside what the checker can measure (measured)

An automated checker measures your geometry from **presentation attributes**, not CSS. Work
within that or your diagram ships unverified:

- No `<style>` blocks and no CSS classes for font-size, font-weight, or text-anchor — set
  them as attributes.
- No `<use>`, no `foreignObject`.
- Group with `<g transform="translate(dx,dy)">` **only**. Never `rotate`, `scale`, `matrix`,
  or `skew`.
- `<marker>` for arrowheads is fine. So are `<defs>`, gradients, and the SD-MOTION
  `<animate>` elements — the checker skips all of them.

→ `UNMEASURABLE_SUBTREE` (advisory — it reports how much of your drawing could not be
checked).

## SD-PALETTE — colour carries meaning (advisory)

Use colour by **role**, not decoration. Pick one palette and use it consistently; use at
least 3 distinct fills so the shapes' meanings are distinguishable.

| role | use for |
|---|---|
| `ink` | text, axis lines, outlines |
| `surface` | the background wash and neutral cards |
| `accent-primary` | the subject of the diagram |
| `accent-secondary` | the thing it is compared or connected to |
| `accent-warn` | danger, failure, the thing to avoid |
| `muted` | context, grid lines, superseded states |

Palettes (choose the one that suits the subject; do not mix two):

| name | ink | surface | primary | secondary | warn | muted |
|---|---|---|---|---|---|---|
| clinical | `#1f2933` | `#f8f9fa` | `#4A90D9` | `#50C878` | `#FF6B6B` | `#9aa5b1` |
| slate | `#22303f` | `#f4f6f8` | `#3d6b99` | `#6ba8a9` | `#d9694f` | `#a8b3bd` |
| warm | `#33291f` | `#fdf8f3` | `#e08a3c` | `#7d9a6d` | `#c1453b` | `#b3a394` |
| indigo | `#241f33` | `#f7f6fb` | `#5b5bd6` | `#3fa39b` | `#dd5a6b` | `#a5a2b8` |
| forest | `#1e2b22` | `#f5f9f5` | `#2f7d54` | `#6f9dc4` | `#cf6248` | `#9db0a4` |
| ember | `#2b2226` | `#fbf6f6` | `#b5476b` | `#4c86a8` | `#e07a3f` | `#ab9ba1` |

Text on a filled shape is `#ffffff`; text on `surface` is the palette's `ink`.

→ `PALETTE_MONOTONY` (advisory).

## SD-DEPTH — flat fills look unfinished; use gradients and elevation (measured)

Solid colours read as a placeholder. Every surface that matters gets a **two-stop gradient**;
every card above the page gets a **shadow copy**. Define gradients once in `<defs>`, running
from a lighter tint to the palette colour itself:

```xml
<defs>
  <linearGradient id="gPrimary" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#5b8fc7"/><stop offset="1" stop-color="#3d6b99"/>
  </linearGradient>
  <linearGradient id="gSurface" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#f4f6f8"/>
  </linearGradient>
  <radialGradient id="gSheen" cx="0.5" cy="0.3" r="0.75">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.45"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
  </radialGradient>
</defs>
```

A raised card is **three rects in this order** — shadow, fill, sheen:

```xml
<rect x="80" y="126" width="260" height="120" rx="14" fill="#22303f" opacity="0.10"/>
<rect x="80" y="120" width="260" height="120" rx="14" fill="url(#gPrimary)"/>
<rect x="80" y="120" width="260" height="120" rx="14" fill="url(#gSheen)"/>
```

The shadow is the same shape offset `+6y` in the palette's `ink` at `opacity="0.10"`. There is
no `<filter>` available — `feDropShadow` is stripped before the learner sees it, so this is
the only shadow that survives.

**Gradients go on `fill`, NEVER on `stroke`.** A gradient's ramp is measured across the
element's bounding box, so a `stroke="url(#gPrimary)"` on a **horizontal** line — whose box has
zero height — is degenerate and the line renders **completely invisible**. This was measured in
the browser, not reasoned: a horizontal path stroked with the vertical `gPrimary` above came out
blank while the same path with a flat stroke drew normally. Axes, connectors, plotted curves and
rules all take a flat palette hex:

```xml
<path d="M120 470 L920 470" fill="none" stroke="#3d6b99" stroke-width="5"/>   <!-- correct -->
<path d="M120 470 L920 470" fill="none" stroke="url(#gPrimary)"/>             <!-- INVISIBLE -->
```

Also:

- Vertical gradients only for surfaces, so the light stays consistent.
- Both stops are **one role and a lighter tint of it** — never primary→warn, which means
  nothing.
- `rx="12"`+ on every card. Sharp corners read as unstyled. No shadows on axes or connectors.
- Lay a `url(#gSurface)` rect over the whole canvas first.
- Gradient stops count as your palette, so this satisfies SD-PALETTE rather than fighting it.

→ `GRADIENT_STROKE_INVISIBLE` (hard); `FLAT_FILL_ONLY` (advisory — no gradient fill anywhere on
a diagram of 4+ shapes), `MISSING_XMLNS` (advisory).

## SD-MOTION — animate the build-up, freeze the result (measured)

The diagram may assemble itself in teaching order, using **SMIL** — `<animate>` nested inside
the shape it animates. There is no CSS here: `<style>` and `style=` are stripped, so
`@keyframes` is silently dropped.

**Stage the structure, not the trimmings.** This is the rule that decides whether the diagram
reads as animated at all. Each teaching step's **shape, its label and its connector go inside one
`<g opacity="0">`** — not just the chips and arrows laid on top of a frame that was already
complete. A figure whose title, panels, cards and captions are all on screen at `t=0` looks static
no matter how many small things fade in, and this is measured: **at least half the drawn elements
must sit inside a staged reveal, and that is a hard failure — the diagram is rejected and sent
back.** Only the background wash and the title are exempt.

**Four absolute rules. Breaking the first makes the diagram vanish.**

1. **`fill="freeze"` on every reveal.** Without it SMIL snaps the element back to its start
   value the instant the animation ends — a shape revealed from `opacity="0"` animates in and
   then **disappears permanently**. This is checked and it is a hard failure.
2. **Use `values="0;1"`, never `from="0" to="1"`.** `from` and `to` are removed by the
   sanitiser that runs before rendering; `values` survives.
3. **`begin` is a plain time offset — `"0s"`, `"1.2s"`, `"800ms"`.** Nothing else is
   permitted: no `begin="other.end"`, no `"btn.click"`, no `"indefinite"`. A diagram using
   those is rejected outright.
4. **The whole build finishes within 4 seconds**, and the frozen end state is the complete
   diagram. A learner who scrolls back must see everything without waiting.

Three idioms. Draw-on connector — `pathLength="100"` makes the dash arithmetic exact whatever
the real path length is, so you never compute it:

```xml
<path d="M120 200 C 220 200 240 300 340 300" pathLength="100"
      fill="none" stroke="#3d6b99" stroke-width="3" marker-end="url(#arrow)"
      stroke-dasharray="100" stroke-dashoffset="100">
  <animate attributeName="stroke-dashoffset" values="100;0" dur="0.8s"
           begin="1.2s" fill="freeze"/>
</path>
```

Staggered reveal — one group per teaching step, `begin` increasing by ~0.4s:

```xml
<g opacity="0">
  <animate attributeName="opacity" values="0;1" dur="0.5s" begin="0.8s" fill="freeze"/>
  ... the card and its label ...
</g>
```

**One** ambient loop per diagram, on the single element the lesson is actually about — a
pulsing node, never a moving layout:

```xml
<circle cx="600" cy="300" r="10" fill="url(#gWarn)">
  <animate attributeName="r" values="10;14;10" dur="2.2s" begin="0s"
           repeatCount="indefinite"/>
</circle>
```

Animate only `opacity`, `stroke-dashoffset`, `r`, `cx`, `cy`, `x`, `y`, `width`, `height`,
`transform`, `stop-color`, `offset`. Never animate a value that carries meaning (a bar's
height, a point's `cx` on an axis) — motion is emphasis, not data. And never make motion the
only way to read the diagram: a learner with reduced-motion settings still sees SMIL, so the
frozen state must carry the whole meaning.

→ `REVEAL_WITHOUT_FREEZE`, `STATIC_STRUCTURE` (hard); `NO_BUILD_UP`, `SLOW_REVEAL` (advisory).

## SD-DENSITY — earn the space (advisory)

- Every shape carries a **specific** label drawn from the excerpt. No "Step 1", no unlabelled
  boxes.
- Prefer **8 well-labelled elements over 4 vague ones**. A diagram of four boxes each holding
  one word teaches nothing.
- But if text covers more area than the shapes, you have written a paragraph in a frame
  (SD-STRUCTURE rule 3).
- Add a title at the top (`font-size="22"`, bold) and use `rx="12"` on rectangles (SD-DEPTH).
- An arrow must be **at least 12× its own stroke-width long**. A 30px arrow at
  `stroke-width="3"` is mostly arrowhead and reads as a floating glyph, not a connector.

→ `TEXT_DOMINANCE`, `STUBBY_ARROW` (advisory).

---

## What gets rejected

- Any value or example not in the LESSON EXCERPT (SD-GROUNDING)
- No `<!-- archetype: NAME -->` inside `<svg>`, or a name not in the SD-TYPE table
  (SD-STRUCTURE)
- A label wider than the box drawn around it (SD-TEXT-FIT)
- A `<text>` with no stated `text-anchor` anywhere in its ancestry (SD-ANCHOR)
- A diagram with no `font-family="Arial, sans-serif"` on its root `<svg>` (SD-FONT)
- A gradient on a `stroke` — the element renders invisible (SD-DEPTH)
- Overlapping text, or a label lying across a shape it does not belong to (SD-SPACING)
- Geometry drawn outside the declared canvas (SD-CANVAS)
- A reveal `<animate>` with no `fill="freeze"` — it makes the shape disappear (SD-MOTION)
- A `begin` that is not a plain time offset (SD-MOTION)

## Output

Return ONLY the raw `<svg>...</svg>` — no markdown, no code fences, no explanation.
The root tag carries `xmlns="http://www.w3.org/2000/svg"`, the `viewBox`, and
`font-family="Arial, sans-serif"`.
Valid XML: close every tag, quote every value, and never repeat an attribute on one element.
