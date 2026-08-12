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
- `<marker>` for arrowheads is fine.

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

## SD-DENSITY — earn the space (advisory)

- Every shape carries a **specific** label drawn from the excerpt. No "Step 1", no unlabelled
  boxes.
- Prefer **8 well-labelled elements over 4 vague ones**. A diagram of four boxes each holding
  one word teaches nothing.
- But do not turn the diagram into prose: if text covers more area than the shapes, you have
  written a paragraph in a frame. Move the words into the lesson and let the drawing show the
  structure.
- Add a title at the top (`font-size="22"`, bold) and use `rx="8"` on rectangles.

→ `TEXT_DOMINANCE` (advisory).

---

## What gets rejected

- Any value or example not in the LESSON EXCERPT (SD-GROUNDING)
- A label wider than the box drawn around it (SD-TEXT-FIT)
- A `<text>` with no stated `text-anchor` anywhere in its ancestry (SD-ANCHOR)
- A diagram with no `font-family="Arial, sans-serif"` on its root `<svg>` (SD-FONT)
- Overlapping text, or a label lying across a shape it does not belong to (SD-SPACING)
- Geometry drawn outside the declared canvas (SD-CANVAS)

## Output

Return ONLY the raw `<svg>...</svg>` — no markdown, no code fences, no explanation.
Valid XML: close every tag, quote every value, and never repeat an attribute on one element.
