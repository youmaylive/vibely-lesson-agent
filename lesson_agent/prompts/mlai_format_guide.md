# MLAI Format Guide

MLAI (Markup Language for Agentic Interfaces) is an XML-based format for creating interactive educational lessons.
Each `.mlai` file is a valid XML document with a `<Lesson>` root element.

## Document Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Lesson>
  <Meta>
    <Id>unique-lesson-id</Id>
    <Title>Lesson Title</Title>
    <Version>1</Version>
    <Tags>
      <Tag>topic</Tag>
    </Tags>
  </Meta>

  <Section>
    <H1>Introduction</H1>
    <Body>Content explanation goes here...</Body>
  </Section>

  <Section>
    <H2>Subtopic</H2>
    <Body>More detailed content...</Body>
    <Code lang="python">example_code()</Code>
  </Section>

  <!-- Interactive components (FlashCard, quizzes) can be placed directly under Lesson -->
  <FlashCard id="fc1">
    <Front>Key term?</Front>
    <Back>Definition here.</Back>
  </FlashCard>

  <SingleSelect id="q1">
    <Prompt>Question text?</Prompt>
    <Options>
      <Option correct="true">Correct answer</Option>
      <Option>Wrong answer</Option>
    </Options>
  </SingleSelect>

</Lesson>
```

## Rules

1. `<Meta>` must be the first child of `<Lesson>`
2. `<Meta>` must contain `<Id>`, `<Title>`, and `<Version>`
3. `<Id>` must start with a letter and contain ONLY letters, numbers, and hyphens (NO underscores). Example: `lesson-08-01`
4. **All content elements (H1, H2, H3, Body, Code) MUST be wrapped in `<Section>` tags.** Interactive components (FlashCard, SingleSelect, MultiSelect, SortQuiz, MatchPairs, FillBlanks, Subjective) can be placed directly under `<Lesson>`.
5. Interactive components (questions) must have a unique `id` attribute
6. Use `&lt;` and `&gt;` for literal < and > in ALL text content, including inside `<Code>` blocks (they are NOT CDATA)
7. Use `&amp;` for literal & in text content
8. `<Body>` supports **Markdown formatting** and **LaTeX math** — no HTML tags

## Rich Content Features

### Markdown in Body

`<Body>` elements support Markdown formatting:

```xml
<Body>
This text includes **bold**, *italic*, and `inline code`.

Here's a [link to documentation](https://example.com).

Lists work too:
- First item
- Second item
- Third item

1. Numbered item one
2. Numbered item two
</Body>
```

### LaTeX Math Expressions

Use `$...$` for inline math and `$$...$$` for display (block) math:

```xml
<Body>
The quadratic formula is $x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}$.

Greek letters like $\alpha$, $\beta$, and $\pi$ are supported.

Display math appears centered on its own line:

$$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$$
</Body>
```

### Section Types (Icons)

Add a `type` attribute to `<Section>` to display different icons:

| Type | Icon | Use For |
|------|------|---------|
| `text` | Document | General explanatory content (default) |
| `concept` | Lightbulb | Key concepts and important ideas |
| `code` | Terminal | Code-focused sections |
| `tip` | Info | Helpful hints and best practices |
| `video` | Play button | Video content sections |
| `example` | Demonstration | Practical examples |

```xml
<Section type="concept">
  <H2>Key Concept</H2>
  <Body>This section explains an important idea with a lightbulb icon.</Body>
</Section>

<Section type="tip">
  <H2>Pro Tip</H2>
  <Body>This is a helpful hint with an info icon.</Body>
</Section>

<Section type="code">
  <H2>Implementation</H2>
  <Body>Code-focused section with a terminal icon.</Body>
  <Code lang="python">print("Hello!")</Code>
</Section>
```

## Available Components (40 total)

### Content Components

#### Back
Back side content of a FlashCard (answer or definition).
- Accepts text content (required)
```xml
<Back>A named reference to a value in memory.</Back>
```

#### Blank
An inline blank in the prompt. Text content is the correct answer.
- Accepts text content (required)
```xml
<Blank>strings</Blank>
```

#### Body
Paragraph text content for explanations and descriptions. Supports **Markdown formatting** and **LaTeX math**.
- Accepts text content (required)
- Markdown: `**bold**`, `*italic*`, `` `code` ``, `[links](url)`, lists (`-` or `1.`)
- Math: `$inline$` for inline, `$$display$$` for block equations
```xml
<Body>Python is a high-level programming language known for readable syntax and versatility.</Body>

<!-- With markdown and math -->
<Body>
Variables store values in memory. Use **descriptive names** like `user_count`.

Key points:
- Variables are *references* to values
- Names are case-sensitive
- Use `snake_case` in Python

The assignment operator creates a binding: $name \leftarrow value$
</Body>
```

#### Code
Code block with syntax highlighting. Requires a lang attribute specifying the programming language.
- Attributes: `lang` one of: python|javascript|typescript|java|c|cpp|csharp|go|rust|ruby|php|sql|bash|html|css|json|xml|markdown|plaintext (required)
- Accepts text content (required)
```xml
<Code lang="python">
name = "Alice"
print(f"Hello, {name}!")
</Code>
```

#### Constraints
Word count limits for the response
- Attributes: `minWords` string (optional), `maxWords` string (optional)
```xml
<Constraints minWords="20" maxWords="150" />
```

#### Criterion
A single grading criterion with points and requirements
- Attributes: `points` string (required), `required` boolean (optional)
- Required children: `<Requirement>`
```xml
<Criterion points="3" required="true">
  <Requirement>Explains readability or maintainability</Requirement>
  <Indicators>readable, understand, maintain, clear</Indicators>
</Criterion>
```

#### Distractor
An unmatched right-side option
- Accepts text content (required)
```xml
<Distractor>char</Distractor>
```

#### Distractors
Container for incorrect answer options
```xml
<Distractors>
  <Distractor>integers</Distractor>
  <Distractor>parentheses</Distractor>
</Distractors>
```

#### FlashCard
A two-sided card that flips between front (question/term) and back (answer/definition). Interactive but not assessable.
- Attributes: `id` string (optional)
- Required children: `<Front>`, `<Back>`
```xml
<FlashCard id="fc1">
  <Front>What is a variable?</Front>
  <Back>A named reference to a value in memory.</Back>
</FlashCard>
```

#### Front
Front side content of a FlashCard (question or term).
- Accepts text content (required)
```xml
<Front>What is a variable?</Front>
```

#### H1
Primary heading for major sections.
- Accepts text content (required)
```xml
<H1>Introduction to Python</H1>
```

#### H2
Secondary heading for subsections.
- Accepts text content (required)
```xml
<H2>Variables and Data Types</H2>
```

#### H3
Tertiary heading for sub-subsections.
- Accepts text content (required)
```xml
<H3>String Concatenation</H3>
```

#### Section
Container for grouping related instructional content. **All content elements (H1, H2, H3, Body, Code) MUST be wrapped in Section tags.**
- Attributes: `type` one of: text|concept|code|tip|video|example (optional, defaults to "text")
- Children: H1, H2, H3, Body, Code
```xml
<Section>
  <H1>Topic Title</H1>
  <Body>Explanation text goes here...</Body>
  <Code lang="python">example()</Code>
</Section>

<!-- With type for icon -->
<Section type="concept">
  <H2>Important Concept</H2>
  <Body>This displays with a **lightbulb icon** and supports *markdown*.</Body>
</Section>

<Section type="tip">
  <H2>Pro Tip</H2>
  <Body>Use math like $E = mc^2$ inline or display: $$\sum_{i=1}^n i = \frac{n(n+1)}{2}$$</Body>
</Section>
```

#### Indicators
Keywords that suggest the requirement is met
- Accepts text content (required)
```xml
<Indicators>readable, understand, maintain, clear</Indicators>
```

#### Item
A single sortable item. The order of Item elements in SortedItems defines the correct order.
- Accepts text content (required)
```xml
<Item>Assembly</Item>
```

#### Left
Left side of a matching pair
- Accepts text content (required)
```xml
<Left>"hello"</Left>
```

#### Option
A single choice option in a selection question. May be marked as correct.
- Attributes: `correct` boolean (optional)
- Accepts text content (required)
```xml
<Option correct="true">4</Option>
```

#### Options
Container for Option children in selection questions. Options are shuffled and answer markers are stripped during rendering.
```xml
<Options>
  <Option correct="true">4</Option>
  <Option>3</Option>
  <Option>5</Option>
  <Option>22</Option>
</Options>
```

#### Pair
A matching pair with Left and Right children
- Required children: `<Left>`, `<Right>`
```xml
<Pair><Left>"hello"</Left><Right>str</Right></Pair>
```

#### Pairs
Container for Pair elements
```xml
<Pairs>
  <Pair><Left>"hello"</Left><Right>str</Right></Pair>
  <Pair><Left>42</Left><Right>int</Right></Pair>
</Pairs>
```

#### Prompt
Question text displayed to the learner for interactive elements.
- Accepts text content
```xml
<Prompt>What is 2 + 2?</Prompt>
```

#### Requirement
Description of what the response must demonstrate for this criterion
- Accepts text content (required)
```xml
<Requirement>Explains readability or maintainability</Requirement>
```

#### Right
Right side of a matching pair
- Accepts text content (required)
```xml
<Right>str</Right>
```

#### RightDistractors
Container for distractor options that have no correct match
```xml
<RightDistractors>
  <Distractor>char</Distractor>
  <Distractor>double</Distractor>
</RightDistractors>
```

#### Rubric
Container for grading criteria. Never sent to client.
```xml
<Rubric>
  <Criterion points="3" required="true">
    <Requirement>Explains readability</Requirement>
    <Indicators>readable, clear</Indicators>
  </Criterion>
  <Criterion points="2">
    <Requirement>Provides example</Requirement>
    <Indicators>example, such as</Indicators>
  </Criterion>
</Rubric>
```

#### SortedItems
Container for Item elements. Write items in the correct order - they will be shuffled when rendered.
```xml
<SortedItems>
  <Item>Assembly</Item>
  <Item>C</Item>
  <Item>Java</Item>
  <Item>Python</Item>
</SortedItems>
```

### Interactive Components (Questions)

#### FillBlanks
Fill-in-the-blank question with drag-drop word pool. Partial credit based on correct fills.
- Attributes: `id` string (required)
- Required children: `<Prompt>`
```xml
<FillBlanks id="q1">
  <Prompt>
    Text values are called <Blank>strings</Blank>.
    They are defined using <Blank>quotes</Blank>.
  </Prompt>
  <Distractors>
    <Distractor>integers</Distractor>
    <Distractor>parentheses</Distractor>
  </Distractors>
</FillBlanks>
```
**Avoid:**
- The id attribute is required for tracking and grading
- Prompt must contain at least one Blank element

#### MatchPairs
Matching question where learner connects left items to right items. Partial credit based on fraction of correct matches.
- Attributes: `id` string (required)
- Required children: `<Prompt>`, `<Pairs>`
```xml
<MatchPairs id="q1">
  <Prompt>Match values to their types:</Prompt>
  <Pairs>
    <Pair><Left>"hello"</Left><Right>str</Right></Pair>
    <Pair><Left>42</Left><Right>int</Right></Pair>
    <Pair><Left>3.14</Left><Right>float</Right></Pair>
  </Pairs>
  <RightDistractors>
    <Distractor>char</Distractor>
    <Distractor>double</Distractor>
  </RightDistractors>
</MatchPairs>
```
**Avoid:**
- The id attribute is required for tracking and grading
- Pairs must have at least 2 Pair elements

#### MultiSelect
Multiple-choice question where the learner can select multiple options. Partial credit grading based on correct selections minus incorrect ones.
- Attributes: `id` string (required)
- Required children: `<Prompt>`, `<Options>`
```xml
<MultiSelect id="q1">
  <Prompt>Which are valid Python data types?</Prompt>
  <Options>
    <Option correct="true">str</Option>
    <Option correct="true">int</Option>
    <Option>char</Option>
    <Option correct="true">bool</Option>
  </Options>
</MultiSelect>
```
**Avoid:**
- The id attribute is required for tracking and grading
- At least one option must be marked correct="true"

#### SingleSelect
Single-choice question where the learner selects exactly one option. Binary grading (all or nothing).
- Attributes: `id` string (required)
- Required children: `<Prompt>`, `<Options>`
```xml
<SingleSelect id="q1">
  <Prompt>What is 2 + 2?</Prompt>
  <Options>
    <Option correct="true">4</Option>
    <Option>3</Option>
    <Option>5</Option>
    <Option>22</Option>
  </Options>
</SingleSelect>
```
**Avoid:**
- The id attribute is required for tracking and grading
- SingleSelect must have exactly one correct option. Use MultiSelect for multiple correct answers.
- At least one option must be marked correct="true"

#### SortQuiz
Ordering question where items are written in correct order and shuffled for the user. Uses Kendall Tau for partial credit.
- Attributes: `id` string (required)
- Required children: `<Prompt>`, `<SortedItems>`
```xml
<SortQuiz id="q1">
  <Prompt>Order from fastest to slowest execution:</Prompt>
  <SortedItems>
    <Item>Assembly</Item>
    <Item>C</Item>
    <Item>Java</Item>
    <Item>Python</Item>
  </SortedItems>
</SortQuiz>
```
**Avoid:**
- The id attribute is required for tracking and grading
- SortedItems must have at least 2 Item elements

#### Subjective
Free-text response graded by AI against a rubric. Rubric is server-only.
- Attributes: `id` string (required)
- Required children: `<Prompt>`, `<Rubric>`
```xml
<Subjective id="q1">
  <Prompt>Why is choosing good variable names important?</Prompt>
  <Rubric>
    <Criterion points="3" required="true">
      <Requirement>Explains readability or maintainability</Requirement>
      <Indicators>readable, understand, maintain, clear</Indicators>
    </Criterion>
    <Criterion points="2">
      <Requirement>Provides a concrete example</Requirement>
      <Indicators>example, such as, compare</Indicators>
    </Criterion>
  </Rubric>
  <Constraints minWords="20" maxWords="150" />
</Subjective>
```
**Avoid:**
- Rubric is required for grading
- minWords cannot be greater than maxWords