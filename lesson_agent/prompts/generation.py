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
3. Generate a complete, high-quality .mlai lesson file
4. Write it to: {output_file}

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
