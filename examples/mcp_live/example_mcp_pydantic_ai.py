"""ez-ptc MCP Bridge + Pydantic AI — Tool mode with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → as_tool() → Pydantic AI Tool → Agent.run() handles the agentic loop

Pydantic AI manages the tool-calling loop automatically, making this the
simplest framework integration.

Usage:
    uv run python examples/mcp_live/example_mcp_pydantic_ai.py

Requires:
    OPENAI_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" pydantic-ai python-dotenv
"""

import asyncio

from dotenv import load_dotenv

from ez_ptc import Toolkit
from _mcp_session import mcp_session

load_dotenv()

RETURN_SCHEMAS = {
    "list_directory": {
        "type": "string",
        "description": "Newline-separated entries like '[FILE] name' or '[DIR] name'",
    },
    "read_text_file": {
        "type": "string",
        "description": "Full text content of the file",
    },
    "write_file": {
        "type": "string",
        "description": "Success confirmation message",
    },
}

USER_TASK = (
    "List all files in {workdir}. "
    "Read each .txt file and print its name and first line. "
    "Then create {workdir}/index.txt listing all the .txt files you found."
)


async def main():
    from pydantic_ai import Agent, Tool

    async with mcp_session() as (session, workdir):
        # Seed workspace
        (workdir / "project.txt").write_text(
            "Project Alpha: AI-powered analytics platform.\n"
        )
        (workdir / "tasks.txt").write_text(
            "TODO: Add unit tests, write docs, deploy to prod.\n"
        )
        (workdir / "config.txt").write_text(
            "env=production\ndebug=false\nport=8080\n"
        )
        print(f"Workspace: {workdir}\n")

        # ── Build toolkit from live MCP server ───────────────────────────
        toolkit = await Toolkit.from_mcp(
            session,
            include_resources=False,
            assist_tool_chaining=True,
            tool_names=["list_directory", "read_text_file", "write_file"],
            return_schemas=RETURN_SCHEMAS,
        )
        print(f"Discovered {len(toolkit)} tools from MCP filesystem server\n")

        # Wrap ez-ptc's async meta-tool as a Pydantic AI Tool
        execute_fn = toolkit.as_tool()  # async callable
        pydantic_tool = Tool(execute_fn, takes_ctx=False)

        agent = Agent(
            "openai:gpt-4.1-mini",
            system_prompt=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}",
            tools=[pydantic_tool],
        )

        user_msg = USER_TASK.format(workdir=workdir)
        print(f"User: {user_msg}\n")

        # Pydantic AI handles the agentic loop automatically
        result = await agent.run(user_msg)

        print("\n--- Final Response ---")
        print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
