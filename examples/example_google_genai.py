"""ez-ptc + Google Gemini — Tool mode example.

Uses toolkit.as_tool() with the google-genai SDK to register
a single meta-tool with Gemini's function calling.

Also shows the difference between assist_tool_chaining=True and False.

Usage:
    uv run python examples/example_google_genai.py

Requires:
    GOOGLE_API_KEY in .env or environment
    pip install google-genai
"""

from dotenv import load_dotenv

from shared_tools import USER_PROMPT, toolkit, toolkit_basic

load_dotenv()


def main():
    from google import genai
    from google.genai import types
    from google.genai.types import FunctionDeclaration, Tool as GenaiTool

    # ── Compare: with vs without tool chaining ──────────────────────
    print("=" * 60)
    print("COMPARISON: Tool schema description sent to the LLM")
    print("=" * 60)

    basic_desc = toolkit_basic.tool_schema()["function"]["description"]
    chained_desc = toolkit.tool_schema()["function"]["description"]

    print("\n--- Without assist_tool_chaining ---")
    print(basic_desc)

    print("\n--- With assist_tool_chaining ---")
    print(chained_desc)

    print("\n" + "=" * 60)
    print("The chaining-enabled version includes 'Returns: {...}' hints")
    print("so the LLM knows the exact shape of each tool's output.")
    print("=" * 60 + "\n")

    # ── Main flow: uses the chaining-enabled toolkit ────────────────
    client = genai.Client()
    execute_fn = toolkit.as_tool()

    # Build the function declaration from toolkit.tool_schema()
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

    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=USER_PROMPT)],
        )
    ]

    print(f"User: {USER_PROMPT}\n")

    # Agentic loop
    for turn in range(10):
        response = client.models.generate_content(
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

                result = execute_fn(code)
                print(f"  Result:\n{_indent(result)}\n")

                response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result},
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
        else:
            print(f"Assistant: {response.text}")
            break


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    main()
