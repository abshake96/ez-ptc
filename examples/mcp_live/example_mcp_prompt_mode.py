"""ez-ptc MCP Bridge — Prompt Mode with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → toolkit.prompt() → OpenAI → extract_code() → execute()

The LLM receives the full tool listing in its system prompt, writes a
Python code block, and ez-ptc executes it against real MCP filesystem tools.

This example uses assist_tool_chaining=False (the default), so the LLM
prints raw results rather than chaining. See example_mcp_chaining.py
for the chaining variant with return_schemas.

Usage:
    uv run python examples/mcp_live/example_mcp_prompt_mode.py

Requires:
    OPENAI_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" openai python-dotenv
"""

import asyncio

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ez_ptc import Toolkit
from _mcp_session import mcp_session

load_dotenv()

USER_TASK = (
    "List all files in {workdir}. "
    "Then read {workdir}/readme.txt and print its contents."
)


async def main():
    async with mcp_session() as (session, workdir):
        # Seed the workspace with test files
        (workdir / "readme.txt").write_text(
            "This project demonstrates ez-ptc with MCP.\n"
        )
        (workdir / "notes.txt").write_text(
            "Key insight: MCP tools become first-class ez-ptc tools.\n"
        )
        print(f"Workspace: {workdir}")
        print(f"Seeded files: {[f.name for f in workdir.iterdir()]}\n")

        # ── Build toolkit from MCP server ────────────────────────────────
        # include_resources=False because the filesystem server only exposes tools.
        # tool_names limits to the tools needed — keeps the prompt short and focused.
        toolkit = await Toolkit.from_mcp(
            session,
            include_resources=False,
            tool_names=["list_directory", "read_text_file", "write_file"],
        )
        print(f"Discovered {len(toolkit)} MCP tools:")
        for tool in toolkit:
            desc = (tool.description or "")[:60]
            print(f"  - {tool.name}: {desc}")
        print()

        # ── Show the generated prompt ────────────────────────────────────
        prompt_text = toolkit.prompt()
        print("--- Generated System Prompt (first 800 chars) ---")
        print(prompt_text[:800] + "...\n")

        # ── Send to OpenAI in prompt mode ────────────────────────────────
        # No tools registered — the LLM writes a code block in plain text.
        client = AsyncOpenAI()
        # Include the absolute workspace path in the user task so the LLM
        # uses it in all file operations (the MCP server requires absolute paths).
        user_msg = USER_TASK.format(workdir=workdir)
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": user_msg},
            ],
        )

        llm_text = response.choices[0].message.content
        print("--- LLM Response ---")
        print(llm_text)
        print()

        # ── Extract and execute ──────────────────────────────────────────
        code = toolkit.extract_code(llm_text)
        if not code:
            print("No code block found in LLM response.")
            return

        print("--- Executing Code ---")
        result = await toolkit.execute(code)
        print(f"Success: {result.success}")
        print(f"Output:\n{result.output}")
        if result.tool_calls:
            print(f"Tool calls: {[tc['name'] for tc in result.tool_calls]}")
        if not result.success:
            print(f"Error: {result.error}")

        # In prompt mode, the LLM's text response IS the final answer
        # (it contains the code block plus any surrounding explanation).
        print("\n--- Final Response ---")
        print("(Prompt mode: the LLM response above contains the full answer.)")


if __name__ == "__main__":
    asyncio.run(main())
