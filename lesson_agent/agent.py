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
    GAMES_GUIDE_DIR,
    MAX_GAME_CANDIDATES,
)
from prompts.system import build_system_prompt
from prompts.generation import build_generation_prompt
from prompts.fix import build_fix_prompt
from games import build_game_prompt_section, registered_game_types
from budget import budget_for_spec, build_budget_section
import lesson_shape
from validator import validate_mlai_file
from svg_agent import resolve_svgs
from svg_tool import svg_mcp_server
import usage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Lessons whose Mermaid gate could not run, collected across a batch so the
# run-level summary can state it plainly instead of leaving it buried in a
# multi-thousand-line log.
_MERMAID_GATE_SKIPS: list[str] = []

# Lessons that shipped below the visual floor even after the one top-up pass, and the
# per-lesson shape measurements, both collected across a batch for the run summary.
# Rule 27's corollary: a number computed and never read is not a gate — these are read
# by `_print_shape_summary` and, in a worker run, land in the phase metadata via the
# per-course census in `workers/phases/curriculum.py`.
_SHAPE_BELOW_FLOOR: list[str] = []
_SHAPE_MEASUREMENTS: list[tuple[str, str]] = []


def lesson_marker(status: str, output_file: Path) -> str:
    """Render the ``##LESSON:<status>:rel=module_XX/lesson_XX.mlai##`` marker.

    The curriculum worker uploads a lesson to S3 when it sees this marker with
    ``status=validated``, instead of when the file first appears on disk. That
    ordering is the whole point: the agent rewrites ``output_file`` in place on
    every fix attempt, so "first appeared" meant S3 got the unvalidated draft and
    kept it — the fix loop's output never shipped. See
    ``memebu-engine-v2/workers/phases/curriculum.py``'s ``parse_lesson_marker``;
    the field names and the ``key=value`` colon format must stay in sync with it,
    exactly as for ``usage.marker()``.

    ``rel`` is ``module_XX/lesson_XX.mlai`` — the worker needs the module segment
    to rebuild the S3 key, and ``output_file.name`` alone would collide across
    modules (every module has a ``lesson_01.mlai``).
    """
    rel = f"{output_file.parent.name}/{output_file.name}"
    return f"##LESSON:{status}:rel={rel}##"


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
                    # Book this call's spend into the run total. Both callers below
                    # discard the returned cost, and nothing tracked tokens at all —
                    # the ##USAGE marker this feeds is the only way the MLAI phase's
                    # spend reaches usage_records.
                    usage.add_sdk_usage(
                        getattr(message, "usage", None),
                        cost_usd=getattr(message, "total_cost_usd", 0.0) or 0.0,
                    )

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


async def _enforce_shape_floor(
    output_file: Path,
    budget,
    lesson_id: str,
    model: str,
    max_turns: int,
    session_id: str | None,
) -> str | None:
    """Measure the written lesson and, if it is below the visual floor, top it up once.

    Returns the (possibly new) session id so the caller keeps resuming one session.

    Bounded at exactly one attempt on purpose. The alternative shapes were both worse:
    looping until the floor is met has no spend cap on a path where a single diagram is
    ~$0.16 and 8 Bedrock calls, and failing the lesson throws away a working lesson over
    a missing illustration. So: try once, then say so loudly and continue.
    """
    try:
        content = output_file.read_text(encoding="utf-8")
    except OSError as exc:
        # A read-only audit that cannot run must never pass silently (rule 21) — but it
        # also must not take the run down.
        print(f"\n⚠️  SHAPE GATE UNAVAILABLE — could not read {output_file}: {exc}")
        return session_id

    report = lesson_shape.check(content, budget)
    print(f"\n📐 Shape: {report.one_line()}")
    for finding in report.advisory:
        print(f"   advisory {finding}")

    if not report.has_hard:
        _SHAPE_MEASUREMENTS.append((lesson_id, report.one_line()))
        return session_id

    for finding in report.hard:
        print(f"   ⚠️  {finding}")

    print(f"\n🎨 Topping up visuals for {lesson_id} (one attempt)...\n")

    topup_prompt = lesson_shape.build_topup_prompt(
        report=report,
        budget=budget,
        output_file=output_file,
        section_headings=lesson_shape.sections_without_visuals(content),
    )

    # Resume the same session so the agent still has the lesson it just wrote in context
    # — the top-up needs to know what the surrounding text says to diagram it, and
    # `lesson_excerpt` grounding is the whole reason diagram labels match the lesson.
    _ok, session_id, _cost = await _run_agent(
        prompt=topup_prompt,
        options=_agent_options(model=model, max_turns=max_turns, session_id=session_id),
    )

    # The agent may have written placeholders rather than calling the tool. resolve_svgs
    # is a no-op when there are none, and it prints what it found either way.
    await resolve_svgs(output_file, model=model)

    try:
        content = output_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"\n⚠️  SHAPE GATE UNAVAILABLE — could not re-read {output_file}: {exc}")
        return session_id

    report = lesson_shape.check(content, budget)
    _SHAPE_MEASUREMENTS.append((lesson_id, report.one_line()))
    print(f"\n📐 Shape after top-up: {report.one_line()}")

    if report.has_hard:
        _SHAPE_BELOW_FLOOR.append(lesson_id)
        # One line, greppable, naming the lesson and the numbers. Fail-open is a
        # deliberate choice here; fail-open QUIETLY is how the Mermaid bug shipped.
        print(
            f"\n🚨 SHAPE-BELOW-FLOOR {lesson_id} — "
            f"{'; '.join(str(f) for f in report.hard)}. Shipping anyway."
        )

    return session_id


def _print_shape_summary(total_lessons: int) -> None:
    """Run-level shape report. Called once per batch, after every lesson."""
    if _SHAPE_MEASUREMENTS:
        print(f"\n📐 Shape census ({len(_SHAPE_MEASUREMENTS)} lesson(s)):")
        for lesson_id, line in _SHAPE_MEASUREMENTS:
            print(f"   {lesson_id}  {line}")

    if _SHAPE_BELOW_FLOOR:
        print(
            f"\n🚨 SHAPE-BELOW-FLOOR for {len(_SHAPE_BELOW_FLOOR)}/{total_lessons} "
            f"lesson(s) — they shipped with fewer diagrams than the floor: "
            f"{', '.join(_SHAPE_BELOW_FLOOR)}"
        )


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

    # Which game types fit THIS lesson, with their full authoring specs. Deterministic
    # narrowing (Stage A) so the prompt cost is bounded and flat in the size of the game
    # registry; the model still makes the choice (Stage B), and may decline. Returns ""
    # — loudly — if the generated guide is missing, so a missing build artifact costs
    # games rather than the whole run. See games.py.
    try:
        spec_text = lesson_path.read_text(encoding="utf-8")
    except OSError as exc:
        # The agent reads this file too, so this is not fatal here — it will fail with a
        # better message. Don't lose the game section silently, though.
        print(f"⚠️  GAMES: could not read the lesson spec for game selection: {exc}")
        spec_text = ""

    game_section = build_game_prompt_section(
        GAMES_GUIDE_DIR, spec_text, MAX_GAME_CANDIDATES
    )

    # How long this lesson should be. Derived from the `duration:` the planner already
    # writes into every spec's frontmatter and that nothing has ever read — see
    # budget.py. A spec without frontmatter (every spec in test_curriculum/) silently
    # gets the default band rather than failing.
    budget = budget_for_spec(spec_text)
    print(
        f"  Budget: {budget.band} "
        f"({'no duration in spec' if budget.minutes is None else str(budget.minutes) + ' min stated'})"
        f" → {budget.sections[0]}-{budget.sections[1]} sections, "
        f"{budget.words[0]}-{budget.words[1]} words, "
        f"{budget.svgs[0]}-{budget.svgs[1]} SVG (floor {budget.svg_floor})"
    )

    gen_prompt = build_generation_prompt(
        lesson_spec_path=lesson_spec_path,
        curriculum_path=curriculum_path,
        output_file=output_file,
        lesson_id=mlai_id,
        game_section=game_section,
        budget_section=build_budget_section(budget),
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
    # Phase 1c: Shape check — the visual floor, and one bounded top-up
    # ------------------------------------------------------------------
    # Deliberately OUTSIDE the validation loop below. Two reasons, both from AGENTS.md:
    #
    #   * rule 24 — a cheap gate placed before the expensive one silently replaces it,
    #     and `MAX_VALIDATION_ATTEMPTS = 500` has no spend cap. A shape defect must not
    #     be able to consume the budget that exists for repairing broken XML.
    #   * rule 31 — fail-open vs fail-closed is a property of the path. This is a
    #     read-only quality audit on a five-hour, ~$64 generation run, so it fails open
    #     LOUDLY: one top-up attempt, then print and ship. A lesson with 2 diagrams
    #     instead of 3 is weaker; refusing to ship it is the wrong trade.
    #
    # Only the SVG floor gets a retry. Word and section overruns are printed and left
    # for the per-course census, because "cut 400 words" is not a fix the model can
    # carry out safely — it has no way to know which paragraph was load-bearing.
    if output_file.exists():
        session_id = await _enforce_shape_floor(
            output_file=output_file,
            budget=budget,
            lesson_id=lesson_id,
            model=model,
            max_turns=max_turns,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Phase 2: External validation loop
    # ------------------------------------------------------------------
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        print(f"\n{'─' * 40}")
        print(f"🔍 Validation attempt {attempt}/{MAX_VALIDATION_ATTEMPTS}")
        print(f"{'─' * 40}")

        result = validate_mlai_file(output_file)

        if not result.mermaid_gate_ran:
            # The gate could not run (missing deps, no node, crash). We do not
            # fail the lesson over an infra problem, but this must never slide by
            # unnoticed — a silently-skipped Mermaid check is exactly how broken
            # diagrams reached students before the gate existed.
            _MERMAID_GATE_SKIPS.append(lesson_id)
            print("\n⚠️  MERMAID GATE UNAVAILABLE — diagrams in this lesson were NOT checked.")
            for line in result.raw_output.splitlines():
                if line.startswith("MERMAID GATE UNAVAILABLE"):
                    print(f"   {line}")

        if result.success:
            print(f"\n✅ Validation passed! ({lesson_id})")
            print(f"   Output: {output_file}")
            # Signals the worker to upload THIS file now. Emitted only here, after
            # the validator passed on the bytes currently on disk.
            print(lesson_marker("validated", output_file), flush=True)
            return True

        print(f"\n❌ Validation failed ({result.error_count} error(s)):")
        # Show a preview of the errors
        for line in result.raw_output.splitlines()[:20]:
            print(f"   {line}")
        if len(result.raw_output.splitlines()) > 20:
            print(f"   ... ({len(result.raw_output.splitlines()) - 20} more lines)")

        if attempt == MAX_VALIDATION_ATTEMPTS:
            print(f"\n❌ Exhausted {MAX_VALIDATION_ATTEMPTS} validation attempts for {lesson_id}.")
            print(lesson_marker("failed", output_file), flush=True)
            return False

        # ------------------------------------------------------------------
        # Phase 3: Feed errors back to agent for fixing
        # ------------------------------------------------------------------
        print(f"\n🔧 Sending errors to agent for fixing (attempt {attempt})...\n")

        fix_prompt = build_fix_prompt(
            output_file=output_file,
            validation_errors=result.raw_output,
            attempt=attempt,
            # Empty when the guide is missing, which drops the game guidance rather
            # than telling the agent to pick "one of ()".
            game_types=registered_game_types(GAMES_GUIDE_DIR),
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

    # Run-level Mermaid gate report. State coverage explicitly either way: a
    # missing line is indistinguishable from a passing one in a long log, and
    # "the gate silently did nothing" is the failure mode this whole layer exists
    # to prevent.
    if _MERMAID_GATE_SKIPS:
        print(
            f"\n🚨 MERMAID GATE SKIPPED for {len(_MERMAID_GATE_SKIPS)}/{total_lessons} "
            f"lesson(s) — their diagrams were NEVER checked and may not render: "
            f"{', '.join(_MERMAID_GATE_SKIPS)}"
        )
    else:
        print(f"\n🎯 Mermaid gate ran on all {total_lessons} lesson(s).")

    _print_shape_summary(total_lessons)

    _snap = usage.snapshot()
    print(
        f"\n💰 Run usage: ${_snap['total_cost']:.4f}, "
        f"{_snap['input_tokens']} in / {_snap['output_tokens']} out tokens, "
        f"{_snap['api_calls']} API calls over {total_lessons} lesson(s)"
    )
    print(f"\n{usage.marker()}")

    return results
