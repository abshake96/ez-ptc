"""ez-ptc — Multi-turn error recovery in prompt mode.

Demonstrates a prompt-mode loop where execution errors are fed back
to the LLM so it can self-correct. Uses the OpenAI API.

Usage:
    uv run python examples/prompt_mode/example_error_recovery.py

Requires:
    OPENAI_API_KEY in .env or environment
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from openai import OpenAI

from shared_tools import toolkit

load_dotenv()

MAX_ATTEMPTS = 3

# A prompt that's likely to produce an initial mistake
USER_PROMPT = (
    "Check the weather in London, UK. If it's rainy, search for "
    "umbrellas and rain jackets. If it's sunny, search for sunglasses. "
    "Print a formatted summary with the weather and matching products."
)


def main():
    client = OpenAI()
    tool_instructions = toolkit.prompt()

    messages = [
        {"role": "system", "content": tool_instructions},
        {"role": "user", "content": USER_PROMPT},
    ]

    print(f"User: {USER_PROMPT}\n")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"--- Attempt {attempt} ---")

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
        )

        llm_text = response.choices[0].message.content
        messages.append({"role": "assistant", "content": llm_text})

        # Extract code from the LLM response
        code = toolkit.extract_code(llm_text)
        if not code:
            print(f"  LLM response (no code): {llm_text[:100]}...")
            print("  No code block found — accepting text response.")
            break

        print(f"  Code:\n{_indent(code)}")

        # Execute with validation
        result = toolkit.execute_sync(code)

        if result.success:
            print(f"  Output:\n{_indent(result.output)}")
            print(f"  Tool calls: {[tc['name'] for tc in result.tool_calls]}")
            break
        else:
            # Feed the error back to the LLM for self-correction
            error_feedback = result.to_string()
            print(f"  Error: {error_feedback[:120]}...")

            correction_msg = (
                f"The code produced an error:\n```\n{error_feedback}\n```\n"
                f"Please fix the code and try again."
            )
            messages.append({"role": "user", "content": correction_msg})
            print(f"  Feeding error back to LLM...\n")
    else:
        print(f"\nFailed after {MAX_ATTEMPTS} attempts.")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    main()
