"""ez-ptc MCP Bridge — Tool chaining with return_schemas.

Demonstrates how return_schemas + assist_tool_chaining=True enables
the LLM to confidently chain MCP tool results — accessing specific
keys rather than printing raw output.

Shows:
  1. Side-by-side prompt comparison (with vs without return_schemas)
  2. Real chained execution against a live filesystem server

Usage:
    uv run python examples/mcp_live/example_mcp_chaining.py

Requires:
    OPENAI_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" openai python-dotenv

Note:
    The RETURN_SCHEMAS keys must match the tool names exposed by your
    version of @modelcontextprotocol/server-filesystem. Run the prompt
    mode example first to see discovered tool names.
"""

import asyncio

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ez_ptc import Toolkit
from _mcp_session import mcp_session

load_dotenv()

# Explicit return schemas for the filesystem tools we'll chain.
# These tell the LLM the shape of each tool's output so it can
# safely write code like `entries = list_directory(...).splitlines()`.
RETURN_SCHEMAS = {
    "list_directory": {
        "type": "string",
        "description": "Newline-separated entries like '[FILE] name' or '[DIR] name'",
    },
    "read_file": {
        "type": "string",
        "description": "Full text content of the file",
    },
    "get_file_info": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "size": {"type": "integer"},
            "modified": {"type": "string"},
            "type": {"type": "string"},
        },
    },
}

USER_TASK = (
    "List all files in {workdir}. "
    "For each .txt file, read its content. "
    "Print a report: file name and the first line of content."
)


async def main():
    async with mcp_session() as (session, workdir):
        # Seed workspace
        (workdir / "alpha.txt").write_text(
            "Project Alpha: distributed caching layer.\nStatus: in progress.\n"
        )
        (workdir / "beta.txt").write_text(
            "Project Beta: ML inference pipeline.\nStatus: complete.\n"
        )
        (workdir / "gamma.txt").write_text(
            "Project Gamma: edge deployment tooling.\nStatus: planning.\n"
        )
        print(f"Workspace: {workdir}\n")

        # ── 1. Side-by-side prompt comparison ────────────────────────────
        print("=" * 60)
        print("1. Prompt comparison: without vs with return_schemas")
        print("=" * 60)

        toolkit_basic = await Toolkit.from_mcp(
            session,
            tool_names=["list_directory", "read_file", "get_file_info"],
            include_resources=False,
            assist_tool_chaining=False,
        )
        toolkit_chained = await Toolkit.from_mcp(
            session,
            tool_names=["list_directory", "read_file", "get_file_info"],
            include_resources=False,
            assist_tool_chaining=True,
            return_schemas=RETURN_SCHEMAS,
        )

        print("\nWithout return_schemas (basic):")
        for line in toolkit_basic.prompt().split("\n"):
            if "def " in line or "Returns:" in line:
                print(f"  {line}")

        print("\nWith return_schemas (chaining-enabled):")
        for line in toolkit_chained.prompt().split("\n"):
            if "def " in line or "Returns:" in line:
                print(f"  {line}")

        # ── 2. Execute chained task ──────────────────────────────────────
        print("\n" + "=" * 60)
        print("2. Executing chained task with real MCP tools")
        print("=" * 60)

        client = AsyncOpenAI()
        # Include absolute workspace path in the user task so the LLM
        # uses it in all file operations (MCP server requires absolute paths).
        user_msg = USER_TASK.format(workdir=workdir)
        print(f"\nUser task: {user_msg}\n")
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": toolkit_chained.prompt()},
                {"role": "user", "content": user_msg},
            ],
        )

        llm_text = response.choices[0].message.content
        print("--- LLM Response ---")
        print(llm_text)
        print()

        code = toolkit_chained.extract_code(llm_text)
        if not code:
            print("No code block in LLM response.")
            return

        print("--- Executing ---")
        result = await toolkit_chained.execute(code)
        print(f"Success: {result.success}")
        print(f"Output:\n{result.output}")
        if result.tool_calls:
            print(f"\nTool calls ({len(result.tool_calls)}):")
            for tc in result.tool_calls:
                print(f"  - {tc['name']}")
        if not result.success:
            print(f"Error: {result.error}")

        # In prompt mode, the LLM's text response IS the final answer.
        print("\n--- Final Response ---")
        print("(Prompt mode: the LLM response above contains the full answer.)")


if __name__ == "__main__":
    asyncio.run(main())
