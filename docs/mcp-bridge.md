# MCP Tool Bridge

The MCP Tool Bridge lets you wrap tools and resources from any [Model Context Protocol](https://modelcontextprotocol.io/) server as native ez-ptc `Tool` objects. This means any MCP server -- file systems, databases, APIs, dev tools -- can be used inside an ez-ptc `Toolkit`, gaining sandboxed execution, tool chaining, and multi-tool orchestration for free.

## Installation

The MCP bridge requires the `mcp` package as an optional dependency:

```bash
# Using uv
uv add "ez-ptc[mcp]"

# Using pip
pip install "ez-ptc[mcp]"
```

The core `ez-ptc` library remains zero-dependency. The `mcp` extra is only needed when you use `Toolkit.from_mcp()` or import from `ez_ptc.mcp`.

## Why bridge MCP to ez-ptc?

MCP servers expose tools one-at-a-time -- each LLM turn calls a single tool. ez-ptc's programmatic tool calling lets the LLM write code that calls **multiple** MCP tools in a single round-trip, with variables, branching, and parallel execution:

```python
# Instead of 3 separate LLM turns, the LLM writes one code block:
readme, issues = parallel(
    (read_readme, "myorg/myrepo"),
    (search_issues, "bug", "open"),
)
print(f"README length: {len(readme)}")
print(f"Open bugs: {len(issues)}")
```

## Quick start

### One-liner: `Toolkit.from_mcp()`

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ez_ptc import Toolkit

server = StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-everything"])

async with stdio_client(server) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # One line -- discovers all tools + resources
        toolkit = await Toolkit.from_mcp(session)

        # Use like any other toolkit
        prompt = toolkit.prompt()
        result = await toolkit.execute('r = echo(message="hello")\nprint(r)')
```

### Lower-level: `tools_from_mcp()`

For more control -- filtering, mixing with local tools, inspecting before building:

```python
from ez_ptc import Toolkit, ez_tool
from ez_ptc.mcp import tools_from_mcp

@ez_tool
def calculate(expression: str) -> str:
    """Evaluate a math expression locally."""
    return str(eval(expression))

async with ClientSession(read, write) as session:
    await session.initialize()

    # Get MCP tools separately
    mcp_tools = await tools_from_mcp(session, tool_names=["search", "fetch"])

    # Mix with local tools
    toolkit = Toolkit(
        mcp_tools + [calculate],
        assist_tool_chaining=True,
    )
```

## What gets wrapped

The bridge wraps three MCP primitives as ez-ptc `Tool` objects:

| MCP Primitive | ez-ptc Mapping | Tool Name |
|---|---|---|
| **Tools** | `Tool` with async wrapper around `session.call_tool()` | Same as MCP tool name |
| **Static Resources** | Zero-arg `Tool` calling `session.read_resource(uri)` | `read_{sanitized_name}` |
| **Resource Templates** | `Tool` with args from URI template variables, calling `session.read_resource()` | `query_{sanitized_name}` |

Names are deduplicated across all categories — if a collision occurs, `_2`, `_3`, etc. are appended automatically.

**Prompts** are NOT wrapped as tools. They're accessed separately via `get_mcp_prompt()` -- see [Prompt templates](#prompt-templates) below.

### Tools

MCP tools are wrapped with full signature information. The wrapper:
- Accepts both positional and keyword arguments (LLM code may call `add(1, 2)` or `add(a=1, b=2)`)
- JSON-parses text results when valid, otherwise returns raw strings
- Raises `RuntimeError` on MCP errors (`isError=True`), which the sandbox captures as traceback for LLM self-correction
- Passes `outputSchema` as `return_schema` on the ez-ptc `Tool` (enables `assist_tool_chaining` hints)

```python
# MCP tool: search(query: str, limit: int = 10) -> results
# LLM can call it naturally:
results = search("weather API", limit=5)
print(results)
```

### Static resources

Static resources (fixed URIs) become zero-argument tools:

```python
# MCP resource: "Application Config" at config://app
# Becomes: read_application_config()
config = read_application_config()
print(config["database"]["host"])
```

### Resource templates

Resource templates with URI variables become parameterized tools:

```python
# MCP template: "User Profile" at users/{user_id}/profile
# Becomes: query_user_profile(user_id: str)  (templates use query_ prefix)
profile = query_user_profile(user_id="42")
print(profile["name"])
```

## Filtering tools

Use `tool_names` to select only the tools you need:

```python
# Only wrap specific MCP tools
toolkit = await Toolkit.from_mcp(
    session,
    tool_names=["search", "fetch", "read_config"],
)

# Or skip resources entirely
toolkit = await Toolkit.from_mcp(session, include_resources=False)
```

The `tool_names` filter applies to all wrapped tools -- MCP tools, static resources, and resource templates.

## Mixing MCP and local tools

Use `extra_tools` to add local `@ez_tool` functions alongside MCP tools:

```python
from ez_ptc import Toolkit, ez_tool

@ez_tool
def format_report(data: dict) -> str:
    """Format data as a markdown report."""
    lines = [f"- **{k}**: {v}" for k, v in data.items()]
    return "\n".join(lines)

toolkit = await Toolkit.from_mcp(
    session,
    extra_tools=[format_report],
    assist_tool_chaining=True,
    timeout=60.0,
)
```

All `Toolkit` constructor kwargs (`preamble`, `postamble`, `assist_tool_chaining`, `timeout`, `sandbox`, `error_hint`) are passed through.

## Prompt templates

MCP prompt templates are NOT wrapped as tools. They're expanded text meant for system prompts, not tool calls. Use the utility functions to work with them:

### `get_mcp_prompt()` -- fetch and expand a prompt

```python
from ez_ptc.mcp import get_mcp_prompt

# Expand a named prompt with arguments
system_text = await get_mcp_prompt(
    session,
    "code_review",
    arguments={"language": "python", "style": "concise"},
)

# Use in your system prompt
messages = [
    {"role": "system", "content": system_text},
    {"role": "user", "content": "Review this code: ..."},
]
```

### `list_mcp_prompts()` -- discover available prompts

```python
from ez_ptc.mcp import list_mcp_prompts

prompts = await list_mcp_prompts(session)
for p in prompts:
    print(f"{p['name']}: {p['description']}")
    for arg in p["arguments"]:
        req = " (required)" if arg["required"] else ""
        print(f"  - {arg['name']}{req}: {arg['description']}")
```

## Tool chaining with `return_schemas`

When `assist_tool_chaining=True`, ez-ptc adds `# Returns:` comments to prompts so the LLM knows the return structure and can safely chain results (e.g. `results[0]["title"]`).

For native ez-ptc tools, return schemas are inferred from type annotations. For MCP tools, there are two sources:

1. **`outputSchema`** — The MCP-native way. If an MCP server sets `outputSchema` on a tool, ez-ptc picks it up automatically. However, `outputSchema` was added recently to the spec and most servers don't set it yet.
2. **`return_schemas`** — A user-provided dict mapping tool names to JSON Schema dicts. This lets you explicitly declare return types for MCP tools that lack `outputSchema`.

**Priority:** user `return_schemas` > MCP `outputSchema` > None.

```python
toolkit = await Toolkit.from_mcp(
    session,
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
```

The generated prompt will include return type hints:

```
def search(query: str, limit: int = 5):
    """Search the knowledge base"""
    # Returns: list[dict(title: str, score: float)]
```

This lets the LLM safely chain results:

```python
results = search(query="python async")
doc = get_document(doc_id=results[0]["title"])
print(doc["content"])
```

`return_schemas` also works on resource tool names (e.g. `"read_config"` for static resources, `"query_user_profile"` for templates).

## Overriding descriptions

MCP servers often have generic or unhelpful tool descriptions. Use `descriptions` to override them per tool, improving LLM prompt adherence:

```python
toolkit = await Toolkit.from_mcp(
    session,
    descriptions={
        "search": "Search the knowledge base. Returns a list of matching documents with title and score.",
        "read_config": "System configuration as a JSON dict with keys: version, max_workers, debug.",
        "query_user_profile": "Fetch a user profile by ID. Returns dict with name, email, role.",
    },
)
```

Tools without a `descriptions` entry keep their original MCP server description. The `descriptions` kwarg works on all three categories — tools, static resources (`read_`), and templates (`query_`).

The lower-level `tools_from_mcp()` accepts the same `descriptions` parameter.

## Lower-level `tools_from_mcp()`

The lower-level `tools_from_mcp()` accepts the same `return_schemas` and `descriptions` parameters:

```python
from ez_ptc.mcp import tools_from_mcp

mcp_tools = await tools_from_mcp(
    session,
    return_schemas={"search": {"type": "object", "properties": {...}}},
)
toolkit = Toolkit(mcp_tools, assist_tool_chaining=True)
```

## Sync usage

For sync contexts, use `from_mcp_sync()`:

```python
toolkit = Toolkit.from_mcp_sync(session, include_resources=False)
result = toolkit.execute_sync('print(search(query="test"))')
```

## Session lifecycle

ez-ptc does **not** own the MCP connection. You manage the session lifecycle:

```python
async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # Create toolkit while session is active
        toolkit = await Toolkit.from_mcp(session)

        # Use toolkit while session is active
        result = await toolkit.execute(code)

    # Session closed here -- toolkit tools will fail if called
```

The toolkit captures a reference to the session. Tool calls route through `session.call_tool()` and `session.read_resource()`, so the session must remain open for the toolkit's lifetime.

## How it works with the executor

MCP tool wrappers are async functions. When the LLM's code calls an MCP tool inside `toolkit.execute()`, the execution flow is:

```
toolkit.execute(code)
  → LocalSandbox.execute() captures the event loop
    → asyncio.to_thread(execute_code, ..., loop)
      → LLM code calls mcp_tool_wrapper(...)
        → wrapper is async, so run_coroutine_threadsafe(coro, loop)
          → session.call_tool() runs on the original event loop
```

This works because `LocalSandbox` already handles async tool dispatch via `run_coroutine_threadsafe`. No changes to the executor were needed for MCP support.

## Complete example

```python
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ez_ptc import Toolkit, ez_tool
from ez_ptc.mcp import get_mcp_prompt, list_mcp_prompts

@ez_tool
def summarize(text: str, max_words: int = 50) -> str:
    """Summarize text to a maximum word count."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."

async def main():
    server = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Create toolkit from MCP + local tools
            toolkit = await Toolkit.from_mcp(
                session,
                extra_tools=[summarize],
                assist_tool_chaining=True,
            )

            # See what's available
            print(f"Tools: {[t.name for t in toolkit.tools]}")
            print(f"\nPrompt preview:\n{toolkit.prompt()[:500]}...")

            # Check available prompts
            prompts = await list_mcp_prompts(session)
            for p in prompts:
                print(f"Prompt: {p['name']} - {p['description']}")

            # Execute code that uses MCP tools
            code = '''
files = list_directory(path="/tmp")
print(f"Files in /tmp: {len(files)}")
for f in files[:5]:
    print(f"  {f}")
'''
            result = await toolkit.execute(code)
            print(f"\nOutput:\n{result.output}")

asyncio.run(main())
```

## API summary

| Function / Method | Description |
|---|---|
| `Toolkit.from_mcp(session, **kwargs)` | Create a Toolkit from an MCP session (async) |
| `Toolkit.from_mcp_sync(session, **kwargs)` | Sync version of `from_mcp()` |
| `tools_from_mcp(session, *, tool_names, include_resources, return_schemas, descriptions)` | Discover and wrap MCP tools/resources as `Tool` objects |
| `get_mcp_prompt(session, name, arguments)` | Fetch and expand an MCP prompt template |
| `list_mcp_prompts(session)` | List available prompts with argument info |

See [API Reference](api-reference.md) for full parameter details.

## See also

- [Getting Started](getting-started.md) -- installation and first toolkit
- [Concepts](concepts.md) -- tools, toolkits, execution engine
- [Tool Chaining](tool-chaining.md) -- return type documentation for MCP tools with `outputSchema`
- [Framework Examples](examples.md) -- using MCP toolkits with OpenAI, LangChain, etc.
