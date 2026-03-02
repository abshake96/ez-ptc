"""Example: MCP Tool Bridge — wrap MCP server tools as ez-ptc tools.

This example demonstrates:
1. Toolkit.from_mcp() — one-liner to discover and wrap all MCP tools
2. tools_from_mcp() — lower-level control with filtering
3. Mixing MCP tools with local @ez_tool functions
4. MCP prompt templates via get_mcp_prompt() / list_mcp_prompts()
5. Resource wrapping (static + templates)
6. Tool chaining with return_schemas

Requirements:
    pip install "ez-ptc[mcp]"

To run with a real MCP server, uncomment the live sections below.
The mock section runs without any server for demonstration purposes.
"""

import asyncio

from ez_ptc import Toolkit, ez_tool
from ez_ptc.mcp import tools_from_mcp, get_mcp_prompt, list_mcp_prompts

# Mock session simulates an MCP server — see _mcp_mock.py for details
from _mcp_mock import mock_session


# ── Local tools to mix with MCP tools ──────────────────────────────────


@ez_tool
def calculate(expression: str) -> str:
    """Evaluate a math expression.

    Args:
        expression: A Python math expression, e.g. "2 + 2"
    """
    return str(eval(expression))  # noqa: S307


@ez_tool
def format_markdown(title: str, items: list) -> str:
    """Format a list of items as a markdown section.

    Args:
        title: Section heading
        items: Items to format as bullet points
    """
    lines = [f"## {title}", ""]
    for item in items:
        lines.append(f"- {item}")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────────────────


async def demo_mock():
    """Run the demo with mock MCP session (no server needed)."""

    session = mock_session()

    # ── 1. One-liner: Toolkit.from_mcp() ──
    print("=" * 60)
    print("1. Toolkit.from_mcp() — discovers everything")
    print("=" * 60)

    toolkit = await Toolkit.from_mcp(session)
    print(f"\nDiscovered {len(toolkit)} tools:")
    for tool in toolkit:
        print(f"  - {tool.signature}: {tool.description}")

    # ── 2. Generate prompt for LLM ──
    print("\n" + "=" * 60)
    print("2. Generated LLM prompt (first 600 chars)")
    print("=" * 60)
    print(toolkit.prompt()[:600] + "...")

    # ── 3. Execute code using MCP tools ──
    print("\n" + "=" * 60)
    print("3. Execute code that calls MCP tools")
    print("=" * 60)

    code = '''
results = search(query="python best practices", limit=3)
print(f"Search returned {len(results)} results")
for r in results:
    print(f"  {r['title']} (score: {r['score']})")
'''
    result = await toolkit.execute(code)
    print(f"\nCode:\n{code}")
    print(f"Output:\n{result.output}")
    print(f"Tool calls: {[tc['name'] for tc in result.tool_calls]}")

    # ── 4. Mix MCP + local tools ──
    print("=" * 60)
    print("4. Mix MCP tools with local tools")
    print("=" * 60)

    toolkit_mixed = await Toolkit.from_mcp(
        session,
        extra_tools=[calculate, format_markdown],
        assist_tool_chaining=True,
    )
    print(f"\nTotal tools: {len(toolkit_mixed)}")
    print(f"  MCP tools: search, get_document, read_system_config, read_user_profile")
    print(f"  Local tools: calculate, format_markdown")

    code = '''
doc = get_document(doc_id="python-101")
result = calculate("len('" + doc["content"] + "')")
print(f"Document '{doc['title']}' has {result} characters")
'''
    result = await toolkit_mixed.execute(code)
    print(f"\nOutput:\n{result.output}")

    # ── 5. Resource tools ──
    print("=" * 60)
    print("5. MCP resources as tools")
    print("=" * 60)

    code = '''
config = read_system_config()
print(f"System version: {config['version']}")
print(f"Max workers: {config['max_workers']}")

profile = read_user_profile(user_id="42")
print(f"User: {profile['name']} ({profile['role']})")
'''
    result = await toolkit.execute(code)
    print(f"\nOutput:\n{result.output}")

    # ── 6. tool_names filter ──
    print("=" * 60)
    print("6. Filter with tool_names")
    print("=" * 60)

    toolkit_filtered = await Toolkit.from_mcp(
        session, tool_names=["search"]
    )
    print(f"\nFiltered to: {[t.name for t in toolkit_filtered.tools]}")

    # ── 7. MCP prompt templates ──
    print("\n" + "=" * 60)
    print("7. MCP prompt templates")
    print("=" * 60)

    prompts = await list_mcp_prompts(session)
    for p in prompts:
        args_str = ", ".join(
            f"{a['name']}{'*' if a['required'] else ''}"
            for a in p["arguments"]
        )
        print(f"\n  {p['name']}: {p['description']}")
        print(f"    Arguments: {args_str}")

    prompt_text = await get_mcp_prompt(
        session, "code_review", {"language": "python", "focus": "security"}
    )
    print(f"\n  Expanded prompt:\n    {prompt_text[:100]}...")

    # ── 8. Tool chaining with return_schemas ──
    print("\n" + "=" * 60)
    print("8. Tool chaining with return_schemas")
    print("=" * 60)

    toolkit_chained = await Toolkit.from_mcp(
        session,
        include_resources=False,
        assist_tool_chaining=True,
        return_schemas={
            "search": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "score": {"type": "number"},
                    },
                },
            },
            "get_document": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    )
    print("\nGenerated prompt with return type hints:")
    prompt = toolkit_chained.prompt()
    # Show just the tool definitions to highlight Returns: comments
    for line in prompt.split("\n"):
        if "def " in line or "# Returns:" in line or '"""' in line:
            print(f"  {line}")

    print("\nExecuting chained code that accesses specific return keys:")
    code = '''
results = search(query="python best practices")
top_hit = results[0]
doc = get_document(doc_id="python-101")
print(f"Top hit: {top_hit['title']} (score: {top_hit['score']})")
print(f"Document: {doc['title']}")
print(f"Content preview: {doc['content'][:40]}...")
'''
    result = await toolkit_chained.execute(code)
    print(f"  Output:\n{result.output}")
    print(f"  Tool calls: {[tc['name'] for tc in result.tool_calls]}")


async def demo_live():
    """Run with a real MCP server (uncomment to use).

    Requires an MCP server. Example with the 'everything' test server:
        npx -y @modelcontextprotocol/server-everything
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-everything"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Create toolkit from MCP + local tools
            toolkit = await Toolkit.from_mcp(
                session,
                extra_tools=[calculate, format_markdown],
                assist_tool_chaining=True,
            )

            print(f"Discovered {len(toolkit)} tools:")
            for tool in toolkit:
                print(f"  - {tool.signature}: {tool.description}")

            # Generate LLM prompt
            print(f"\nPrompt preview:\n{toolkit.prompt()[:500]}...")

            # List available prompts
            prompts = await list_mcp_prompts(session)
            print(f"\nAvailable prompts: {[p['name'] for p in prompts]}")


async def main():
    print("ez-ptc MCP Tool Bridge Demo")
    print("Using mock MCP session (no server required)\n")
    await demo_mock()

    # Uncomment to run with a real MCP server:
    # print("\n\n--- Live MCP Server ---\n")
    # await demo_live()


if __name__ == "__main__":
    asyncio.run(main())
