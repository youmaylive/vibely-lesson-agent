# Claude Agent SDK - Comprehensive Guide

A complete guide to building AI agents with the Claude Agent SDK. This SDK provides the same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript.

## Table of Contents

1. [Overview](#overview)
2. [Installation & Setup](#installation--setup)
3. [Core Concepts](#core-concepts)
4. [Basic Usage](#basic-usage)
5. [Configuration Options](#configuration-options)
6. [Built-in Tools](#built-in-tools)
7. [Custom Tools & MCP Servers](#custom-tools--mcp-servers)
8. [Subagents](#subagents)
9. [Hooks](#hooks)
10. [Sessions](#sessions)
11. [Permissions](#permissions)
12. [Best Practices](#best-practices)
13. [Complete Examples](#complete-examples)
14. [Error Handling](#error-handling)
15. [Troubleshooting](#troubleshooting)

---

## Overview

The Claude Agent SDK enables you to build AI agents that autonomously:
- Read and edit files
- Run terminal commands
- Search the web
- Query databases
- Integrate with external APIs
- And much more...

### Key Differentiator

Unlike the standard Anthropic Client SDK where you implement tool execution yourself, the **Agent SDK** has Claude execute tools directly. You configure what Claude can do, and Claude handles the rest.

```python
# Client SDK: You implement the tool loop
response = client.messages.create(...)
while response.stop_reason == "tool_use":
    result = your_tool_executor(response.tool_use)
    response = client.messages.create(tool_result=result, ...)

# Agent SDK: Claude handles tools autonomously
async for message in query(prompt="Fix the bug in auth.py"):
    print(message)
```

### When to Use Agent SDK vs CLI

| Use Case | Best Choice |
|----------|-------------|
| Interactive development | CLI |
| CI/CD pipelines | SDK |
| Custom applications | SDK |
| One-off tasks | CLI |
| Production automation | SDK |

---

## Installation & Setup

### Prerequisites

- **Python**: 3.10+
- **Node.js**: 18+ (bundled CLI requires this)

### Python Installation

```bash
# Using pip
pip install claude-agent-sdk

# Using uv (recommended)
uv add claude-agent-sdk
```

### TypeScript Installation

```bash
npm install @anthropic-ai/claude-agent-sdk
```

### Authentication

Set your API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=your-api-key
```

Or create a `.env` file:

```
ANTHROPIC_API_KEY=your-api-key
```

#### Alternative Providers

The SDK supports third-party providers:

| Provider | Environment Variable |
|----------|---------------------|
| Amazon Bedrock | `CLAUDE_CODE_USE_BEDROCK=1` |
| Google Vertex AI | `CLAUDE_CODE_USE_VERTEX=1` |
| Microsoft Azure | `CLAUDE_CODE_USE_FOUNDRY=1` |

---

## Core Concepts

### Message Types

The SDK uses a streaming message architecture:

```python
Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent
```

| Type | Description |
|------|-------------|
| `UserMessage` | User input |
| `AssistantMessage` | Claude's response with content blocks |
| `SystemMessage` | System metadata and status |
| `ResultMessage` | Final result with cost/usage info |
| `StreamEvent` | Partial message updates (optional) |

### Content Blocks

Assistant messages contain content blocks:

```python
ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock
```

| Block | Description |
|-------|-------------|
| `TextBlock` | Claude's text response |
| `ThinkingBlock` | Claude's reasoning (for thinking models) |
| `ToolUseBlock` | Tool invocation request |
| `ToolResultBlock` | Tool execution result |

---

## Basic Usage

### Two Main Interfaces

The Python SDK provides two ways to interact with Claude:

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session | New each time | Reuses same session |
| Conversation | Single exchange | Multiple exchanges |
| Connection | Automatic | Manual control |
| Interrupts | Not supported | Supported |
| Hooks | Not supported | Supported |
| Custom Tools | Not supported | Supported |
| Use Case | One-off tasks | Continuous conversations |

### Using `query()` - Simple Tasks

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Glob"],
            permission_mode="acceptEdits"
        )
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(block.text)
                elif hasattr(block, "name"):
                    print(f"Tool: {block.name}")
        elif isinstance(message, ResultMessage):
            print(f"Done: {message.subtype}")

asyncio.run(main())
```

### Using `ClaudeSDKClient` - Continuous Conversations

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock

async def main():
    async with ClaudeSDKClient() as client:
        # First question
        await client.query("What's the capital of France?")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Claude: {block.text}")

        # Follow-up - Claude remembers context
        await client.query("What's the population of that city?")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Claude: {block.text}")

asyncio.run(main())
```

### Streaming Input

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient

async def message_stream():
    """Generate messages dynamically."""
    yield {"type": "text", "text": "Analyze the following data:"}
    await asyncio.sleep(0.5)
    yield {"type": "text", "text": "Temperature: 25°C, Humidity: 60%"}
    yield {"type": "text", "text": "What patterns do you see?"}

async def main():
    async with ClaudeSDKClient() as client:
        await client.query(message_stream())
        async for message in client.receive_response():
            print(message)

asyncio.run(main())
```

---

## Configuration Options

### ClaudeAgentOptions Reference

```python
@dataclass
class ClaudeAgentOptions:
    # Tool configuration
    tools: list[str] | ToolsPreset | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)

    # System prompt
    system_prompt: str | SystemPromptPreset | None = None

    # MCP servers
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)

    # Permissions
    permission_mode: PermissionMode | None = None
    can_use_tool: CanUseTool | None = None

    # Session management
    continue_conversation: bool = False
    resume: str | None = None
    fork_session: bool = False

    # Limits
    max_turns: int | None = None
    max_budget_usd: float | None = None
    max_thinking_tokens: int | None = None

    # Model selection
    model: str | None = None
    fallback_model: str | None = None

    # Subagents
    agents: dict[str, AgentDefinition] | None = None

    # Hooks
    hooks: dict[HookEvent, list[HookMatcher]] | None = None

    # Output format
    output_format: OutputFormat | None = None

    # Working directory and environment
    cwd: str | Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    add_dirs: list[str | Path] = field(default_factory=list)

    # Settings sources
    setting_sources: list[SettingSource] | None = None

    # Advanced
    betas: list[SdkBeta] = field(default_factory=list)
    include_partial_messages: bool = False
    sandbox: SandboxSettings | None = None
    plugins: list[SdkPluginConfig] = field(default_factory=list)
```

### Common Configuration Patterns

#### Read-only Analysis Agent

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep"],
    permission_mode="bypassPermissions"
)
```

#### Full Automation Agent

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    permission_mode="acceptEdits"
)
```

#### Web Research Agent

```python
options = ClaudeAgentOptions(
    allowed_tools=["WebSearch", "WebFetch", "Read", "Write"],
    permission_mode="acceptEdits"
)
```

#### Custom System Prompt

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Glob"],
    permission_mode="acceptEdits",
    system_prompt="You are a senior Python developer. Always follow PEP 8."
)
```

#### Using Claude Code's System Prompt with Additions

```python
options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": "Additional instructions here..."
    },
    setting_sources=["project"]  # Load CLAUDE.md files
)
```

---

## Built-in Tools

### File Operations

| Tool | Description |
|------|-------------|
| `Read` | Read any file (text, images, PDFs, notebooks) |
| `Write` | Create new files |
| `Edit` | Make precise edits to existing files |
| `Glob` | Find files by pattern (`**/*.ts`, `src/**/*.py`) |
| `Grep` | Search file contents with regex |
| `NotebookEdit` | Edit Jupyter notebook cells |
 `
### System Operations

| Tool | Description |
|------|-------------|
| `Bash` | Run terminal commands, scripts, git operations |
| `BashOutput` | Get output from background shell processes |
| `KillBash` | Stop background shell processes |

### Web Operations

| Tool | Description |
|------|-------------|
| `WebSearch` | Search the web for information |
| `WebFetch` | Fetch and parse web page content |

### Agent Operations

| Tool | Description |
|------|-------------|
| `Task` | Spawn subagents for focused subtasks |
| `AskUserQuestion` | Ask clarifying questions with options |
| `TodoWrite` | Manage task lists |
| `ExitPlanMode` | Exit planning mode with a plan |

### MCP Operations

| Tool | Description |
|------|-------------|
| `ListMcpResources` | List available MCP resources |
| `ReadMcpResource` | Read content from MCP resources |

### Tool Input/Output Examples

#### Read Tool

```python
# Input
{
    "file_path": "/path/to/file.py",
    "offset": 10,   # Optional: start line
    "limit": 100    # Optional: number of lines
}

# Output (text files)
{
    "content": "file contents with line numbers",
    "total_lines": 500,
    "lines_returned": 100
}
```

#### Edit Tool

```python
# Input
{
    "file_path": "/path/to/file.py",
    "old_string": "def old_function():",
    "new_string": "def new_function():",
    "replace_all": False  # Optional
}

# Output
{
    "message": "Successfully edited file",
    "replacements": 1,
    "file_path": "/path/to/file.py"
}
```

#### Bash Tool

```python
# Input
{
    "command": "npm test",
    "timeout": 60000,  # Optional: ms
    "description": "Run tests",
    "run_in_background": False
}

# Output
{
    "output": "All tests passed",
    "exitCode": 0,
    "killed": False,
    "shellId": None
}
```

---

## Custom Tools & MCP Servers

### Model Context Protocol (MCP)

MCP is an open standard for connecting AI agents to external tools and data sources.

### Transport Types

| Type | Use Case |
|------|----------|
| `stdio` | Local processes via stdin/stdout |
| `http` | Remote HTTP servers |
| `sse` | Server-Sent Events for streaming |
| `sdk` | In-process SDK tools |

### Connecting External MCP Servers

#### stdio Server (Local Process)

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                "GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]
            }
        }
    },
    allowed_tools=["mcp__github__list_issues", "mcp__github__search_issues"]
)
```

#### HTTP/SSE Server (Remote)

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "remote-api": {
            "type": "sse",
            "url": "https://api.example.com/mcp/sse",
            "headers": {
                "Authorization": f"Bearer {os.environ['API_TOKEN']}"
            }
        }
    },
    allowed_tools=["mcp__remote-api__*"]  # Wildcard for all tools
)
```

### Creating Custom Tools (SDK MCP Server)

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions
from typing import Any

@tool("add", "Add two numbers", {"a": float, "b": float})
async def add(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{
            "type": "text",
            "text": f"Sum: {args['a'] + args['b']}"
        }]
    }

@tool("get_weather", "Get weather for a city", {"city": str})
async def get_weather(args: dict[str, Any]) -> dict[str, Any]:
    # Simulated weather lookup
    return {
        "content": [{
            "type": "text",
            "text": f"Weather in {args['city']}: Sunny, 72°F"
        }]
    }

# Create server with tools
calculator = create_sdk_mcp_server(
    name="utilities",
    version="1.0.0",
    tools=[add, get_weather]
)

# Use with Claude
options = ClaudeAgentOptions(
    mcp_servers={"utils": calculator},
    allowed_tools=["mcp__utils__add", "mcp__utils__get_weather"]
)
```

### Tool Naming Convention

MCP tools follow the pattern: `mcp__<server-name>__<tool-name>`

Examples:
- `mcp__github__list_issues`
- `mcp__postgres__query`
- `mcp__utils__add`

### Using .mcp.json Config File

Create a `.mcp.json` file at your project root:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### MCP Tool Search

For large numbers of MCP tools, enable tool search to load tools on-demand:

```python
options = ClaudeAgentOptions(
    mcp_servers={ ... },
    env={
        "ENABLE_TOOL_SEARCH": "auto"  # or "auto:5" for 5% threshold
    }
)
```

---

## Subagents

Subagents are separate agent instances that handle focused subtasks with isolated context.

### Benefits

1. **Context Isolation**: Prevents information overload
2. **Parallelization**: Run multiple analyses concurrently
3. **Specialization**: Tailored prompts for specific tasks
4. **Tool Restrictions**: Limit what each subagent can do

### Defining Subagents Programmatically

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async def main():
    async for message in query(
        prompt="Review the authentication module for security issues",
        options=ClaudeAgentOptions(
            # Task tool required for subagent invocation
            allowed_tools=["Read", "Grep", "Glob", "Task"],
            agents={
                "code-reviewer": AgentDefinition(
                    description="Expert code reviewer for quality and security reviews.",
                    prompt="""You are a code review specialist with expertise in
                    security, performance, and best practices.

                    When reviewing code:
                    - Identify security vulnerabilities
                    - Check for performance issues
                    - Verify adherence to coding standards
                    - Suggest specific improvements""",
                    tools=["Read", "Grep", "Glob"],  # Read-only
                    model="sonnet"  # Optional model override
                ),
                "test-runner": AgentDefinition(
                    description="Runs and analyzes test suites.",
                    prompt="""You are a test execution specialist.
                    Run tests and provide clear analysis of results.""",
                    tools=["Bash", "Read", "Grep"]
                )
            }
        )
    ):
        if hasattr(message, "result"):
            print(message.result)

asyncio.run(main())
```

### AgentDefinition Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | `str` | Yes | When to use this agent |
| `prompt` | `str` | Yes | Agent's system prompt |
| `tools` | `list[str]` | No | Allowed tools (inherits if omitted) |
| `model` | `str` | No | Model override (`sonnet`, `opus`, `haiku`, `inherit`) |

### Invoking Subagents

#### Automatic Invocation

Claude automatically delegates based on the task and subagent descriptions.

#### Explicit Invocation

```python
prompt = "Use the code-reviewer agent to check the authentication module"
```

### Dynamic Agent Configuration

```python
def create_security_agent(level: str) -> AgentDefinition:
    is_strict = level == "strict"
    return AgentDefinition(
        description="Security code reviewer",
        prompt=f"You are a {'strict' if is_strict else 'balanced'} security reviewer...",
        tools=["Read", "Grep", "Glob"],
        model="opus" if is_strict else "sonnet"
    )

# Use at runtime
agents={"security": create_security_agent("strict")}
```

### Detecting Subagent Invocation

```python
async for message in query(...):
    if hasattr(message, 'content') and message.content:
        for block in message.content:
            if getattr(block, 'type', None) == 'tool_use' and block.name == 'Task':
                print(f"Subagent invoked: {block.input.get('subagent_type')}")

    # Check if message is from within a subagent
    if hasattr(message, 'parent_tool_use_id') and message.parent_tool_use_id:
        print("  (running inside subagent)")
```

### Common Tool Combinations for Subagents

| Use Case | Tools |
|----------|-------|
| Read-only analysis | `Read`, `Grep`, `Glob` |
| Test execution | `Bash`, `Read`, `Grep` |
| Code modification | `Read`, `Edit`, `Write`, `Grep`, `Glob` |
| Full access | Omit `tools` field to inherit all |

---

## Hooks

Hooks let you run custom code at key points in the agent lifecycle.

### Available Hook Events

| Event | Description |
|-------|-------------|
| `PreToolUse` | Before tool execution |
| `PostToolUse` | After tool execution |
| `UserPromptSubmit` | When user submits a prompt |
| `Stop` | When stopping execution |
| `SubagentStop` | When a subagent stops |
| `PreCompact` | Before message compaction |

### Hook Callback Signature

```python
async def my_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    # Your logic here
    return {}
```

### Hook Return Values

```python
{
    "decision": "block",         # Block the action
    "systemMessage": "...",      # Warning for user
    "reason": "...",             # Feedback for Claude
    "hookSpecificOutput": {...}  # Hook-specific data
}
```

### Example: Security Validation Hook

```python
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher, HookContext
from typing import Any

async def validate_bash_command(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """Block dangerous bash commands."""
    if input_data['tool_name'] == 'Bash':
        command = input_data['tool_input'].get('command', '')
        if 'rm -rf /' in command:
            return {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': 'Dangerous command blocked'
                }
            }
    return {}

async def log_tool_use(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """Log all tool usage for auditing."""
    print(f"Tool used: {input_data.get('tool_name')}")
    return {}

options = ClaudeAgentOptions(
    hooks={
        'PreToolUse': [
            HookMatcher(matcher='Bash', hooks=[validate_bash_command], timeout=120),
            HookMatcher(hooks=[log_tool_use])  # All tools
        ],
        'PostToolUse': [
            HookMatcher(hooks=[log_tool_use])
        ]
    }
)
```

### Example: File Change Audit Hook

```python
from datetime import datetime

async def log_file_change(input_data, tool_use_id, context):
    file_path = input_data.get('tool_input', {}).get('file_path', 'unknown')
    with open('./audit.log', 'a') as f:
        f.write(f"{datetime.now()}: modified {file_path}\n")
    return {}

options = ClaudeAgentOptions(
    permission_mode="acceptEdits",
    hooks={
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[log_file_change])]
    }
)
```

---

## Sessions

Sessions maintain context across multiple exchanges.

### Capturing Session ID

```python
session_id = None

async for message in query(
    prompt="Read the authentication module",
    options=ClaudeAgentOptions(allowed_tools=["Read", "Glob"])
):
    if hasattr(message, 'subtype') and message.subtype == 'init':
        session_id = message.session_id
```

### Resuming Sessions

```python
# Resume with full context
async for message in query(
    prompt="Now find all places that call it",
    options=ClaudeAgentOptions(resume=session_id)
):
    if hasattr(message, "result"):
        print(message.result)
```

### Forking Sessions

Create a new session from an existing one:

```python
options = ClaudeAgentOptions(
    resume=session_id,
    fork_session=True  # Create new session with same context
)
```

### Session with ClaudeSDKClient

```python
async with ClaudeSDKClient() as client:
    await client.query("What's in the project?")
    async for message in client.receive_response():
        pass  # Process response

    # Continue in same session
    await client.query("Tell me more about the main module")
    async for message in client.receive_response():
        pass  # Claude remembers context
```

---

## Permissions

### Permission Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `default` | Requires `canUseTool` callback | Custom approval flows |
| `acceptEdits` | Auto-approves file edits | Trusted development |
| `bypassPermissions` | Skips all prompts | CI/CD pipelines |
| `plan` | Planning mode, no execution | Design review |

### Custom Permission Handler

```python
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

async def custom_permission_handler(
    tool_name: str,
    input_data: dict,
    context: dict
) -> PermissionResultAllow | PermissionResultDeny:
    # Block writes to system directories
    if tool_name == "Write" and input_data.get("file_path", "").startswith("/system/"):
        return PermissionResultDeny(
            message="System directory write not allowed",
            interrupt=True
        )

    # Redirect config file operations to sandbox
    if tool_name in ["Write", "Edit"] and "config" in input_data.get("file_path", ""):
        safe_path = f"./sandbox/{input_data['file_path']}"
        return PermissionResultAllow(
            updated_input={**input_data, "file_path": safe_path}
        )

    return PermissionResultAllow(updated_input=input_data)

options = ClaudeAgentOptions(
    can_use_tool=custom_permission_handler,
    allowed_tools=["Read", "Write", "Edit"]
)
```

### Allowing MCP Tools

```python
options = ClaudeAgentOptions(
    mcp_servers={ ... },
    allowed_tools=[
        "mcp__github__*",           # All tools from github server
        "mcp__db__query",           # Only query from db server
        "mcp__slack__send_message"  # Only send_message from slack
    ]
)
```

---

## Best Practices

### 1. Context Management

- Use subagents to isolate context for specialized tasks
- Let the orchestrator maintain global plan, not every detail
- Use `CLAUDE.md` for project conventions

### 2. Security & Permissions

- Start with deny-all baseline
- Use allowlists per subagent
- Keep secrets short-lived and out of agent context
- Validate sensitive actions with hooks

### 3. Orchestration Design

- Chain subagents for deterministic workflows
- Run subagents in parallel when dependencies are low
- Orchestrator routes; subagents have single responsibility

### 4. Error Handling

```python
from claude_agent_sdk import (
    CLINotFoundError,
    ProcessError,
    CLIJSONDecodeError
)

try:
    async for message in query(prompt="Hello"):
        print(message)
except CLINotFoundError:
    print("Install Claude Code: npm install -g @anthropic-ai/claude-code")
except ProcessError as e:
    print(f"Process failed with exit code: {e.exit_code}")
except CLIJSONDecodeError as e:
    print(f"Failed to parse response: {e}")
```

### 5. Workflow Patterns

**Three-Stage Pipeline:**
1. `pm-spec`: Reads enhancement, writes spec
2. `architect-review`: Validates design, produces ADR
3. `implementer-tester`: Implements code & tests

**TDD with Subagents:**
1. Testing subagent writes tests first
2. Run tests, confirm failures
3. Implementer subagent makes tests pass
4. Code-review subagent enforces quality

---

## Complete Examples

### Bug-Fixing Agent

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

async def fix_bugs():
    async for message in query(
        prompt="Review utils.py for bugs that would cause crashes. Fix any issues.",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Glob"],
            permission_mode="acceptEdits"
        )
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(block.text)
                elif hasattr(block, "name"):
                    print(f"Tool: {block.name}")
        elif isinstance(message, ResultMessage):
            print(f"Done: {message.subtype}")
            print(f"Cost: ${message.total_cost_usd:.4f}")

asyncio.run(fix_bugs())
```

### Multi-Agent Code Review

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async def comprehensive_review():
    async for message in query(
        prompt="Perform a comprehensive review of the authentication module",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Grep", "Glob", "Task"],
            agents={
                "security-reviewer": AgentDefinition(
                    description="Security specialist for vulnerability analysis",
                    prompt="Analyze for security vulnerabilities, injection attacks, auth issues.",
                    tools=["Read", "Grep", "Glob"]
                ),
                "performance-reviewer": AgentDefinition(
                    description="Performance specialist for optimization",
                    prompt="Analyze for performance bottlenecks, memory leaks, inefficiencies.",
                    tools=["Read", "Grep", "Glob"]
                ),
                "maintainability-reviewer": AgentDefinition(
                    description="Code quality specialist",
                    prompt="Analyze for code smells, complexity, documentation gaps.",
                    tools=["Read", "Grep", "Glob"]
                )
            }
        )
    ):
        if hasattr(message, "result"):
            print(message.result)

asyncio.run(comprehensive_review())
```

### Database Query Agent with MCP

```python
import asyncio
import os
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async def query_database():
    async for message in query(
        prompt="How many users signed up last week? Break it down by day.",
        options=ClaudeAgentOptions(
            mcp_servers={
                "postgres": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres",
                             os.environ["DATABASE_URL"]]
                }
            },
            allowed_tools=["mcp__postgres__query"]
        )
    ):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            print(message.result)

asyncio.run(query_database())
```

### Interactive Conversation Session

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock

class ConversationSession:
    def __init__(self, options=None):
        self.client = ClaudeSDKClient(options)
        self.turn_count = 0

    async def start(self):
        await self.client.connect()
        print("Starting conversation. Commands: 'exit', 'interrupt', 'new'")

        while True:
            user_input = input(f"\n[Turn {self.turn_count + 1}] You: ")

            if user_input.lower() == 'exit':
                break
            elif user_input.lower() == 'interrupt':
                await self.client.interrupt()
                continue
            elif user_input.lower() == 'new':
                await self.client.disconnect()
                await self.client.connect()
                self.turn_count = 0
                continue

            await self.client.query(user_input)
            self.turn_count += 1

            print(f"[Turn {self.turn_count}] Claude: ", end="")
            async for message in self.client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="")
            print()

        await self.client.disconnect()

async def main():
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Bash"],
        permission_mode="acceptEdits"
    )
    session = ConversationSession(options)
    await session.start()

asyncio.run(main())
```

### Real-time Progress Monitoring

```python
import asyncio
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ToolUseBlock,
    ToolResultBlock,
    TextBlock
)

async def monitor_progress():
    options = ClaudeAgentOptions(
        allowed_tools=["Write", "Bash"],
        permission_mode="acceptEdits"
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Create 3 Python files with different sorting algorithms")

        async for message in client.receive_messages():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        if block.name == "Write":
                            print(f"Creating: {block.input.get('file_path')}")
                    elif isinstance(block, ToolResultBlock):
                        print("Completed tool execution")
                    elif isinstance(block, TextBlock):
                        print(f"Claude: {block.text[:100]}...")

            if hasattr(message, 'subtype') and message.subtype in ['success', 'error']:
                print("Task completed!")
                break

asyncio.run(monitor_progress())
```

---

## Error Handling

### Error Types

| Error | Description |
|-------|-------------|
| `ClaudeSDKError` | Base exception class |
| `CLINotFoundError` | Claude Code CLI not found |
| `CLIConnectionError` | Connection to Claude Code failed |
| `ProcessError` | Claude Code process failed |
| `CLIJSONDecodeError` | JSON parsing failed |

### Comprehensive Error Handling

```python
from claude_agent_sdk import (
    query,
    ClaudeSDKError,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
    CLIJSONDecodeError
)

async def safe_query(prompt: str):
    try:
        async for message in query(prompt=prompt):
            yield message
    except CLINotFoundError as e:
        print(f"CLI not found: {e}")
        print("Install: npm install -g @anthropic-ai/claude-code")
    except CLIConnectionError as e:
        print(f"Connection failed: {e}")
    except ProcessError as e:
        print(f"Process error (exit code {e.exit_code}): {e.stderr}")
    except CLIJSONDecodeError as e:
        print(f"Parse error on line: {e.line}")
    except ClaudeSDKError as e:
        print(f"SDK error: {e}")
```

### MCP Connection Error Handling

```python
async for message in query(prompt="...", options=options):
    if message.type == "system" and message.subtype == "init":
        failed = [s for s in message.mcp_servers if s.status != "connected"]
        if failed:
            print(f"Failed MCP servers: {failed}")

    if message.type == "result" and message.subtype == "error_during_execution":
        print("Execution failed")
```

---

## Troubleshooting

### Common Issues

#### "API key not found"

Ensure `ANTHROPIC_API_KEY` is set:
```bash
export ANTHROPIC_API_KEY=your-api-key
```

#### Claude not delegating to subagents

1. Include `Task` in `allowedTools`
2. Use explicit prompting: "Use the code-reviewer agent to..."
3. Write clear descriptions in `AgentDefinition`

#### MCP server "failed" status

- Check environment variables match what server expects
- Verify package is installed (`npx` packages need Node.js)
- Test connection strings for database servers
- Check network access for remote servers

#### Tools not being called

Ensure tools are allowed:
```python
allowed_tools=["mcp__servername__*"]
```

Or change permission mode:
```python
permission_mode="acceptEdits"
```

#### Windows: Long prompt failures

Command line length limit (8191 chars) can cause issues. Keep prompts concise or use filesystem-based agents.

### Debug Logging

Enable stderr logging:
```python
options = ClaudeAgentOptions(
    stderr=lambda msg: print(f"[DEBUG] {msg}")
)
```

---

## Resources

### Official Documentation

- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Python SDK Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [TypeScript SDK Reference](https://platform.claude.com/docs/en/agent-sdk/typescript)
- [Quickstart Guide](https://platform.claude.com/docs/en/agent-sdk/quickstart)

### GitHub Repositories

- [Python SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [TypeScript SDK](https://github.com/anthropics/claude-agent-sdk-typescript)
- [Demo Projects](https://github.com/anthropics/claude-agent-sdk-demos)

### MCP Resources

- [MCP Specification](https://modelcontextprotocol.io/)
- [MCP Server Directory](https://github.com/modelcontextprotocol/servers)

### npm Package

- [@anthropic-ai/claude-agent-sdk](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)

---

## Sources

This guide was compiled from the following sources:

- [Agent SDK Overview - Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Quickstart - Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/quickstart)
- [Agent SDK Reference - Python](https://platform.claude.com/docs/en/agent-sdk/python)
- [Subagents in the SDK](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [Connect to External Tools with MCP](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [Building Agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [GitHub - anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [GitHub - anthropics/claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos)
