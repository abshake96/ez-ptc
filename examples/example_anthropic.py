"""ez-ptc + Anthropic — Tool mode example.

Uses toolkit.as_tool() and toolkit.tool_schema(format="anthropic") to
register a single meta-tool with Anthropic's messages API.

Also shows the difference between assist_tool_chaining=True and False.

Usage:
    uv run python examples/example_anthropic.py

Requires:
    ANTHROPIC_API_KEY in .env or environment
    pip install anthropic
"""

from dotenv import load_dotenv

from shared_tools import USER_PROMPT, toolkit, toolkit_basic

load_dotenv()


def main():
    import anthropic

    # ── Compare: with vs without tool chaining ──────────────────────
    print("=" * 60)
    print("COMPARISON: Tool schema description sent to the LLM")
    print("=" * 60)

    basic_desc = toolkit_basic.tool_schema(format="anthropic")["description"]
    chained_desc = toolkit.tool_schema(format="anthropic")["description"]

    print("\n--- Without assist_tool_chaining ---")
    print(basic_desc)

    print("\n--- With assist_tool_chaining ---")
    print(chained_desc)

    print("\n" + "=" * 60)
    print("The chaining-enabled version includes 'Returns: {...}' hints")
    print("so the LLM knows the exact shape of each tool's output.")
    print("=" * 60 + "\n")

    # ── Main flow: uses the chaining-enabled toolkit ────────────────
    client = anthropic.Anthropic()
    tool_schema = toolkit.tool_schema(format="anthropic")
    execute_fn = toolkit.as_tool()

    messages = [
        {"role": "user", "content": USER_PROMPT},
    ]

    print(f"User: {USER_PROMPT}\n")

    # Agentic loop
    for turn in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=4096,
            system=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}",
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

                    result = execute_fn(code)
                    print(f"  Result:\n{_indent(result)}\n")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"Assistant: {block.text}")
            break


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    main()
