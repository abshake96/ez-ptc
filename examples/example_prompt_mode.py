"""ez-ptc Prompt Mode — Framework-free example.

Demonstrates Mode 1 (prompt mode) where the toolkit generates a system
prompt instruction block, the LLM writes code in its text response,
and ez-ptc extracts and executes it. No framework needed — just raw
OpenAI API calls.

Also shows the difference between assist_tool_chaining=True and False.

Usage:
    uv run python examples/example_prompt_mode.py

Requires:
    OPENAI_API_KEY in .env or environment
"""

from dotenv import load_dotenv
from openai import OpenAI

from shared_tools import USER_PROMPT, toolkit, toolkit_basic

load_dotenv()


def main():
    client = OpenAI()

    # ── Compare: with vs without tool chaining ──────────────────────
    print("=" * 60)
    print("COMPARISON: What the LLM sees in the system prompt")
    print("=" * 60)

    print("\n--- Without assist_tool_chaining (basic) ---")
    print(toolkit_basic.prompt())

    print("\n--- With assist_tool_chaining (recommended) ---")
    print(toolkit.prompt())

    print("\n" + "=" * 60)
    print("Notice the '# Returns: ...' comments above. The LLM now knows")
    print("the exact keys (temp, condition, etc.) to use when chaining.")
    print("=" * 60)

    # ── Main flow: uses the chaining-enabled toolkit ────────────────
    tool_instructions = toolkit.prompt()
    print()

    # Send to LLM without any tool calling — just system prompt + user message
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": tool_instructions},
            {"role": "user", "content": USER_PROMPT},
        ],
    )

    llm_text = response.choices[0].message.content
    print("--- LLM Response ---")
    print(llm_text)
    print()

    # Extract and execute the code block
    code = toolkit.extract_code(llm_text)
    if code:
        print("--- Extracted Code ---")
        print(code)
        print()

        result = toolkit.execute(code)
        print("--- Execution Result ---")
        print(f"Success: {result.success}")
        print(f"Output:\n{result.output}")
        print(f"Tool calls: {len(result.tool_calls)}")
        for tc in result.tool_calls:
            print(f"  - {tc['name']}({tc['args']}, {tc['kwargs']})")

        if not result.success:
            print(f"Error: {result.error}")
            print(f"Stderr:\n{result.error_output}")
    else:
        print("No code block found in LLM response.")


if __name__ == "__main__":
    main()
