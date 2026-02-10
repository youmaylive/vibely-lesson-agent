import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, SystemMessage, UserMessage, AssistantMessage, TextBlock
from pprint import pprint
async def main():
    async for message in query(
        prompt="Plan the fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Bash"], model="claude-opus-4-5")
    ):
        # pprint(message)  # Claude reads the file, finds the bug, edits it
        if isinstance(message, AssistantMessage) and isinstance(message.content[0], TextBlock): 
            print(message.content[0].text)

asyncio.run(main())