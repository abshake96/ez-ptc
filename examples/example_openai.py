"""ez-ptc + OpenAI — Tool mode example.

Uses toolkit.as_tool() to register a single meta-tool with OpenAI's
chat completions API. The LLM calls the meta-tool with Python code,
ez-ptc executes it and returns the result.

Also shows the difference between assist_tool_chaining=True and False.

Usage:
    uv run python examples/example_openai.py

Requires:
    OPENAI_API_KEY in .env or environment
"""

import json

from dotenv import load_dotenv
from openai import OpenAI

from shared_tools import USER_PROMPT, toolkit, toolkit_basic

load_dotenv()


def main():
    client = OpenAI()

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
    tool_schema = toolkit.tool_schema(format="openai")
    execute_fn = toolkit.as_tool()

    messages = [
        {"role": "system", "content": f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"},
        {"role": "user", "content": USER_PROMPT},
    ]

    print(f"User: {USER_PROMPT}\n")

    # Agentic loop
    for turn in range(10):
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            tools=[tool_schema],
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                print(f"[Tool call] execute_tools(code=...)")
                print(f"  Code:\n{_indent(args['code'])}")

                result = execute_fn(**args)
                print(f"  Result:\n{_indent(result)}\n")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            print(f"Assistant: {choice.message.content}")
            break


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    main()
