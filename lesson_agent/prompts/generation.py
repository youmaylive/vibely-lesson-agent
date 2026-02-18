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

The lesson should include:
- Proper <Meta> block with lesson ID "{lesson_id}" and appropriate title/tags
- Rich instructional content with sections (use `type` attribute: concept, code, tip, example)
- Markdown formatting in Body text (**bold**, *italic*, `code`, lists)
- LaTeX math expressions where appropriate ($inline$ and $$display$$)
- At least 4 FlashCards for key concepts
- At least 2 SingleSelect questions
- At least 1 MultiSelect question
- At least 1 SortQuiz
- At least 1 MatchPairs question
- At least 1 FillBlanks question
- At least 1 Subjective question with rubric
- All assessment IDs must be unique

Make the content genuinely educational and research-grade.
Once you have written the file, confirm that you are done."""