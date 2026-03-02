"""ez-ptc MCP Bridge + LangChain — Tool mode agentic loop with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → as_tool() wrapped with @langchain_tool → bind_tools() → agentic loop

The LLM sends Python code via LangChain's tool calling. ez-ptc executes
it against real MCP filesystem tools and feeds results back into the loop.

Usage:
    uv run python examples/mcp_live/example_mcp_langchain.py

Requires:
    OPENAI_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" langchain-openai langchain-core python-dotenv
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
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool as langchain_tool
    from langchain_openai import ChatOpenAI

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

        # Wrap ez-ptc's async meta-tool with LangChain's @tool decorator
        execute_fn = toolkit.as_tool()  # async callable

        @langchain_tool
        async def execute_tools(code: str) -> str:
            """Execute Python code with access to tools."""
            return await execute_fn(code)

        tools = [execute_tools]
        tools_by_name = {t.name: t for t in tools}

        llm = ChatOpenAI(model="gpt-4.1-mini")
        llm_with_tools = llm.bind_tools(tools)

        user_msg = USER_TASK.format(workdir=workdir)
        messages = [
            SystemMessage(content=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"),
            HumanMessage(content=user_msg),
        ]

        print(f"User: {user_msg}\n")

        # ── Agentic loop ─────────────────────────────────────────────────
        for turn in range(10):
            ai_msg = await llm_with_tools.ainvoke(messages)
            messages.append(ai_msg)

            if ai_msg.tool_calls:
                for tc in ai_msg.tool_calls:
                    print(f"[Tool call] {tc['name']}(code=...)")
                    print(f"  Code:\n{_indent(tc['args'].get('code', ''))}")

                    tool_obj = tools_by_name[tc["name"]]
                    result = await tool_obj.ainvoke(tc["args"])
                    print(f"  Result:\n{_indent(str(result))}\n")

                    messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            else:
                print("\n--- Final Response ---")
                print(ai_msg.content)
                break
        else:
            print("\n(Max turns reached without final text response)")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    asyncio.run(main())
