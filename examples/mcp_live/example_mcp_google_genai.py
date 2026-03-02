"""ez-ptc MCP Bridge + Google GenAI — Tool mode agentic loop with a real filesystem server.

End-to-end flow:
  Toolkit.from_mcp() → tool_schema() → FunctionDeclaration → Gemini function calling → agentic loop

Google GenAI requires manually constructing FunctionDeclarations from the
schema and uses a different message format (types.Content / types.Part).

Usage:
    uv run python examples/mcp_live/example_mcp_google_genai.py

Requires:
    GOOGLE_API_KEY in .env or environment
    Node.js / npx on PATH
    pip install "ez-ptc[mcp]" google-genai python-dotenv
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
    from google import genai
    from google.genai import types
    from google.genai.types import FunctionDeclaration, Tool as GenaiTool

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

        execute_fn = toolkit.as_tool()  # async callable

        # Google GenAI doesn't accept raw OpenAI-format schemas — extract
        # fields from tool_schema() and build a FunctionDeclaration manually.
        schema = toolkit.tool_schema(format="openai")
        func_decl = FunctionDeclaration(
            name=schema["function"]["name"],
            description=schema["function"]["description"],
            parameters=schema["function"]["parameters"],
        )
        tools = GenaiTool(function_declarations=[func_decl])
        config = types.GenerateContentConfig(
            tools=[tools],
            system_instruction=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}",
        )

        client = genai.Client()
        user_msg = USER_TASK.format(workdir=workdir)
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=user_msg)],
            )
        ]

        print(f"User: {user_msg}\n")

        # ── Agentic loop ─────────────────────────────────────────────────
        for turn in range(10):
            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            parts = candidate.content.parts
            function_calls = [p for p in parts if p.function_call]

            if function_calls:
                contents.append(candidate.content)

                response_parts = []
                for part in function_calls:
                    fc = part.function_call
                    code = fc.args.get("code", "")
                    print(f"[Tool call] execute_tools(code=...)")
                    print(f"  Code:\n{_indent(code)}")

                    result = await execute_fn(code)
                    print(f"  Result:\n{_indent(result)}\n")

                    response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result},
                        )
                    )

                contents.append(types.Content(role="user", parts=response_parts))
            else:
                print("\n--- Final Response ---")
                print(response.text)
                break
        else:
            print("\n(Max turns reached without final text response)")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    asyncio.run(main())
