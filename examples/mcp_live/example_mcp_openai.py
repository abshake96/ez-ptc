"""ez-ptc MCP Bridge + OpenAI — Tool mode agentic loop with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → tool_schema() + as_tool() → OpenAI tool calling → agentic loop

The LLM sends Python code via OpenAI's native tool calling. ez-ptc executes
it against real MCP filesystem tools and feeds results back into the loop.

Uses return_schemas + assist_tool_chaining so the LLM knows tool return
types upfront and can write correct code on the first try.

Usage:
    uv run python examples/mcp_live/example_mcp_openai.py

Requires:
    OPENAI_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" openai python-dotenv
"""

import asyncio
import json

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ez_ptc import Toolkit
from _mcp_session import mcp_session

load_dotenv()

# Return schemas for the tools we'll use — tells the LLM the shape of
# each tool's output so it can chain results without guessing.
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

        # Register with OpenAI's tool calling
        tool_schema = toolkit.tool_schema(format="openai")
        execute_fn = toolkit.as_tool()  # async callable

        client = AsyncOpenAI()
        system = f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"
        user_msg = USER_TASK.format(workdir=workdir)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        print(f"User: {user_msg}\n")

        # ── Agentic loop ─────────────────────────────────────────────────
        for turn in range(10):
            response = await client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=[tool_schema],
            )

            choice = response.choices[0]

            if choice.message.tool_calls:
                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    print(f"[Tool call] execute_tools(code=...)")
                    print(f"  Code:\n{_indent(args['code'])}")

                    result_str = await execute_fn(**args)
                    print(f"  Result:\n{_indent(result_str)}\n")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })
            else:
                print("\n--- Final Response ---")
                print(choice.message.content)
                break
        else:
            print("\n(Max turns reached without final text response)")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    asyncio.run(main())
