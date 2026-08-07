"""
SVG Tool — MCP tool for the lesson agent to call mid-generation.

The lesson agent calls `generate_svg(concept, context, lesson_excerpt)` while writing a
lesson. This tool generates a validated, overlap-free, lesson-grounded SVG and returns
the markup. The agent then embeds the result directly in the .mlai file.

`lesson_excerpt` is what makes this better than the old post-step: the agent passes the
section text it JUST wrote, so the diagram is grounded in the real lesson instead of the
~300 chars of attribute strings the post-step could see.

Uses generate_one_svg() from svg_agent.py (same quality logic).

NOTE: nothing in here may call `query()`. This tool is served to a `query()` session, and
a nested session deadlocks MCP init (`Control request timeout: initialize`). generate_one_svg
talks to Bedrock directly for exactly this reason.
"""

from claude_agent_sdk import tool, create_sdk_mcp_server

from svg_agent import generate_one_svg, DEFAULT_MODEL


# ---------------------------------------------------------------------------
# MCP Tool Definition
# ---------------------------------------------------------------------------

@tool(
    "generate_svg",
    (
        "Generate an educational SVG diagram for a lesson concept. Returns raw "
        "<svg>...</svg> markup ready to embed inside <Svg>...</Svg>. The diagram is "
        "validated, overlap-free, auto-fitted, and checked for faithfulness to the "
        "lesson text you pass in. ALWAYS pass lesson_excerpt — without it the diagram "
        "will invent example values that contradict your lesson."
    ),
    {"concept": str, "context": str, "lesson_excerpt": str},
)
async def generate_svg_tool(args):
    """Generate one lesson-grounded SVG. Called by the lesson agent mid-generation."""
    svg_markup = await generate_one_svg(
        concept=args.get("concept", ""),
        context=args.get("context", ""),
        lesson_excerpt=args.get("lesson_excerpt", ""),
        model=DEFAULT_MODEL,
    )
    if svg_markup:
        return {"content": [{"type": "text", "text": svg_markup}]}
    # No silent placeholder SVG — a failure must be visible, not shipped into a lesson.
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "ERROR: SVG generation failed after all attempts. Omit this diagram "
                    "and continue writing the lesson — do NOT invent your own <svg> markup."
                ),
            }
        ],
        "isError": True,
    }


# ---------------------------------------------------------------------------
# MCP Server (registered with the lesson agent)
# ---------------------------------------------------------------------------

svg_mcp_server = create_sdk_mcp_server(name="svg", tools=[generate_svg_tool])
