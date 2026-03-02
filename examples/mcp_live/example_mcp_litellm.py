"""ez-ptc MCP Bridge + LiteLLM — Tool mode agentic loop with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → tool_schema() + as_tool() → LiteLLM acompletion() → agentic loop

LiteLLM uses the OpenAI-compatible tool calling format but can route to
any provider (swap the model string to use Anthropic, Gemini, etc.).

Usage:
    uv run python examples/mcp_live/example_mcp_litellm.py

Requires:
    OPENAI_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" litellm python-dotenv
"""

import asyncio
import json

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
    import litellm

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

        # LiteLLM uses OpenAI-compatible format
        tool_schema = toolkit.tool_schema(format="openai")
        execute_fn = toolkit.as_tool()  # async callable

        user_msg = USER_TASK.format(workdir=workdir)
        messages = [
            {"role": "system", "content": f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"},
            {"role": "user", "content": user_msg},
        ]

        print(f"User: {user_msg}\n")

        # ── Agentic loop ─────────────────────────────────────────────────
        # Swap model string for any LiteLLM-supported provider, e.g.
        # "anthropic/claude-sonnet-4-5-20250514", "gemini/gemini-2.0-flash", etc.
        for turn in range(10):
            response = await litellm.acompletion(
                model="openai/gpt-4.1-mini",
                messages=messages,
                tools=[tool_schema],
            )

            choice = response.choices[0]
            message = choice.message

            if message.tool_calls:
                messages.append(message)

                for tool_call in message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    print(f"[Tool call] execute_tools(code=...)")
                    print(f"  Code:\n{_indent(args['code'])}")

                    result = await execute_fn(**args)
                    print(f"  Result:\n{_indent(result)}\n")

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": result,
                    })
            else:
                print("\n--- Final Response ---")
                print(message.content)
                break
        else:
            print("\n(Max turns reached without final text response)")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    asyncio.run(main())
