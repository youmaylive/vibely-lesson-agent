# Course cover spec — adapting the thumbnail skill to a course

The document above is a **YouTube** thumbnail skill. Everything in it about contrast, colour, type size
and the 120px test applies to a course cover unchanged, and it is the authority on those. This file is
only the delta: how the cover is *produced* here, the two rules that invert for a course, and the exact
values the checker enforces.

Every rule has an ID. When a cover is rejected you are told the IDs, so read the rule with that ID and
change only that. **Rules marked `no gate` are not checked** — they are here because a rule left out of
the brief entirely is a rule nobody follows, and because they are the difference between a cover someone
clicks and one they scroll past.

Three rules are marked **`advisory — vision critique`**. A vision model is shown the finished cover and
asked those three questions, once, *after* the retry loop has ended. So they are observed and reported —
but a `no` never costs you a retry and never blocks the cover. That placement is deliberate: a judge with
unmeasured precision sitting inside a retry loop once flagged 76% of this project's diagrams and silently
replaced the review that mattered. Write to these rules because they decide whether the cover is any
good, not because something will stop you.

**The critique's own precision is poor, and that is measured rather than suspected — which is the reason
the placement above is not merely cautious.** Across the four covers of the 4-Sep artifact run, one
finding was right, two over-reached, and one was a hallucination about something not in the picture:
`recursion`'s `TH-TRUE` correctly said the numbered branches are not a valid tree hierarchy (they are
not — it is a botanical tree with numerals scattered over it); `immune-system`'s `TH-TRUE` complained
that *"the DNA helix … is depicted as a flat ladder-like strip"* and **there is no DNA in that picture**;
`economics`' `TH-STOCK` answered `no` because the cover is a *"generic commodity/product still-life"*,
which is on none of the seven cliches its own question enumerates and is the artifact `TH-STOCK` was
narrowed to permit. So: 1 of 4 useful, and a judge that invents a subject cannot be allowed to spend a
retry. It stays advisory until precision reaches rule 25's bar on ten hand-sampled covers, and until then
read a `no` as a prompt to look at the PNG yourself, never as a finding. `THUMBNAIL_CRITIQUE=0` turns it
off with no rebuild.

## How the cover is produced — an image model paints it

You do **not** draw. You write **art direction** for a text-to-image model (`OPENROUTER_IMAGE_MODEL`,
default `openai/gpt-5.4-image-2`), it returns a PNG, and the PNG is what a student sees.

This is a reversal, and it is recorded rather than quietly swapped: this spec previously said *"You write
an SVG document. Chrome rasterises it to PNG at 3×"*, on the premise that **diffusion cannot spell a
title**. That premise was measured at the pivot and is false — five models, one prompt, one headline, and
**all five spelled `HOW NEURONS FIRE` correctly**. What killed the SVG version was the other end: a
drawing by a language model looks like a drawing by a language model. Seven covers came out as boxes,
lines and a wall of blue-orange, and the fifteen vector rules that policed them are retired at the bottom
of this file.

Three consequences that decide what you can ask for:

- **There is no negative prompt on this endpoint.** Every "do not draw X" only works as a sentence inside
  the prompt. The exclusions that protect the painted text are appended **by code** on every attempt —
  do not restate them, and do not weaken them. The one exclusion you must **not** write yourself is a ban
  on the subject's own markings: see `TH-MARKS`, which exists because that sentence turned a price board
  into a board with no prices on it.
- **You cannot ask for a pixel size**, only a 16:9 aspect ratio and a coarse resolution tier. So the
  dimension check is a ratio plus a floor, never an equality (`TH-ASPECT`, `TH-SIZE`).
- **You are writing words, not pixels.** On a correction turn you cannot edit the picture — only the
  words that produce it. "Move the headline left" is not an edit; it is a different request.

There is still **no face**. The skill's Face Expression Psychology section is dropped, and the reason
changed with the medium: an image model paints faces perfectly well, so this is now a decision rather
than a limitation — a synthesised face on a course cover asserts an instructor who does not exist, and
that section's table is tuned for reaction-video CTR, not a course catalogue.

---

## `TH-GROUND` — the subject comes from THIS course's curriculum  · **hard on the citation, advisory on the render**

**Pick the TOPIC out of the COURSE block, say in writing which entry you picked, then let `TH-SUBJECT`
choose the object.** That two-step split is a correction, not a flourish — see below. The reply carries
three machine-read lines above the headline:

```
SUBJECT: a crate of oranges at a night market, a chalked price slate wedged against it
SOURCE: Market equilibrium and price signals
MARKS: the chalked figures on the slate, and the stencilled crate numbers
```

**This rule picks the topic; it does not pick the object.** Written as *"pick one of those concepts and
draw THAT"*, it produced covers nobody could recognise, because the entries in a curriculum are abstract
nouns — `Instantiation`, `Market equilibrium and price determination` — and an abstract noun has no
appearance. The model then invented a prop to stand for it: a split-flap board, a brass vault door.
Measured against the four covers that work, the fix is to go **down one level** from the cited concept to
the physical thing a student of it handles, which is `TH-SUBJECT`.

`SOURCE` must appear in the course's module titles or `key_concepts`, compared case- and
whitespace-insensitively and matched as a substring — so citing `law of demand` out of the concept
`Demand: law of demand, demand curves, determinants of demand` is correct and preferred over quoting the
whole clause. **This is checked in code before a single image is paid for**, so an invented citation costs
one cheap text turn and nothing else. `SUBJECT` is not required to appear verbatim in the art direction;
the picture may describe the same thing in other words.

Why this is hard and not advice. The COURSE block lists every module and every concept the course teaches —
for a typical course that is ~66 named things, *"Production Possibility Frontier"*, *"Refractory period"*,
*"Terms of trade"*. A cover drawn from the *field* instead of from the *course* is the measured failure:
the first two live covers for a course teaching PPF and comparative advantage were **two crossed crystals,
then two crossed ropes**, and the third was **cracked stone with fire inside**. All three spelled the
headline perfectly, passed every pixel gate, and depict nothing that course teaches. Nothing was going to
catch that, because `TH-SUBJECT` below asks only whether the thing is *concrete*.

**The second half — did the model paint what you asked for — is advisory, and stays advisory.** The vision
critique already names, blind, the one thing it can see in the finished cover; the run compares that name
against `SUBJECT`/`SOURCE` in code, for free, and prints `TH-GROUND` when they share no significant word.
The case it was written from: the art direction correctly asked for *"a macrophage caught
mid-phagocytosis, pseudopods curling around a rod-shaped bacterium"* and the model painted **a gold blob
swallowing a white pill**. It is a word-overlap comparison, so a cover that draws exactly the right thing
and gets described in other words lands here too — which is why it only prints, and why promoting it would
need precision measured on ten hand-sampled covers.

**Read the curriculum for weight, not for wording.** `students get stuck on` and `taught with the
analogies` tell you which concept the course thinks is hard enough to need help — that is a signal about
*which* concept to draw. They are not descriptions of a picture: the analogies are metaphors, which
`TH-SUBJECT` forbids painting, and the stuck-on lines are usually a developer at a screen, which
`TH-STOCK` forbids. Take the concept out of them and leave the scenery behind.

## `TH-SUBJECT` — the artifact a practitioner handles  · `advisory — vision critique`

**Ask what a practitioner of the thing you cited physically handles, trades, reads, or builds with. Draw
that object, close, filling the frame, lit.** `TH-GROUND` above chose the topic; this rule turns the topic
into a thing with an appearance.

This is the rule the *"I am not able to recognise it"* complaint rewrote, and the evidence is this
project's own output rather than an argument:

| cited topic | what was drawn | outcome |
|---|---|---|
| supply and demand | a crate of oranges at a night market | **works** |
| compound interest | a stack of gold coins | **works** |
| reading music | an open score on a wooden stand | **works** |
| the Silk Road | a rope-bound bale of gold silk, scrolls, glass vials | **works** |
| market equilibrium | an invented split-flap price board | unrecognisable |
| instantiation | an invented brass vault door | unrecognisable |
| comparative advantage | cracked stone towers with fire inside | unrecognisable |
| a course's subject, generally | two crossed crystals / two crossed ropes | unrecognisable |

Every cover that works is **the field's obvious artifact, drawn plainly**. Every cover that fails is a prop
invented to stand for an abstraction. So when the cited concept is abstract — and most curriculum entries
are — do not invent a symbol for it. Go down one level: `Instantiation` → *the object a Python programmer
handles*; `Market equilibrium` → *the thing a trader physically touches*. Being obvious is not the defect
here; being invented is.

Not a metaphor for learning — no lightbulbs, no ladders, no glowing brains, no rocket ships, no jigsaw
pieces, no staircases. Not an abstraction as the subject ("data", "growth", "innovation").

**A diagram IS allowed when the diagram is the artifact.** A printed score, a chart on paper, a plotted
curve on graph paper, a schematic pinned to a drafting table — those are physical objects a practitioner
reads, and one of the four covers that work is exactly this. What is banned is a diagram drawn as the
picture's *own structure*: boxes and arrows floating on a background with nothing depicted holding them.
This is a narrowing of the previous rule, which banned diagrams outright and thereby barred the
recognisable answer for every subject whose artifact is a drawing.

**The measured failure that remains is the abstract collision.** Two of the first two real covers for
*Economics for Developers* were two crossed objects meeting at a spark — crystals, then ropes — and the
vision critique named both unprompted: *"a generic crossing/tension motif that could illustrate almost any
topic."* Both spelled the headline perfectly and passed every pixel gate, which is exactly why this rule
cannot be enforced by a statistic. The shape to avoid: **two abstract things arranged so their
*relationship* is the picture** — crossing, colliding, balancing, facing off, meeting in a flash of light.
It is the diagram failure wearing paint. If the sentence describing your subject would still make sense
for a course on a completely different topic, the subject is not concrete enough.

**The medium and the light are no longer yours to invent here — see `TH-STYLE`.** This paragraph used to
read *"Say the medium and the light. 'Rich painterly digital illustration, dramatic rim lighting, deep
shadow, shallow depth of field' gets a painting."* That one sentence, repeated in the art rules, **was the
entire style system**, and it is why every cover of every course in every subject came back as the same oil
painting. It is replaced by a named style from a gallery, whose reference file is appended by code. The
half of it that was right survives inside `TH-STYLE`: saying *nothing* about the medium gets a photograph,
which is the register `TH-STOCK` forbids.

**Fill the frame, and leave one calmer region for the headline.** The image model has no layout engine,
so the space for text exists only if you compose the picture around it. Say where the subject sits and
where the calm area is, in the second paragraph. The appended clauses ask for an illustration that
reaches all four edges; your composition has to make that true of something other than empty ground.

**A second mass is allowed only if you can name it in one word.** The old spec learned this the hard way
on drawings and it transfers: three of four covers in one batch drew two separated masses, and the one
that worked drew two nameable things whose pairing *is* the course's claim.

## `TH-TRUE` — the picture must be true, not merely plausible  · `advisory — vision critique`

The picture carries most of the meaning, so a wrong picture is a wrong cover. A cover painted beautifully
that states something false is worse than one with no subject at all, because the people most likely to
spot the error are the people the course is for.

**Labels raise the stakes on this rule rather than relieving them.** This paragraph opened *"there are no
labels on this cover"* until `TH-LABELS` existed. Now that a few words can be painted on, a mislabelled
part is a *worse* defect than an unlabelled wrong one: it is a false statement in the course's own
vocabulary, and it is checked by nobody — `check_labels` proves a label came out of the curriculum, never
that it is attached to the right part of the picture.

Check the direction of every curve and the sign of every axis before you ask for it. A bond potential
energy curve has its stable state at a **minimum**; drawing it as a peak is the failure meant here, and
this generator has shipped it. Demand slopes down, supply slopes up, entropy increases, an overfit curve
passes *through* every point. Both ends of a curve are part of its claim — decide what each end does
(wall, asymptote, plateau) and say so — and count the turning points you intend against the ones you
asked for.

**The cheapest way to get this right is `TH-SUBJECT`'s preference for a concrete object.** A benzene ring
has no asymptote to get wrong. Every `TH-TRUE` failure this generator has shipped was a curve. If you are
not certain of the shape of a thing, choose a different subject you are certain of — **one part you are
sure of beats a richer one you are half sure of.**

## `TH-STOCK` — no office photograph, no logo  · `advisory — vision critique`

Stock-photo blandness is a diffusion model's native register, so it has to be refused explicitly and in
positive terms. **What this bans, and all it bans:** a person at a laptop, a flat lay of a desk with a
coffee cup and a notebook, hands typing, a logo or a mascot, two products with sparks between them,
motivational lens flare, a generic icon standing in for the field (a gear for engineering).

**What it no longer bans — and this narrowing is the correction.** It used to read *"not a beaker but the
molecule in module 3; not a chart but the pattern the course is about"*, i.e. a ban on the field's own
obvious subject matter, which I had read out of the skill's "generic stock photo feel → gets skipped" row.
The corpus says that reading was wrong: every cover on disk that works draws the field's obvious artifact
(see `TH-SUBJECT`'s table), and the covers that fail are the ones that avoided it. Combined with
`TH-GROUND`'s abstract citation and the old blanket ban on diagrams, this rule was one of three whose
intersection left the model no recognisable answer at all — for *market equilibrium* the image every
economics student knows was forbidden twice over.

"Stock" here means **the generic office photograph**, not a well-known object. A crate of oranges for
supply and demand is obvious and correct.

## `TH-MARKS` — the subject keeps its own markings  · **hard, checked before any image is generated**

**Name the markings the object carries in real life on the `MARKS:` line, and then ask for them in the
prompt.** Or write the single word `none`, plus which unmarked object you mean.

This exists because the pipeline was doing the opposite. Every image prompt has a clause appended by code
to protect the transcription gate, and it used to end *"no letters hidden in the artwork"* — a ban on all
text anywhere. Once `TH-GROUND` pushed the subject toward things whose meaning **is** their markings, that
clause stripped exactly the markings that made them legible. The failing prompt asked, in its own words,
for a split-flap price board *"with no digits, letters, or symbols printed on any flap"* and *"no other
text, numbers, or marks anywhere on the board"*: **a price board with no prices.** What shipped was
meaningless furniture, and that is the *"garbage data"* complaint, mechanically.

So the appended clause is now two sentences — one banning **added** text (subtitle, caption, watermark,
logo, signature, date, page numbers, UI chrome, lorem ipsum) and one **asking for** the subject's own
markings. `MARKS:` is the half you write, and it is checked in code: at least one substantive word of what
you name must appear in the art direction, before any image is paid for. A permission nothing checks is a
rule that lives in prose, which is how this shipped in the first place.

**Ask for the markings crisply, and prefer figures and notation over words — a preference, not a
constraint.** Digits, notation, numerals, glyphs, engraving, syntax colours in code: all wanted, all
legible. `music-theory.png` is the existence proof from before this rule existed: it asked for *"the inked
treble clef, noteheads and stems"* positively, and it is one of the four covers that work.

The preference exists for one reason only, and it is cosmetic: an image model asked for running prose on
an object invents letters and paints visible gibberish — `immune-system-single.png` painted a vial reading
`FUSMIEEISNATEMET`. That is recorded in `report["marks_seen"]` and **not gated**, because gating it is
what the next paragraph is about.

**This rule used to end *"ask for it too small and blurred to read as words"*, and that sentence is
deleted.** It was there because `TH-TITLE` judged every legible word in the frame, so a stencil on a crate
was a hard failure. On 4 Sep 2026 it was measured doing real damage on **4 of 5 live covers**: the
`economics` cover's split-flap price boards read `GRAD` and `GRADO` instead of prices — a price board whose
prices are deliberately unreadable, which is this rule's own opening complaint reintroduced from the other
end. Worse, `recursion` and `python-oop` **shipped with no headline at all**: the correction turn repeated
the instruction, the model obeyed it on the largest lettering in the frame, and four attempts went by. So
`TH-TITLE` now judges added text only (see its three steps) and the markings are simply not its business.

Do **not** write your own exclusion of markings. "No digits on the flaps", "no symbols on the dial" is the
sentence that caused this.

**Ask for FEW markings — two or three, on one or two surfaces. Quantity, not blur, is what separates a
real object from gibberish, and that is measured.** The two covers of the third live run (4 Sep 2026)
differ in nothing else. `economics` named *"the chalked price and quantity figures on the slate, and the
stencilled crate numbers"* and got **3**: `3.20/kg`, `B-27`, `LOT 04` — every one correct, every one a
reason the picture reads as a market. `python-oop` named *"the printed variable name … and etched
dimension-style tick marks along the drawer edges"* and got **20**: `STANETATG`, `PYITINBER`, `ANPYSTIRRY`,
`11:60`, `1.334"`, on a cover whose headline was perfect. So legibility does **not** degrade gradually with
quantity — a model asked for a few marks paints them right, and a model asked to annotate every surface
invents. `blueprint` provokes it hardest, because its own `Visual Elements` list asks for dimension lines
and measurement indicators on a picture that already has a subject; the bound is stated here rather than by
editing the vendored style file, which stays verbatim.

Two things this is not. It is not the blur mandate returning: the marks are still asked for **crisply**,
and the change is how *many*, not how legible. And it is not a gate — a `marks_seen` token count could be
one, but calibrating a threshold on four covers is exactly the trap that once flagged 76% of this project's
SVG diagrams, and the vision critique already reports the defect in words (*"TH-TRUE: the dimension labels
and card text are garbled nonsense"*). It stays a preference until precision is measured on ten covers.

## `TH-STYLE` — name a visual register from the gallery  · **hard on membership, checked before any image is generated**

**Write one name from the STYLE GALLERY on the `STYLE:` line, copied character for character.** The
gallery, a content-signal → style table, and the whole list of names are in the prompt above. There is no
free-text option and no default: an unrecognised name is refused before any image is bought, and the error
hands you the list back.

You do **not** describe the style in your own words — `compose_image_prompt` appends the chosen style's
vendored reference file (from the `cover-image` skill, Apache 2.0) to the image prompt on every attempt.
Assembled in code for the same reason the text exclusions are: a retry rewrites your art direction, so
anything you hold in your own prose erodes across four attempts and anything code appends does not.

**Why this exists, measured.** One sentence of prose — see the note now standing in `TH-SUBJECT` — was the
entire style system, and eleven covers on disk look related because of it. So the register is now a choice
from nine, with the subject's own signals telling you which.

**The nine, and why only nine.** The upstream gallery has twenty. Eleven are declined, and the criterion
is a threshold rather than taste: `TH-PALETTE` assigns one of five **strongly saturated** grounds, and
`TH-SATURATION` is a hard 0.10 mean-saturation floor. So the question asked of each style was *does its
identity survive being drawn on a saturated ground* — and for a style that is a way of **making marks**
(halftone, chalk, pixels, dimension lines) the answer is yes and often canonical, while for a style whose
identity **is** its pale light there is nothing left of it once the ground is overridden.

| declined | reason |
|---|---|
| `minimal` `elegant` `watercolor` `nature` `vintage` | pale by design; cannot reach the saturation floor — the six pale covers in `output/thumbnails/rejected-original/` measure **0.03-0.06**, so they fail it even after it was re-sited to 0.10. `elegant` is upstream's default — the register these covers were rejected for |
| `fantasy-animation` `playful` `warm` `flat-doodle` | the identity is a light ground (`#E8F4FC`, `#FFFBEB`, `#FFFAF0`, `#FFFFFF`); pastel over a saturated ground is the muddy mass `TH-ACCENT` exists to catch |
| `notion` | grey dashboard chrome — low chroma, and `TH-STOCK` bans the UI register by name |
| `intuition-machine` | its defining feature is bilingual Chinese labels, which `TH-TITLE` would read back as unaccounted text |

A per-style saturation floor instead of declining them would be a threshold with **zero covers behind it**,
which is the trap that once flagged 76% of this project's SVG diagrams. `vintage` is the one worth
re-testing later: `silk-road.png` is the best cover on disk at 49.5% accent share and is vintage *in feel* —
but painterly-vintage, not this file's aged-paper scheme.

**Two sections of every style file are dropped, and one of them is not obvious.** `Color Palette` and
`Background` go because `TH-PALETTE` owns colour and two palettes in one prompt is a contradiction the
image model resolves however it likes. `Best For` goes because selection has already happened by the time
the file loads. And **`Typography` goes** — that one was in the keep list until all nine were read: six of
the nine mandate a typeface contradicting the appended text clause's *"heavy condensed sans-serif"*, and
four demand exactly the letterforms `TH-GLYPH` fires on (`retro` "vintage-style hand lettering",
`sketch-notes` "bold hand-written marker font", `chalkboard` "hand-drawn chalk lettering … imperfect
baseline", `pixel-art` "pixelated bitmap font, chunky blocky letterforms"). A hand-lettered headline is the
hardest thing for the transcription gate to read back, which is already why the skill's own base prompt is
declined wholesale. **So the style owns the marks and the shapes; the letterforms stay with the clause the
gate reads back.** The loader **raises** if a kept heading disappears upstream, rather than shipping a cover
whose style rules are silently absent.

**`dark-atmospheric` is the one to watch, and for the opposite reason to the pale styles.** Its identity is
partly its near-black ground, and `TH-PALETTE` has no dark row — so it arrives with its glow, its fog and
its backlit silhouettes but not its darkness. It has been chosen 5 times across four live runs and its
covers are the ones that sit closest to the saturation floor, so it is recorded rather than tuned: 10
hand-sampled covers is the bar, and `accent_share` has separated the muddy ones from the fine ones every
time so far.

**One style was kept and then declined on live covers, and that is worth reading before proposing another
one.** `blueprint` passed every test this list applies — a blueprint on a saturated ground is still
recognisably a blueprint, and `recursion`'s early cover was a dark blueprint that worked. Then five covers
chose it and **all five came back with garbled pseudo-measurements** stamped over the subject: 20 invented
tokens on one (`STANETATG`, `PYITINBER`, `11:60`), 14 on another (`1414.4`, `2841.1AM`), and the critique
named it unprompted twice. Once it went further — *"generic blueprint-style translucent boxes with arrows
and gibberish labels, not a clearly identifiable object"* — which is the original complaint about this
project's covers, reproduced by a style added to fix it. The mechanism is in the style file itself: its
`Visual Elements` list asks for dimension lines and measurement indicators, so every blueprint cover is a
subject **plus an annotation layer**, and the annotation layer is where an image model invents letters.
Bounding the mark count in the prompt was tried first and did not hold, because the style asks for the
annotations independently of what the art direction asks for.

Two consequences. `editorial-infographic` ("callouts and numbered parts") and `sketch-notes` ("arrows and
annotations") have the same shape and are **kept**, because no live cover has chosen either and declining
them now would be reasoning where the blueprint decision was measuring — if one is chosen and the critique
reports garbled marks, that is the same finding. And the axis this list was originally curated on — does the
style survive a saturated ground — is necessary and **not sufficient**: colour was the only axis with covers
behind it when the list was written.

## `TH-LAYOUT` — name an information structure  · **hard on membership, checked before any image is generated**

**Write one name from the LAYOUT GALLERY on the `LAYOUT:` line.** Same contract as `TH-STYLE`: exact
membership, refused before any image is paid for, reference file appended by code (from the `infographic`
skill, Apache 2.0). Layout answers a different question from style — style is *how it is drawn*, layout is
*how the information is arranged*.

**`single-subject` is a first-class answer and it is the default.** It means today's behaviour exactly: one
object, close, filling the frame, lit, no structure and no reference file injected. It is not the lesser
choice — **all four covers on disk that work are single subjects**, and reaching for structure on a course
whose subject is one artifact would repeat the change that made these covers worse rather than better.
Choose a structured layout when the *curriculum itself* has that shape: modules that run in order →
`linear-progression`; one central concept with satellites → `hub-spoke`; kinds of a thing →
`tree-branching`; an anatomy with named parts → `structural-breakdown`. That shape is readable from the
COURSE block above, which prints `builds:` and `teaches:` for every module.

**A structured layout is still a PICTURE.** Every rule above still holds: `TH-SUBJECT`'s concrete artifact,
`TH-STOCK`'s ban on the UI register, and above all the ban on *boxes and arrows floating on a background
with nothing depicted holding them*. `structural-breakdown` of a real object cut away is a picture;
`structural-breakdown` of three rounded rectangles is the drawing failure this pipeline spent seven covers
learning to avoid.

**Ten of twenty upstream layouts are declined**, and every reason is one of two: a text-dense grid blows
`MAX_LABELS = 6`, or the shape itself is an abstraction `TH-SUBJECT` already bans.

| declined | reason |
|---|---|
| `comparison-matrix` `periodic-table` | one label per cell, dozens of cells — far past the label cap |
| `dashboard` | metric tiles are numbers and captions, and `TH-STOCK` bans the UI register |
| `comic-strip` `story-mountain` | narrative panels need sentences, not 3-word labels; and a curriculum is not a plot |
| `funnel` `bridge` | conversion / problem-solution marketing shapes; "gap-crossing" is an abstraction, not an artifact |
| `isometric-map` | spatial relationships between places, and a curriculum has no geography |
| `venn-diagram` `jigsaw` | two overlapping abstractions **is** `TH-SUBJECT`'s named failure — "two abstract things arranged so their relationship is the picture" — and `jigsaw` is banned there by name |

Each layout file's `Recommended Pairings` section is dropped, and that one is a trap rather than noise:
every one of them recommends `infographic`'s **own** 17 styles (`craft-handmade`, `aged-academia`, …), none
of which is in the STYLE GALLERY. Injected, it would recommend a style `TH-STYLE` then refuses. The 17 are
declined wholesale for a second reason too: the two skills' style galleries overlap **without agreeing** —
`chalkboard.md` is byte-identical across them while `pixel-art.md` differs — and two files with the same
name and different contents is exactly the divergence to refuse up front. **One gallery owns each
dimension**: styles from `cover-image`, layouts from `infographic`.

---

## `TH-WORDS` — at most 6 words in the headline  · **hard, checked before any image is generated**

The headline is the only *sentence* on the cover — the one thing a student reads first, and the only text
at all unless you declare labels under `TH-LABELS`. **At most 6 words**, and the cap is enforced on the
`HEADLINE:` line before a single image call is made, so breaking it costs one cheap retry.

**You may and should shorten the course title.** "Model Fitting and Regression Diagnostics in Practice"
becomes "Model Fitting". An abbreviated headline that reads at 120px beats a complete one that does not,
and the full title appears everywhere else on the page. Short headlines are also the ones image models
spell correctly — and the spelling is checked, letter for letter.

**Shortening is not renaming: the headline must share a significant word with the course title**, and that
is checked in code alongside the citation, before any image is paid for. The measured failure is
*Economics for Developers* shipping a cover that reads `SUPPLY MEETS DEMAND` — short, legible, spelled
right, and it does not say which course the card is for. Identifying the course is the cover's first job.
The check folds plurals and matches prefixes, so `STAR` for *The Life Cycle of Stars* and `COMPOUNDING`
for *Compound Interest* both pass; it fails open loudly on a title with no word long enough to carry
subject meaning.

## `TH-TITLE` — the headline is painted, and read back  · **hard, 4 attempts**

The skill says a thumbnail should not duplicate the video title and that text should be cut if it cannot
be made large. **Both invert here.** On YouTube the player renders the title beside the thumbnail; a
course card carries no such guarantee, so the cover must say what the course is. The title is not
decoration on this image — it is the image's job.

The gate: after each render, a vision model (`OPENROUTER_VISION_MODEL`, default
`anthropic/claude-sonnet-5`) reads the words in the PNG back, sorted into **two groups** —

- **`TEXT:`** the lettering laid *over* the picture: the headline, and any caption, subtitle, tagline,
  watermark, signature, credit line or logo wordmark.
- **`MARKS:`** the writing that belongs to a depicted object: numbers or codes stamped, etched, printed,
  chalked or engraved onto the thing being painted. Dial figures, part numbers, a price board, the label on
  a bottle, the spine of a book.

**Only the `TEXT:` group is judged.** The `MARKS:` group is printed and recorded in `report["marks_seen"]`
and never produces a finding — see `TH-MARKS` for the four-of-five-covers measurement that put it there.
If the reply carries neither header, the whole of it is treated as `TEXT:`, which is the strict behaviour
this gate had before the split: an unparseable read-back must cost an attempt, never pass a cover whose
headline was never checked.

The `TEXT:` group is then compared against the headline **plus the labels you declared** in three steps:

1. The headline must appear as a **contiguous run of tokens** inside the transcription — letter for letter,
   in order, after normalisation. This is the only relaxation of the headline's old strictness: it was
   equality against the whole image, it is now a substring, and every letter of it is still checked.
2. Every remaining token must be **accounted for by a declared label** — matched with
   `difflib.SequenceMatcher` at ratio ≥ **0.75** against any word of any label. An unaccounted token is a
   hard `TH-TITLE` failure. This is the check that still catches `MASTERCLASS 2026`, a watermark, a
   signature, and the letter-shaped noise measured below.
3. A token that is accounted-for **but misspelled** — `RECURSSION` against the label `recursion`, ratio
   0.947 — is an advisory `TH-LABELS`. Printed, recorded, never retried.

Normalisation absorbs case, whitespace, line breaks and smart quotes — measured against real replies, where
three of four models wrapped the headline as `HOW\nNEURONS\nFIRE`. **It does not absorb letters.** A
misspelled headline fails; so does a caption or a watermark, which is why the exclusions are appended by
code and not left to a generation turn to remember.

**With no labels declared, this verdict is identical to the old equality check** — a test pins that, because
the four covers that work all took this path.

**The asymmetry is the whole design: the headline is hard, the labels are advisory.** A wobbly label is a
blemish; a wobbly headline is a dead card. Six labels have six times one label's chance of a garbled glyph,
and the cost of hard-failing on the subject's own text is already on disk: the `recursion` cover burned all
four attempts and **shipped with no headline at all**, which is worse than any defect this gate was written
to catch. `TH-GLYPH` needs no change either — its question asks only for *"the largest headline text"*, so
labels never reach it.

**The 0.75 threshold is a guess, and it is recorded as one.** It could not be calibrated before the fact:
no labelled cover existed to sample. So it is set in the safe direction, which is deliberately the generous
one — too generous ships a misspelt label (advisory, cosmetic), too strict burns four attempts and can ship
a headline-less card. It stays on the advisory side of that trade until precision is measured on ten
hand-sampled covers.

**Normalisation also drops any token with no letter in it, and that is `TH-MARKS`' cost paid here.** The
two rules were enforcing opposite contracts, and this gate won by destroying the cover: measured on the
`recursion` cover, the art direction asked for brass linked-list tags "each stamped with a numeral and a
pointer-hook arrow" — precisely what `TH-MARKS` exists to permit and what makes a linked list legible —
the transcription came back `RECURSION AND DATA STRUCTURES 12 7 19 20`, equality failed, four attempts
burned, and because the digits belong to the *subject* the text-free fallback could not be text-free
either. What shipped had **no headline at all**, which is worse than every defect this gate was built to
catch. So: strict about letters, blind to letterless marks. Two consequences, both real:

- An **undeclared** word still fails — `MASTERCLASS 2026` keeps its letters. That is the check that matters,
  and the line it draws is now *added text versus the object's own markings*, sorted by the vision model
  rather than by a rule about digits. The one thing declaring a label changes is *which* words are allowed
  through step 2; it does not open the door to a caption.
- A digit **in the headline** can no longer be enforced: `PYTHON 3 CLASSES` painted as `PYTHON CLASSES`
  passes. There is no way to be strict about a headline digit while permitting the subject's digits — the
  transcript does not say where in the frame a glyph sat. Accepted knowingly, and pinned in
  `test_lexical_text`.

**That letterless tolerance was necessary and it was not sufficient, and the second half of the fix is the
two-group read-back above.** Real object markings carry letters: on the styled run of 4 Sep 2026 the
`python-oop` cover painted its headline *and all three declared labels* correctly and was rejected over
`19068G XHPVE 501S NAW V7` — a stamped brass casting — while `economics` was rejected over `GRADO X17`,
`immune-system` over `HR GIOT`, and `recursion` over `Ø09 Ø11 Ø38`. Four of five covers, and two of the
five ended with no headline. A rule about *digits* cannot see this; the difference between a part number
and a watermark is not in the characters, it is in whether the writing belongs to the depicted thing. That
question is answerable by a model looking at the pixels and by nothing else, which is where it now lives.

**Both halves were then confirmed on the re-run of that same cover, which is better evidence than the
unit tests because the failure it had to survive was not one I wrote.** Attempt 2 transcribed
`RECURSION AND TREES NEN STN NUIT SOT STLE SOC NALY SEAURSION` — the model had smeared letter-shaped
noise across the blueprint — and it **failed**, correctly, because those tokens carry letters. Attempt 3
transcribed the headline plus 60 bare numerals on the tree's nodes and **passed**. One run, one rejection
of real letter garbage and one acceptance of the subject's own digits: the line this normaliser draws is
the line that was wanted, and the cover ships with its title on it.

- The headline must appear **verbatim inside your PROMPT**. This is structural, not stylistic: the model
  paints only what the prompt asks for, so a prompt that never mentions the headline produces no text and
  the gate then fails four times on a picture nobody asked to carry any.
- On a failure you are told what the picture actually reads. Fix it in the *words*: make the headline
  shorter, ask for it larger, or put it somewhere emptier.
- After 4 attempts the run ships the **best text-free image** — one extra render with a positive "this
  picture contains no writing of any kind" clause, confirmed text-free by the same vision pass — and
  records `TH-TITLE` as an unresolved problem. That is a loud fail-open, not a silence: a cover is
  cosmetic, and failing a course generation over one is the wrong trade.
  - That render is your art direction **with every sentence naming the headline removed**, not your art
    direction plus the clause. The two would contradict each other by construction, since the bullet
    above *requires* you to name the headline: asking for "the words X in the upper-left" and "no
    writing of any kind" in one prompt lets the model resolve the conflict either way, and measured, it
    kept the words. So write the headline in **its own sentence** — a picture whose every sentence
    mentions it cannot be pruned, and the run says so with `TH-TITLE_PRUNE_FAILED`.
  - The fallback is taken **only when the outstanding problem is the text**. If a pixel gate is still
    failing, repainting without a headline cannot fix it, so no extra call is made and the real finding
    is what gets reported.
- If the vision call itself errors, the run prints `TH-TITLE_GATE_SKIPPED` and accepts the attempt. A
  read-only audit fails open **loudly** (rule 21); it must never pass quietly.

**What this gate does NOT check, measured: the headline's weight and size.** The prompt asks for *"a single
bold heavy sans-serif line … large enough to read easily at a small size"*, and `python-oop` from the 4-Sep
artifact run came back with a **thin, small serif** headline — legible at full size, gone at card size —
and passed cleanly, because a transcription proves the letters are *right*, not that they are *big*. That
is a model compliance failure with no gate behind it, and it is the SVG era's nine title-geometry rules —
listed in the retired table at the end of this file, so they are not repeated as IDs here — being genuinely
missed rather than merely retired: they measured coordinates that a painted cover does not have. `TH-CONTRAST` cannot stand in — it reads 1.0:1 on
crisp painted type. Deliberately not fixed: a weight-and-size gate needs a new pixel measurement
(a stroke-width or cap-height estimate over the text band), and inventing a threshold for one without
sampling ten covers first is rule 25's exact trap. So it is recorded here, and until someone measures it,
**look at the headline** on any cover that matters.

## `TH-LABELS` — the few words on the picture come out of the curriculum  · **hard on the citation, advisory on the render**

**Write the words to be painted on the picture on the `LABELS:` line, separated by `|` — or the single word
`none`.** At most **6**, at most **3 words** each. Every one is checked, before any image is paid for,
against the same corpus `TH-GROUND` checks `SOURCE:` against: the course's module titles and
`key_concepts`, normalised, matched as a substring. `none` plus an explanation is still `none`.

```
LAYOUT: structural-breakdown
LABELS: axon | myelin sheath | synapse
```

**This is the concrete answer to "not course based".** Before it, one `SOURCE:` citation was checked and
then nothing of it was visible in the picture. Now the words a student actually reads on the cover are
curriculum text, verified verbatim before a cent is spent.

Three checks and each one is a cheap refusal rather than a wasted image:

- **In the curriculum.** An invented label is refused with the corpus quoted back. Substring, not equality,
  for the reason `TH-GROUND` already gives: real `key_concepts` are compound strings, so `law of demand` out
  of `Demand: law of demand, demand curves, determinants of demand` is the honest citation.
- **Substantive.** A label has to carry at least one word of ≥4 letters that is not a stopword, so `of the`
  and `and` are not labels.
- **In your own art direction.** Every declared label must appear in the `PROMPT` text. This is the same
  structural check the headline gets, for the same reason inverted: a label the picture was never asked to
  carry is a word the gate has been told to *expect*, and it costs the same four attempts.

**Writing `none` is a legitimate and often correct answer.** With `LAYOUT: single-subject` it is the
behaviour of every cover on disk that works. Declare labels when the layout has parts worth naming, not
because the field exists.

**On the render side this rule is advisory, and `TH-TITLE` step 3 explains why** — a misspelt label is
printed and recorded, never retried. What is *not* checked at all, and should be read as a known gap: that
a label is attached to the **right part** of the picture. `check_labels` proves a word came from the
curriculum; nothing proves `myelin sheath` points at the myelin sheath. That is `TH-TRUE`'s territory, it is
advisory too, and it is the reason a labelled cover is worth looking at before it ships.

**An empty corpus fails open, loudly.** A course whose spine carries no module titles or concepts is a thin
*input*, not a bad cover — the same decision `check_source` already makes.

## `TH-GLYPH` — the same headline, spelled out  · **hard, second question, only on a pass**

`TH-TITLE` above asks a vision model to read **words**, and a vision model asked for words answers with
the word it expects. A shipped cover was painted `CLASSÆS` — an `Æ` ligature where `ES` belonged — and it
transcribed clean as `MASTER PYTHON CLASSES`. The one gate the whole painted-title design rests on had
autocompleted the defect away.

So a second question asks for the same headline **one character at a time, separated by spaces**, with
explicit instructions not to correct, complete, or guess the intended word. The reply is compared on
letters and digits alone — spacing and punctuation dropped from both sides, since word boundaries are
what `TH-TITLE` already checks, and nothing folds one letter into another (`CLASSÆS` must not equal
`CLASSES`).

It runs **only when `TH-TITLE` passed**, and it is ~$0.005. On the fail path the finding already exists
and a second opinion would buy nothing. A `TH-GLYPH` failure is not fixable by moving the text: the
correction asks for a plain heavy condensed sans-serif with no ligatures and no decorative letterforms.
It counts as a text failure for the text-free fallback, alongside `TH-TITLE`. The vision call erroring
prints `TH-GLYPH_GATE_SKIPPED` and accepts the attempt — same fail-open-loudly reasoning as above.

## `TH-PALETTE` — the row is assigned to this course  · `no gate on the pixels`

Three hexes, named in the prompt as colours. **The row is not yours to choose** — it is derived from the
course title by a SHA-256 hash, so it is the same on every regenerate and different across a catalogue.

| row | ground | accent | headline | neutral-on-ground | accent-on-ground |
|---|---|---|---|---|---|
| `blue-orange` | `#0B4FD8` | `#FF7A1A` | `#FFFFFF` | 6.72:1 | 2.58:1 |
| `green-white` | `#00753F` | `#111111` | `#FFFFFF` | 5.81:1 | 3.25:1 |
| `yellow-black` | `#FFD400` | `#111111` | `#111111` | 13.19:1 | 13.19:1 |
| `purple-yellow` | `#6A2CC4` | `#FFD400` | `#FFFFFF` | 7.58:1 | 5.30:1 |
| `red-white` | `#E01B24` | `#111111` | `#FFFFFF` | 4.83:1 | 3.91:1 |

- **ground** is the dominant field of the picture; **accent** is the subject and the light on it;
  **headline** is the colour of the painted words. **The last two are not interchangeable.** Every row's
  headline hex clears WCAG AA on its own ground, computed by `contrast()` and asserted per row in the test
  suite. An earlier version of this table had two columns the wrong way round on three rows, which put
  `yellow-black`'s type at white-on-yellow — **1.43:1**, illegible — and it shipped for weeks. Name the
  headline hex in the prompt; put the words in nothing else.
- `yellow-black` is deliberately two colours: white is unusable anywhere on a yellow ground.
- The accent is a **subject** colour and is deliberately not held to 4.5:1 — blue-orange's orange-on-blue
  is 2.58:1 and reads plainly at 120px, checked by looking.
- Saturate hard, and use **no fourth colour family**.

**Why this is ungated, stated rather than papered over.** In the SVG era the palette was enforced by
scanning hexes in the source. A raster has no hexes, and the pixel-side proxy was measured and rejected:
asked for indigo (hue family 8), all four bake-off models painted the neighbouring **blue** (family 7)
dominant at 31.8–68.6%, with family 8 under 4%. A bin-exact gate rejects all four good covers, and ±1 bin
is a threshold fitted to n=4. So this is art direction that the transcription gate confirms is
*readable* without confirming it is the requested colour.

**Why the row is assigned rather than chosen.** **6 of the 7 covers generated while the palette was a free
choice came back `blue-orange`**, and a catalogue of near-identical blue cards is the "boring" complaint
one level above a single cover — invisible to every gate here, because this agent only ever sees one
course. Removed by construction instead. The cost is real and accepted: the row no longer matches the
subject. The old table's "pick this for" column (blue for science, green for finance…) is retired with it.

The skill's sixth pair, **White + Dark, is not available.** A near-white ground measures around 0.05 mean
saturation against the 0.10 floor, so it cannot satisfy `TH-SATURATION`, and it is precisely the pale look
these covers were rejected for. Recorded so its absence reads as a decision. (The margin here narrowed
from 7x to 2x when the floor was re-sited — still a real gap, and re-measured rather than inherited.)

---

## What is measured on the PNG

The pixel reader is stdlib — IHDR, zlib, PNG unfiltering — and it never knew Chrome made the bytes it was
written for. Verified at the pivot rather than assumed: **all four bake-off PNGs, from three vendors,
decode readably**, which is what makes the 37-cover SVG-era corpus a legitimate comparison population for
the thresholds below.

| id | measured | threshold | on failure |
|---|---|---|---|
| `TH-SATURATION` | mean HSV saturation over the canvas | **≥ 0.10**, advisory to 0.35 | **hard** — retried with a finding |
| `TH-ASPECT` | width / height against 16:9 | **±2%** | **hard** — but not fixable in the prompt; change the model |
| `TH-SIZE` | pixel dimensions | **≥ 1200×630** | **hard** — raise the resolution tier or change the model |
| `TH-FLAT` | the whole cover is one flat colour | — | **hard** — nothing was painted; retried |
| `TH-ACCENT` | share of pixels both bright *and* saturated | 2% | *advisory* — see below |
| `TH-BYTES` | PNG file size | 4 MB | *advisory* — printed for an operator |
| `TH-CONTRAST` | WCAG ratio, ground vs the most distant rendered band | 4.5:1 | *advisory* |
| `TH-HUES` | distinct hue families, greys excluded | — | *reported only* |
| squint | 120px downscale, luminance spread | — | *reported only* |

Measured values on the four painted covers, for calibration: saturation **0.459–0.910** (rejected SVG
covers ran 0.030–0.059), 3–5 hue families, 1.61–5.56 MB, dimensions 1536×864 to 2752×1536.

**Three of these were hard gates in the SVG era and were demoted on measurement, not on taste.**
`TH-CONTRAST` (4.5:1), `TH-HUES` (≤3) and `TH-BYTES` (2 MB) **never fired once on 37 real covers** — not
even on the six that were rejected by eye, which scored 14.2–14.3:1. Each of them fires on the painted
covers that *work*: 3 of 4 exceed 2 MB, 3 of 4 carry more than 3 hue families, and a painted headline's
anti-aliased pixels smear across dozens of luminance bins so no band clears the share floor and a
perfectly legible cover reads 1.5:1. Keeping them would have made the new medium unshippable on evidence
the old medium never generated. `TH-CONTRAST` is also the *weaker* claim now: a transcription that must
match letter for letter is a stronger test of legibility than a ratio on a band of pixels.

**`TH-ACCENT` exists because `TH-SATURATION` cannot see a muddy cover, and that is a measurement.** Bright
*and* saturated on the same pixel (`luminance > 0.45` and `saturation > 0.45`) — the "single warm pool of
light against a cool dark surround" every working cover describes. Eleven covers on disk:

| accent % | mean sat | mean lum | cover | |
|---|---|---|---|---|
| **49.5** | 0.65 | 0.47 | `silk-road` | works |
| 14.3 | 0.48 | 0.44 | `music-theory` | works |
| 8.8 | 0.67 | 0.28 | `compound-interest` | works |
| 4.4 | 0.45 | 0.23 | `supply-and-demand` | works |
| 4.0 | 0.39 | 0.31 | `after/python-oop` | unrecognisable |
| 3.8 | 0.49 | 0.26 | `before/python-oop` | unrecognisable |
| 0.7 | 0.55 | 0.26 | `before/economics` | unrecognisable |
| **0.3** | 0.43 | 0.29 | `after/economics` | worst |

Read the `mean sat` column: **it does not separate these at all** — the worst cover (0.43) scores *above* a
good one (0.45), and `before/economics` at 0.55 beats two of the three that work. Mean luminance is no
better. So a near-black subject on a dark field was always going to clear the saturation floor, and the
usual cause is the palette applied backwards: the subject painted in the **ground** colour instead of the
accent.

**The same table is why the floor itself moved from 0.35 to 0.10** — read one row further than it was
originally read. If mean saturation cannot separate good covers from bad ones, then a *hard* floor sited
inside the good population is all cost and no benefit, and that is what 0.35 became once dark-ground styles
(`chalkboard`, `dark-atmospheric`) entered the gallery. Re-measured over 57 covers with one instrument:
the pale population it was written to reject is **0.03-0.06**, painted covers run **0.13-0.84**, and the
SVG-era covers this whole effort replaces are the *most* saturated files on disk at **0.78-0.92** — the
single cover named as the clearest example of the founding complaint measures **0.87**. Two forced
`chalkboard` covers at 0.13 and 0.22 were good pictures and 0.35 rejected both — and the retry it triggered
was unsatisfiable, since a chalkboard's ground is most of the canvas and neutral by definition, so "be more
saturated" can only be answered by changing style. 0.10 sits in the 0.06→0.13 gap. The 0.10-0.35 band is
kept as an advisory so the information survives the re-siting.

**Advisory, and its limit is stated here rather than found later: it separates *muddy* from *not muddy*,
not *recognisable* from *unrecognisable*.** Both python-oop covers clear the 2% floor and both are
unrecognisable — what is wrong with them is the subject, which no pixel statistic can reach. It stays
advisory until precision is measured on ten hand-sampled covers; promoting a judge with unmeasured
precision into a retry loop is what once flagged 76% of this project's diagrams and silently replaced the
review that mattered.

Only findings a correction turn can act on are retried (rule 24). "Your cover reads as grey, saturate it"
can change the pixels; "your PNG is 4.6 MB" cannot — there is no phrasing that makes a diffusion model
emit fewer bytes and there is no Pillow here to recompress with. Those go to the log, whose reader is an
operator who *can* act by changing the model or the tier.

If the PNG is an encoding the reader does not claim (16-bit, palette, interlaced), the run prints
`PIXEL_CHECKS_SKIPPED` and names the gate that did not run. Fail-open, loudly — and more reachable than
it used to be, because the bytes now come from a third party rather than from Chrome.

---

## Output

`TH-FORMAT` — the reply format is stated at the end of this prompt and it is **machine-read**. These things
make a reply unusable, and every one of them costs a cheap retry with **no image call**: a missing
`SUBJECT:`, `SOURCE:`, `MARKS:`, `STYLE:`, `LAYOUT:`, `LABELS:`, `HEADLINE:` or `PROMPT:` marker; a headline
over the word cap; a headline that does not appear verbatim inside the prompt; a headline sharing no word
with the course title (`TH-WORDS`); a `SOURCE:` that is not in this course's curriculum (`TH-GROUND`);
`MARKS:` naming markings the prompt never asks for (`TH-MARKS`); a `STYLE:` or `LAYOUT:` name that is not in
the gallery character for character (`TH-STYLE`, `TH-LAYOUT`); and a label that is not in the curriculum, is
only stopwords, is over the cap, or is never mentioned in the prompt (`TH-LABELS`). Write prose in `PROMPT` —
no bullets, no markdown, no `key: value` lines, no code fence.

Every one of those checks is on this side of the spend, deliberately. An image call is the expensive thing
in this loop, so any verdict that *can* be computed from the reply alone belongs before it.

---

## Retired rules — what the SVG era enforced and why it is gone

Recorded rather than deleted, per the project's own rule: *a rule dropped from a prompt is a regression no
test will catch.* If any of these re-appears as a defect on a painted cover, this table is where to start.

| retired id | what it enforced | why it cannot survive |
|---|---|---|
| `TH-CANVAS` | the exact `<svg>` root, 640×360 authoring units | there is no document to open; the model returns pixels |
| `TH-FONT` | `font-family="Arial, sans-serif"` | no font is chosen and none can be measured; every width in the old checker was an Arial advance |
| `TH-ANCHOR` | `text-anchor` on every `<text>` | there are no `<text>` elements |
| `TH-MARGIN` | no text within 24px of an edge | needs the title's coordinates; a raster has none. Handled as composition, unchecked |
| `TH-OPAQUE` | no `opacity` below 1 anywhere | an attribute rule with no attributes. Its purpose — no pale washes — is now held by `TH-SATURATION` on the pixels |
| `TH-TYPE-SIZE` | every `<text>` the same `font-size` | no font sizes exist. `TH-WORDS` plus one headline is what remains |
| `TH-LINES` | 1–3 lines, `font-size × 1.15` apart | the model chooses the line breaks; the transcription normaliser absorbs them |
| `TH-TYPE-FLOOR` | no text under 30 units — deleted eyebrows, kickers, axis labels, legends | replaced by the appended exclusions, which forbid *all* text but the headline, and by the transcription gate that fails on any extra word |
| `TH-OVERLAP` | no two text bounding boxes intersect | one headline, no boxes |
| `TH-DENSITY` | 15–40 drawing elements, under 12 fails | a painted picture has no elements to count. This rule existed because the drawings were empty; paint does not have that failure mode |
| `TH-CLEAR` | nothing drawn across the type, measured by a second render with `<text>` removed | needs the vector document twice. The surviving half — compose a calmer region for the headline — is `TH-TITLE`'s precondition, and legibility is now tested by reading the words back |
| `TH-GROUND-BASE` | the base rect must carry `data-ground="1"` | `data-ground` was scaffolding for `TH-CLEAR`'s second render |
| `TH-STACK` | every `data-ground` element before every subject element | same; there is no document order |
| `TH-PLATE` | a backdrop paint may only be the ground or its `shade` | there is no plate, and the `shade`/`deep` columns are gone (below) |
| `TH-SAFE-ZONE` | no text in the bottom 128×56 corners, where a card overlays badges | needs the title's coordinates. **This one is a real loss** — a card still overlays duration and progress there, and nothing now stops the model painting the headline into a corner. Asked for in composition, unchecked |

Two more constraints that were not IDs and are retired with them, so they are not searched for later:

- **The `shade` and `deep` depth-tone columns** (two extra hexes per palette row) existed so a *drawing*
  could show depth in flat planes without opacity. An image model paints light. They are gone from the
  table, and with them the measured rules that governed them: `deep` runs 1.15:1 to 1.86:1 against its own
  ground, so it could not carry a silhouette, and it fell under the 4.5:1 floor on two rows, so it could
  not sit under type.
- **"Span 440 of 640 units across"** — a bounding-box target for a drawn subject, already advisory because
  it scored 2-in-3 precision against the 90% bar. "Fill the frame" is the surviving half, in `TH-SUBJECT`.
- **"Say the medium and the light: rich painterly digital illustration, dramatic rim lighting, deep
  shadow"** — the single sentence that *was* this project's whole style system, in this file and in the art
  rules both. Replaced by `TH-STYLE`. It is listed here because it is the rule most likely to be
  reintroduced by someone who reads one cover and thinks the model needs a nudge about the medium: it does
  not, it needs a *different* medium per course, and one sentence hardcoding one medium is why eleven covers
  looked related. The half of it that was true survives in `TH-STYLE`.

Two things dropped from the **vendored** files, recorded here for the same reason:

- **Every style file's `Typography` section**, and it was the one that looked most useful. Six of the nine
  kept styles mandate a typeface contradicting the appended *"heavy condensed sans-serif"* clause, and four
  demand hand-lettered or bitmap letterforms — the exact thing `TH-GLYPH` fires on and the transcription
  gate reads back worst. The reasoning is in `TH-STYLE`. If a cover ever comes back in a typeface nobody
  asked for, this is the section to suspect being re-added.
- **Every layout file's `Recommended Pairings` section**, which recommends `infographic`'s own 17 styles —
  none of them in the STYLE GALLERY, so it would recommend a style `TH-STYLE` then refuses. Also in
  `TH-LAYOUT`.
