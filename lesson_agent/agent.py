"""
Agent runner with externally enforced validation loop.

The agent generates MLAI content. Validation is run by Python code
via subprocess — the agent cannot skip or circumvent it.

Flow:
  1. Agent generates the .mlai file (generation phase)
  2. Python runs the validator CLI externally
  3. If errors: Python feeds them back to the agent as a fix prompt
  4. Repeat 2-3 until validation passes or max attempts exhausted
"""

import asyncio
import copy
import json
from pathlib import Path

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from config import (
    PROJECT_ROOT,
    DEFAULT_MODEL,
    DEFAULT_MAX_TURNS,
    MAX_VALIDATION_ATTEMPTS,
)
from prompts.system import build_system_prompt
from prompts.generation import build_generation_prompt
from prompts.fix import build_fix_prompt
from validator import validate_mlai_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_options(
    model: str,
    max_turns: int,
    session_id: str | None = None,
) -> ClaudeAgentOptions:
    """Build common agent options, optionally resuming a session."""
    opts = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        model=model,
        system_prompt=build_system_prompt(),
        max_turns=max_turns,
        cwd=str(PROJECT_ROOT),
    )
    if session_id:
        opts.resume = session_id
    return opts


async def _run_agent(prompt: str, options: ClaudeAgentOptions) -> tuple[bool, str | None]:
    """Run a single agent invocation.

    Returns
    -------
    (success, session_id)
        success: whether the agent reported success
        session_id: captured session id for resumption
    """
    success = False
    session_id = None

    async for message in query(prompt=prompt, options=options):
        # Capture session ID from the init message
        if hasattr(message, "subtype") and message.subtype == "init":
            if hasattr(message, "session_id"):
                session_id = message.session_id

        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
                elif hasattr(block, "name"):
                    print(f"\n🔧 Tool: {block.name}")

        elif isinstance(message, ResultMessage):
            if message.subtype == "success":
                success = True
            else:
                print(f"\n⚠️  Agent finished with status: {message.subtype}")
            if hasattr(message, "total_cost_usd") and message.total_cost_usd:
                print(f"💰 Cost: ${message.total_cost_usd:.4f}")

    return success, session_id


# ---------------------------------------------------------------------------
# Single lesson generation
# ---------------------------------------------------------------------------


async def generate_lesson(
    lesson_spec_path: str,
    curriculum_path: str,
    output_dir: str,
    model: str = DEFAULT_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> bool:
    """Generate a single MLAI lesson with externally enforced validation.

    Steps:
      1. Agent reads spec + curriculum, generates .mlai, writes file
      2. Python validates via subprocess (agent cannot skip this)
      3. On failure: Python feeds errors to agent, agent fixes, repeat
      4. Passes or exhausts MAX_VALIDATION_ATTEMPTS
    """
    lesson_path = Path(lesson_spec_path)
    lesson_id = lesson_path.stem
    # Convert underscores to hyphens for valid MLAI IDs
    # (IDs must contain only letters, numbers, and hyphens)
    mlai_id = lesson_id.replace("_", "-")
    # Resolve to absolute path relative to PROJECT_ROOT (the agent's cwd)
    # so both the agent and the Python validator see the same path.
    output_file = (PROJECT_ROOT / output_dir / f"{lesson_id}.mlai").resolve()

    print(f"\n{'=' * 60}")
    print(f"Generating: {lesson_id}")
    print(f"  Spec:   {lesson_spec_path}")
    print(f"  Output: {output_file}")
    print(f"  Model:  {model}")
    print(f"{'=' * 60}\n")

    # ------------------------------------------------------------------
    # Phase 1: Generation
    # ------------------------------------------------------------------
    print("📝 Phase 1: Generating MLAI content...\n")

    gen_prompt = build_generation_prompt(
        lesson_spec_path=lesson_spec_path,
        curriculum_path=curriculum_path,
        output_file=output_file,
        lesson_id=mlai_id,
    )

    agent_ok, session_id = await _run_agent(
        prompt=gen_prompt,
        options=_agent_options(model=model, max_turns=max_turns),
    )

    if not agent_ok:
        print("\n❌ Agent failed during generation phase.")
        return False

    # ------------------------------------------------------------------
    # Phase 2: External validation loop
    # ------------------------------------------------------------------
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        print(f"\n{'─' * 40}")
        print(f"🔍 Validation attempt {attempt}/{MAX_VALIDATION_ATTEMPTS}")
        print(f"{'─' * 40}")

        result = validate_mlai_file(output_file)

        if result.success:
            print(f"\n✅ Validation passed! ({lesson_id})")
            print(f"   Output: {output_file}")
            return True

        print(f"\n❌ Validation failed ({result.error_count} error(s)):")
        # Show a preview of the errors
        for line in result.raw_output.splitlines()[:20]:
            print(f"   {line}")
        if len(result.raw_output.splitlines()) > 20:
            print(f"   ... ({len(result.raw_output.splitlines()) - 20} more lines)")

        if attempt == MAX_VALIDATION_ATTEMPTS:
            print(f"\n❌ Exhausted {MAX_VALIDATION_ATTEMPTS} validation attempts for {lesson_id}.")
            return False

        # ------------------------------------------------------------------
        # Phase 3: Feed errors back to agent for fixing
        # ------------------------------------------------------------------
        print(f"\n🔧 Sending errors to agent for fixing (attempt {attempt})...\n")

        fix_prompt = build_fix_prompt(
            output_file=output_file,
            validation_errors=result.raw_output,
            attempt=attempt,
        )

        # Resume the same session so the agent has full context
        fix_ok, session_id = await _run_agent(
            prompt=fix_prompt,
            options=_agent_options(
                model=model,
                max_turns=max_turns,
                session_id=session_id,
            ),
        )

        if not fix_ok:
            print(f"\n⚠️  Agent reported issues during fix attempt {attempt}, re-validating anyway...")

    return False


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------


async def generate_all_lessons(
    curriculum_path: str,
    output_dir: str,
    module_filter: str | None = None,
    model: str = DEFAULT_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> dict:
    """Generate MLAI lessons for all lessons in the curriculum."""
    curriculum_file = Path(curriculum_path)
    curriculum_dir = curriculum_file.parent

    with open(curriculum_file, encoding="utf-8") as f:
        curriculum = json.load(f)

    results: dict[str, list[str]] = {"success": [], "failed": [], "skipped": []}
    output_dir_path = Path(output_dir)

    for module in curriculum["modules"]:
        module_id = module["module_id"]

        if module_filter and module_id != module_filter:
            continue

        print(f"\n📚 Module: {module['module_title']}")

        for lesson in module["lessons"]:
            lesson_id = lesson["lesson_id"]
            lesson_spec = curriculum_dir / module_id / f"{lesson_id}.md"

            if not lesson_spec.exists():
                print(f"  ⚠️  Spec not found: {lesson_spec}")
                results["skipped"].append(lesson_id)
                continue

            module_output_dir = output_dir_path / module_id
            module_output_dir.mkdir(parents=True, exist_ok=True)

            ok = await generate_lesson(
                lesson_spec_path=str(lesson_spec),
                curriculum_path=curriculum_path,
                output_dir=str(module_output_dir),
                model=model,
                max_turns=max_turns,
            )

            if ok:
                results["success"].append(lesson_id)
            else:
                results["failed"].append(lesson_id)

    # ------------------------------------------------------------------
    # Write enriched curriculum.json to output with mlai_path fields
    # ------------------------------------------------------------------
    success_set = set(results["success"])
    enriched = copy.deepcopy(curriculum)
    for module in enriched["modules"]:
        module_id = module["module_id"]
        for lesson in module["lessons"]:
            lesson_id = lesson["lesson_id"]
            if lesson_id in success_set:
                lesson["mlai_path"] = f"{module_id}/{lesson_id}.mlai"

    output_curriculum = output_dir_path / "curriculum.json"
    with open(output_curriculum, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Curriculum written to {output_curriculum}")

    return results