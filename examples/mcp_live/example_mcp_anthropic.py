"""ez-ptc MCP Bridge + Anthropic — Tool mode agentic loop with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → tool_schema(format="anthropic") + as_tool() → Anthropic tool calling → agentic loop

The LLM sends Python code via Anthropic's native tool calling. ez-ptc executes
it against real MCP filesystem tools and feeds results back into the loop.

Usage:
    uv run python examples/mcp_live/example_mcp_anthropic.py

Requires:
    ANTHROPIC_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" anthropic python-dotenv
"""

import asyncio

from dotenv import load_dotenv
from anthropic import AsyncAnthropic

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

        # Register with Anthropic's tool calling (native format)
        tool_schema = toolkit.tool_schema(format="anthropic")
        execute_fn = toolkit.as_tool()  # async callable

        client = AsyncAnthropic()
        system = f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"
        user_msg = USER_TASK.format(workdir=workdir)
        messages = [
            {"role": "user", "content": user_msg},
        ]

        print(f"User: {user_msg}\n")

        # ── Agentic loop ─────────────────────────────────────────────────
        for turn in range(10):
            response = await client.messages.create(
                model="claude-sonnet-4-5-20250514",
                max_tokens=4096,
                system=system,
                tools=[tool_schema],
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        code = block.input.get("code", "")
                        print(f"[Tool call] execute_tools(code=...)")
                        print(f"  Code:\n{_indent(code)}")

                        result = await execute_fn(code)
                        print(f"  Result:\n{_indent(result)}\n")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                print("\n--- Final Response ---")
                for block in response.content:
                    if hasattr(block, "text"):
                        print(block.text)
                break
        else:
            print("\n(Max turns reached without final text response)")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    asyncio.run(main())
