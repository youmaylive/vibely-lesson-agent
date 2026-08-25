"""
User prompt for the initial lesson generation step.
"""

from pathlib import Path


def build_generation_prompt(
    lesson_spec_path: str,
    curriculum_path: str,
    output_file: Path,
    lesson_id: str,
    game_section: str = "",
    budget_section: str = "",
) -> str:
    """Build the user prompt that instructs the agent to generate an MLAI file.

    `game_section` is the per-lesson game half, built by
    `games.build_game_prompt_section` from this lesson's spec. It carries the full
    authoring specs for the few game types that fit this lesson's content; the
    catalog and the cross-game rules live in the system prompt instead, because they
    are identical for every lesson and belong in the cached prefix.

    Defaults to `""` — a lesson with no fitting game, or a run where the generated
    guide is missing, costs zero prompt tokens here and generates without a game.

    `budget_section` is the per-lesson length budget, built by
    `budget.build_budget_section` from the `duration:` in this lesson's spec
    frontmatter. It also defaults to `""`: a spec with no frontmatter (every spec in
    `test_curriculum/` is like this) generates against the qualitative rules below
    alone, rather than failing.

    Why this parameter exists at all: measured across the 89 lessons of one real
    planner run, the specs carry a median of 13 `content_outline` bullets and the
    written lessons carry a median of 13 `<Section>` blocks — close to 1:1. Not one of
    63 sampled sections exceeded 300 words, so the length is not prose bloat, it is
    topic count, and topic count is the only thing a budget can fix. See
    `budget.py`'s docstring for the full measurement.
    """
    return f"""Generate an MLAI lesson from the specification.

**Lesson spec file**: {lesson_spec_path}
**Curriculum context**: {curriculum_path}
**Output file path**: {output_file}

Steps:
1. Read the lesson spec: {lesson_spec_path}
2. Read the curriculum for context: {curriculum_path}
3. Generate a complete, engaging .mlai lesson file (HUMAN voice — see system prompt)
4. Write it to: {output_file}

## ⚡ WRITING STYLE REMINDER (read before generating):

Remember: you're writing for humans who get bored easily. The #1 complaint about AI-generated lessons is "sounds like ChatGPT." Beat that by:
- **First sentence = hook.** A question, a surprising stat, a "what if" — NOT "In this lesson..."
- **Be specific.** "Python's GIL releases every 5ms" > "Python has threading limitations"
- **Sound like YOU have an opinion.** "This is the part most tutorials get wrong..." is engaging. "This concept is important" is not.

### ❌ BAD opening (AI-ish):
"In this lesson, we will explore the fundamentals of recursion. Recursion is a powerful programming technique that plays a crucial role in computer science."

### ✅ GOOD opening (human):
"Here's a weird trick: write a function that calls itself, and somehow it solves problems that would take hundreds of lines of loops. That's recursion — and once it clicks, you'll wonder how you ever coded without it."

### ❌ BAD explanation:
"It is important to note that hash tables provide O(1) average-case lookup time. Furthermore, they leverage a hash function to map keys to array indices."

### ✅ GOOD explanation:
"Hash tables are fast. Stupidly fast. While a sorted list needs to check ~20 items to find something in a million entries (binary search), a hash table gets there in one shot. How? It cheats — it converts your key into an array index directly."

Now generate the lesson with THIS voice:


## CRITICAL: Document Structure Rules

You MUST follow this exact structure pattern:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Lesson>
  <Meta>
    <Id>{lesson_id}</Id>
    <Title>...</Title>
    <Version>1</Version>
    <Tags><Tag>...</Tag></Tags>
  </Meta>

  <Section type="concept">
    <H1>Lesson Title</H1>
    <Body>Introduction...</Body>
  </Section>

  <Section type="concept">
    <H2>First Topic</H2>
    <Body>Explanation...</Body>
    <Code lang="python">example()</Code>
  </Section>

  <Mermaid>
flowchart LR
  A["Input"] --> B["Process"]
  B --> C{{"Decision"}}
  C -->|"Yes"| D["Output"]
  C -->|"No"| E["Retry"]
  </Mermaid>

  <FlashCard id="fc-1">
    <Front>Key term?</Front>
    <Back>Definition.</Back>
  </FlashCard>

  <Svg>
    <!-- markup returned by generate_svg(concept=..., context=...,
         lesson_excerpt=<the Section text you just wrote>) — pasted verbatim -->
  </Svg>

  <Section type="example">
    <H3>Worked Example</H3>
    <Body>...</Body>
    <Code lang="python">...</Code>
  </Section>

  <Svg>
    <!-- second generate_svg result — lesson_excerpt = the Worked Example above,
         including its <Code> block -->
  </Svg>

  <Mermaid>
sequenceDiagram
  Client->>Server: Request
  Server-->>Client: Response
  </Mermaid>

  <SingleSelect id="q1">
    <Prompt>Question?</Prompt>
    <Options>
      <Option correct="true">Right</Option>
      <Option>Wrong</Option>
    </Options>
  </SingleSelect>

  <Svg>
    <!-- third generate_svg result -->
  </Svg>

  <Game type="TYPE_FROM_THE_CATALOG">
{{ "...": "the fields that type's spec lists, and nothing else" }}
  </Game>

  <Section type="concept">
    <H2>Summary</H2>
    <Body>Recap...</Body>
  </Section>
</Lesson>
```

## ABSOLUTE RULES (DO NOT VIOLATE):

1. **Teaching content (H1, H2, H3, Body, Code) MUST be wrapped in `<Section type="...">`**
   - NEVER place H1, H2, H3, Body, or Code directly under <Lesson>
   - They MUST always be inside a <Section> tag
   - Section types: `concept`, `code`, `example`, `tip`

2. **FlashCards go DIRECTLY under <Lesson>** — NOT inside a Section
   - Place FlashCards between Sections, after the concept they reinforce

3. **Assessment components go DIRECTLY under <Lesson>** — NOT inside a Section
   - SingleSelect, MultiSelect, SortQuiz, MatchPairs, FillBlanks, Subjective
   - Place them after the teaching sections, before the summary

4. **A `<Game>` block, if one fits, goes DIRECTLY under <Lesson>** — NOT inside a Section
   - `<Game>` inside a `<Section>` is `INVALID_CHILD` and the lesson will not ship
   - Place it near the end, after the concept has been taught — it is reinforcement
   - At most ONE per lesson, and none at all is a valid choice

5. **Document flow**: Meta → Teaching Sections → FlashCards → More Sections → Assessments → Game → Summary Section

{budget_section}
## Content Requirements:

- Proper <Meta> block with lesson ID "{lesson_id}" and appropriate title/tags
- Sections that each make ONE point (use types: concept, example, code, tip)
- Markdown formatting in Body text (**bold**, *italic*, `code`, lists)
- LaTeX math expressions where appropriate ($inline$ and $$display$$)
- FlashCards for the key terms, placed between sections
- A mix of assessment types — **chosen because they fit what this lesson teaches, not
  one of every type.** A MatchPairs on a topic with nothing to pair, or a SortQuiz on
  something with no natural order, teaches nothing and costs the learner a minute.
- All assessment IDs must be unique
- Exactly ONE `<Game>` block, chosen from the candidate specs at the end of this prompt —
  unless none of them genuinely fits what this lesson teaches, in which case omit it. A
  forced game asks the student to practise something the game shape cannot test, which is
  worse than no game.
- A final summary Section wrapping up key points — ONE, at the end. Not a recap per
  section.

## 🎨 VISUAL REQUIREMENTS (MANDATORY — see the counts in the LENGTH BUDGET above):

You MUST include visuals to keep learners engaged. Use a MIX of Mermaid + SVG:

### Mermaid (for flows/processes/relationships):
- Just write Mermaid diagram code directly — auto-renders
- Use for: flowcharts, sequence diagrams, timelines, state machines, comparisons
- **Double-quote every node and edge label** (`A["Text"]`, `-->|"Yes"|`), use `&lt;br/&gt;` for line
  breaks, and never write numeric entities like `&#10;` or `&#40;`. Diagrams are parsed by the real
  Mermaid parser before your lesson is accepted — see the Mermaid rules in your instructions.

### SVG diagrams — call the `generate_svg` tool (for custom labeled diagrams):

Do NOT write `<Svg concept="..." />` placeholders, and do NOT hand-write `<svg>` markup.
Call the **`generate_svg`** tool, then paste what it returns.

Call it with THREE arguments:
- `concept` — what to diagram, SPECIFIC, including the exact terms to label
- `context` — one sentence on what this part of the lesson is doing
- `lesson_excerpt` — **the actual lesson text you just wrote for this part**, including
  its code blocks, copied verbatim (roughly the preceding Section)

`lesson_excerpt` is the important one. The diagram generator can only see what you pass
it. Leave it out and it invents its own example values — a real lesson taught
`font-size: 20px` and got a diagram showing `24px`, because the generator never saw the
lesson. Pass the real text and every label in the diagram comes from YOUR lesson.

Then embed the returned markup exactly as given:

```
<Svg>
  <svg viewBox="..." xmlns="http://www.w3.org/2000/svg">...</svg>
</Svg>
```

Do not edit the returned SVG. If the tool returns an ERROR, skip that diagram and carry
on — never substitute your own markup.

Use SVG for: architectures, scientific diagrams, labeled illustrations, anatomy of a
syntax/structure — anything Mermaid can't do.

### Target per lesson:
- `generate_svg` calls (distinct concepts), each embedded in `<Svg>...</Svg>` — the count
  is in the LENGTH BUDGET above, and the lower number there is a **hard floor**. A lesson
  below it is sent back to you.
- Mermaid diagrams (written directly) — count in the budget above
- Place both DIRECTLY under `<Lesson>` (NOT inside Section)
- **A diagram replaces prose, it does not accompany it.** After you embed an SVG of a
  structure or a process, the surrounding text should be two sentences saying what to
  notice — not a paragraph restating the diagram in words.

Once you have written the file, confirm that you are done.

{game_section}"""
