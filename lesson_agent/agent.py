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
import os
from pathlib import Path

# MUST be set before claude_agent_sdk is imported — Query reads it at construction time.
#
# With an SDK MCP server registered, the SDK waits this long for the FIRST result before
# closing the subprocess's stdin (see _internal/query.py, `_stream_close_timeout`). The
# default is 60s. Our generate_svg tool takes 15-90s (generate + review, up to 4 attempts),
# so stdin was closing mid-run and every tool call after the first died with
# "Tool permission stream closed before response received" / "Stream closed".
#
# This — not nested query() calls — is what actually broke the earlier in-agent-tool
# attempt. Verified: 3 sequential 20s tool calls fail 1/3 at the default and pass 3/3 here.
os.environ.setdefault("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", "1800000")  # 30 min

from claude_agent_sdk import (  # noqa: E402 — must follow the env var above
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
from svg_agent import resolve_svgs
from svg_tool import svg_mcp_server


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
        allowed_tools=[
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
            "mcp__svg__generate_svg",
        ],
        # Dict of name -> server, NOT a list. Passing a list here is a second,
        # independent cause of `Control request timeout: initialize`.
        mcp_servers={"svg": svg_mcp_server},
        permission_mode="acceptEdits",
        model=model,
        system_prompt=build_system_prompt(),
        max_turns=max_turns,
        cwd=str(PROJECT_ROOT),
    )
    if session_id:
        opts.resume = session_id
    return opts


async def _prompt_stream(text: str):
    """Wrap a prompt string as a streaming-mode message iterator.

    In-process MCP servers (our `generate_svg` tool) REQUIRE this. With a plain string
    prompt the SDK runs one-shot and closes the subprocess's stdin, which kills the
    control channel the SDK uses to serve tool calls back to the CLI — the first
    `mcp__svg__generate_svg` call then dies with
    `CLIConnectionError: ProcessTransport is not ready for writing`.

    This is the actual reason the earlier in-agent-tool attempt failed. Do not "simplify"
    this back to `query(prompt=some_string)` while an SDK MCP server is registered.
    """
    yield {
        "type": "user",
        "message": {"role": "user", "content": text},
        "parent_tool_use_id": None,
        "session_id": "default",
    }


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
    cost_usd = 0.0

    # Retry on transient TaskGroup/connection errors (Foundry can drop mid-session,
    # especially during long tool-call sequences like image search/validate).
    MAX_RETRIES = 3
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async for message in query(prompt=_prompt_stream(prompt), options=options):
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
                        cost_usd = message.total_cost_usd
                        print(f"💰 Cost: ${cost_usd:.4f}")

            # If we got here without exception, we're done
            break

        except Exception as exc:
            print(f"\n⚠️  Agent error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            if attempt < MAX_RETRIES:
                print(f"   Retrying in 3s...")
                await asyncio.sleep(3)
                # Fresh options (new MCP server) for the retry
                options = _agent_options(
                    model=options.model,
                    max_turns=options.max_turns,
                    session_id=session_id,
                )
            else:
                print(f"\n❌ Agent failed after {MAX_RETRIES} attempts.")

    return success, session_id, cost_usd


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

    # Convert underscores to hyphens for MLAI ID (IDs must use hyphens)
    mlai_id = lesson_id.replace('_', '-')

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

    agent_ok, session_id, _cost = await _run_agent(
        prompt=gen_prompt,
        options=_agent_options(model=model, max_turns=max_turns),
    )

    if not agent_ok:
        print("\n❌ Agent failed during generation phase.")
        return False

    # ------------------------------------------------------------------
    # Phase 1b: Safety net for leftover SVG placeholders
    # ------------------------------------------------------------------
    # SVGs are generated in-agent now (mcp__svg__generate_svg), so this is a no-op on
    # a normal run. It only fires if the agent ignored the tool and wrote placeholders
    # anyway, or for older .mlai files. resolve_svgs prints and returns 0 when there is
    # nothing to do, and derives the lesson excerpt itself in that fallback path.
    if output_file.exists():
        await resolve_svgs(output_file, model=model)

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
        fix_ok, session_id, _cost = await _run_agent(
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

    output_curriculum = output_dir_path / "new_curriculum.json"
    with open(output_curriculum, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Curriculum written to {output_curriculum}")

    # Emit usage summary marker (parsed by curriculum worker)
    total_lessons = len(results["success"]) + len(results["failed"])
    print(f"\n##USAGE:total_cost=0:input_tokens=0:output_tokens=0:api_calls={total_lessons}##")

    return results
