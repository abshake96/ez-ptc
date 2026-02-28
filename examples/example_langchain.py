"""ez-ptc + LangChain — Tool mode example.

Uses toolkit.as_tool() wrapped with LangChain's @tool decorator,
then bound to a chat model via bind_tools().

Also shows the difference between assist_tool_chaining=True and False.

Usage:
    uv run python examples/example_langchain.py

Requires:
    OPENAI_API_KEY in .env or environment
    pip install langchain-openai langchain-core
"""

from dotenv import load_dotenv

from shared_tools import USER_PROMPT, toolkit, toolkit_basic

load_dotenv()


def main():
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool as langchain_tool
    from langchain_openai import ChatOpenAI

    # ── Compare: with vs without tool chaining ──────────────────────
    # LangChain reads the docstring from as_tool(), so the difference
    # shows up in what the LLM sees as the tool description.
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
    # Wrap ez-ptc's meta-tool with LangChain's @tool decorator
    execute_fn = toolkit.as_tool()

    @langchain_tool
    def execute_tools(code: str) -> str:
        """Execute Python code with access to tools."""
        return execute_fn(code)

    tools = [execute_tools]
    tools_by_name = {t.name: t for t in tools}

    llm = ChatOpenAI(model="gpt-4.1-mini")
    llm_with_tools = llm.bind_tools(tools)

    messages = [
        SystemMessage(content=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"),
        HumanMessage(content=USER_PROMPT),
    ]

    print(f"User: {USER_PROMPT}\n")

    # Agentic loop
    for turn in range(10):
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)

        if ai_msg.tool_calls:
            for tc in ai_msg.tool_calls:
                print(f"[Tool call] {tc['name']}(code=...)")
                print(f"  Code:\n{_indent(tc['args'].get('code', ''))}")

                tool_obj = tools_by_name[tc["name"]]
                result = tool_obj.invoke(tc["args"])
                print(f"  Result:\n{_indent(str(result))}\n")

                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        else:
            print(f"Assistant: {ai_msg.content}")
            break


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.strip().split("\n"))


if __name__ == "__main__":
    main()
