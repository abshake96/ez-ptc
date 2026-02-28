"""ez-ptc + Pydantic AI — Tool mode example.

Uses toolkit.as_tool() registered as a Pydantic AI Tool on an Agent.
Pydantic AI handles the tool-calling loop automatically.

Also shows the difference between assist_tool_chaining=True and False.

Usage:
    uv run python examples/example_pydantic_ai.py

Requires:
    OPENAI_API_KEY in .env or environment
    pip install pydantic-ai
"""

from dotenv import load_dotenv

from shared_tools import USER_PROMPT, toolkit, toolkit_basic

load_dotenv()


def main():
    from pydantic_ai import Agent, Tool

    # ── Compare: with vs without tool chaining ──────────────────────
    print("=" * 60)
    print("COMPARISON: Meta-tool docstring sent to the LLM")
    print("=" * 60)

    basic_doc = toolkit_basic.as_tool().__doc__
    chained_doc = toolkit.as_tool().__doc__

    print("\n--- Without assist_tool_chaining ---")
    print(basic_doc)

    print("\n--- With assist_tool_chaining ---")
    print(chained_doc)

    print("\n" + "=" * 60)
    print("The chaining-enabled version includes 'Returns: {...}' hints")
    print("so the LLM knows the exact shape of each tool's output.")
    print("=" * 60 + "\n")

    # ── Main flow: uses the chaining-enabled toolkit ────────────────
    # Wrap ez-ptc's meta-tool as a Pydantic AI Tool
    execute_fn = toolkit.as_tool()
    pydantic_tool = Tool(execute_fn, takes_ctx=False)

    agent = Agent(
        "openai:gpt-4.1-mini",
        system_prompt=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}",
        tools=[pydantic_tool],
    )

    print(f"User: {USER_PROMPT}\n")

    # Pydantic AI handles the agentic loop automatically
    result = agent.run_sync(USER_PROMPT)

    print(f"Assistant: {result.output}")


if __name__ == "__main__":
    main()
