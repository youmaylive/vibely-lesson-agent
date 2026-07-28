"""
User prompt for the initial lesson generation step.
"""

from pathlib import Path


def build_generation_prompt(
    lesson_spec_path: str,
    curriculum_path: str,
    output_file: Path,
    lesson_id: str,
) -> str:
    """Build the user prompt that instructs the agent to generate an MLAI file."""
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

  <FlashCard id="fc-1">
    <Front>Key term?</Front>
    <Back>Definition.</Back>
  </FlashCard>

  <Section type="example">
    <H3>Worked Example</H3>
    <Body>...</Body>
    <Code lang="python">...</Code>
  </Section>

  <SingleSelect id="q1">
    <Prompt>Question?</Prompt>
    <Options>
      <Option correct="true">Right</Option>
      <Option>Wrong</Option>
    </Options>
  </SingleSelect>

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

4. **Document flow**: Meta → Teaching Sections → FlashCards → More Sections → Assessments → Summary Section

## Content Requirements:

- Proper <Meta> block with lesson ID "{lesson_id}" and appropriate title/tags
- Rich instructional content with multiple Sections (use types: concept, example, code, tip)
- Markdown formatting in Body text (**bold**, *italic*, `code`, lists)
- LaTeX math expressions where appropriate ($inline$ and $$display$$)
- At least 4 FlashCards for key concepts (placed between sections)
- At least 2 SingleSelect questions
- At least 1 MultiSelect question
- At least 1 SortQuiz
- At least 1 MatchPairs question
- At least 1 FillBlanks question
- At least 1 Subjective question with rubric
- All assessment IDs must be unique
- A final summary Section wrapping up key points

Make the content genuinely educational and research-grade.
Once you have written the file, confirm that you are done."""
