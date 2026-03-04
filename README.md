# ez-ptc

**Easy Programmatic Tool Calling** -- a lightweight, zero-dependency, framework-agnostic library for multi-tool execution with any LLM.

[![PyPI version](https://img.shields.io/pypi/v/ez-ptc.svg)](https://pypi.org/project/ez-ptc/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## What is programmatic tool calling?

The idea of **programmatic tool calling** (PTC) was introduced by Anthropic. Instead of the traditional pattern where an LLM makes one tool call per turn, the LLM writes code that calls multiple tools, uses variables, branches on results, and loops -- all executed in a single round-trip. Anthropic described this approach in their [engineering blog post](https://www.anthropic.com/engineering/advanced-tool-use) and provides a [first-party implementation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/computer-use#programmatic-tool-use) for the Claude API.

ez-ptc takes this pattern and makes it easy to use with **any LLM provider** -- OpenAI, Anthropic, Google, Groq, or any framework that talks to them.

## Why ez-ptc?

- **Works with any LLM provider** -- OpenAI, Anthropic, Google, Groq, LiteLLM, and more. Not locked to a single API.
- **Zero dependencies** -- pure Python, no runtime dependencies. Bring your own LLM client.
- **Two modes** -- prompt mode (inject into any system prompt, no framework needed) or tool mode (native integration with OpenAI, LangChain, Pydantic AI, etc.).
- **MCP support** -- wrap tools from any MCP server with one line: `Toolkit.from_mcp(session)`.
- **Tool chaining with return types** -- documents the exact return shape of each tool so the LLM doesn't guess wrong keys and cause `KeyError` at runtime.

## Installation

```bash
# Using uv (recommended)
uv add ez-ptc

# Using pip
pip install ez-ptc
```

Zero runtime dependencies. Bring your own LLM client.

For [MCP server integration](#mcp-tool-bridge):

```bash
uv add "ez-ptc[mcp]"
# or: pip install "ez-ptc[mcp]"
```

## Quick start

### 1. Define tools

```python
from typing import TypedDict
from ez_ptc import Toolkit, ez_tool

class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str

@ez_tool
def get_weather(location: str, unit: str = "celsius") -> WeatherResult:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    # Your actual API call here
    return {"location": location, "temp": 22, "unit": unit, "condition": "sunny"}

@ez_tool
def search_products(query: str, limit: int = 5) -> list[dict]:
    """Search the product catalog.

    Args:
        query: Search query string
        limit: Maximum number of results
    """
    return [{"name": "Umbrella", "price": 24.99}]

toolkit = Toolkit([get_weather, search_products])
```

### 2. Choose your mode

**Prompt mode** -- framework-free, inject into any system prompt:

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[
        {"role": "system", "content": toolkit.prompt()},
        {"role": "user", "content": "What's the weather in NYC and SF?"},
    ],
)

code = toolkit.extract_code(response.choices[0].message.content)
result = toolkit.execute_sync(code)
print(result.output)
```

**Tool mode** -- native integration with any framework:

```python
from openai import OpenAI
import json

client = OpenAI()
execute_fn = toolkit.as_tool_sync()
tool_schema = toolkit.tool_schema(format="openai")

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the weather in NYC and SF?"},
]

for turn in range(10):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=[tool_schema],
    )
    choice = response.choices[0]
    if choice.message.tool_calls:
        messages.append(choice.message)
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_fn(**args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    else:
        print(choice.message.content)
        break
```

## What the LLM writes

Instead of separate tool calls, the LLM writes a single code block:

```python
# Built-in parallel() helper runs tools concurrently
sf, ny = parallel(
    (get_weather, "San Francisco, CA"),
    (get_weather, "New York, NY"),
)
print(f"SF: {sf['temp']}°C, {sf['condition']}")
print(f"NY: {ny['temp']}°C, {ny['condition']}")
```

Multiple tool calls, parallel execution, variable passing -- one round-trip.

## Tool chaining

When the LLM chains tool outputs -- passing the result of one tool into a conditional or another tool call -- it needs to know the exact shape of each return value. Without that information, the LLM guesses key names, and guesses are often wrong:

```python
# The LLM writes this...
weather = get_weather("San Francisco, CA")
print(weather["temperature"])  # KeyError! The actual key is "temp"
```

**The fix:** use `TypedDict` return types (or Pydantic `BaseModel`) and enable `assist_tool_chaining`:

```python
toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)
```

Now the LLM sees return type annotations alongside each tool:

```python
def get_weather(location: str, unit: str = 'celsius') -> WeatherResult:
    """Get current weather for a location.
    ...
    """
    # Returns: {location: str, temp: int, unit: str, condition: str}
```

The LLM knows the exact keys and types -- `weather["temp"]`, `weather["condition"]` -- and can chain tool outputs without guessing. This works in all three output methods: `prompt()`, `as_tool()`, and `tool_schema()`.

See [Tool Chaining](docs/tool-chaining.md) for TypedDict, Pydantic, and explicit schema examples.

## Framework support

ez-ptc works with any LLM provider or framework:

| Framework | Mode | Example |
|-----------|------|---------|
| Raw API (OpenAI, Anthropic) | Prompt or Tool | [prompt mode](examples/prompt_mode/example_prompt_mode.py), [openai](examples/frameworks/example_openai.py), [anthropic](examples/frameworks/example_anthropic.py) |
| LangChain | Tool | [example](examples/frameworks/example_langchain.py) |
| Pydantic AI | Tool | [example](examples/frameworks/example_pydantic_ai.py) |
| LiteLLM | Tool | [example](examples/frameworks/example_litellm.py) |
| Google GenAI | Tool | [example](examples/frameworks/example_google_genai.py) |
| MCP servers | Tool or Prompt | [example](examples/advanced/example_mcp_bridge.py), [docs](docs/mcp-bridge.md) |

## MCP Tool Bridge

ez-ptc can wrap tools from any [MCP](https://modelcontextprotocol.io/) server -- file systems, databases, APIs, dev tools -- and use them in a `Toolkit`. The LLM can then call multiple MCP tools in a single round-trip, with variables, branching, and parallel execution.

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ez_ptc import Toolkit

server = StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-everything"])

async with stdio_client(server) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # One line -- discovers all tools and resources
        toolkit = await Toolkit.from_mcp(session)

        # Use like any other toolkit
        result = await toolkit.execute('r = echo(message="hello")\nprint(r)')
```

What gets wrapped:
- **MCP Tools** -- wrapped as `Tool` objects with full signature and positional arg support
- **Static Resources** -- wrapped as zero-arg tools (e.g. `read_config()`)
- **Resource Templates** -- wrapped as parameterized tools (e.g. `query_user_profile(user_id="42")`)
- **Prompts** -- not tools; accessed via `get_mcp_prompt()` for system prompt injection

Mix MCP tools with local `@ez_tool` functions:

```python
toolkit = await Toolkit.from_mcp(
    session,
    extra_tools=[my_local_tool],
    assist_tool_chaining=True,
)
```

Requires `pip install ez-ptc[mcp]`. The core library stays zero-dependency. See the [MCP Bridge docs](docs/mcp-bridge.md) for the full guide.

## How ez-ptc compares to Anthropic's native PTC

Anthropic offers [first-party programmatic tool calling](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/computer-use#programmatic-tool-use) through their API. It runs in a managed container and is tightly integrated with the Claude model.

ez-ptc takes a different approach:

- **Any LLM provider** -- works with OpenAI, Anthropic, Google, Groq, or any API. Anthropic's native PTC is Claude-only.
- **Any framework** -- integrates with LangChain, Pydantic AI, LiteLLM, or plain HTTP calls. No vendor lock-in.
- **Zero dependencies** -- pure Python, no managed containers, no external services. Runs entirely in your process.
- **Full sandbox control** -- you configure the execution environment: allowed builtins, timeouts, and what the LLM can access.

If you are already using the Claude API and want a managed solution, Anthropic's native PTC is a good choice. If you want provider flexibility, local execution, or framework integration, ez-ptc fills that gap.

## Key features

- **Zero dependencies** -- pure Python, bring your own LLM client
- **Two modes** -- prompt mode (framework-free) or tool mode (native integration)
- **MCP Tool Bridge** -- wrap any MCP server's tools and resources as native ez-ptc tools with `Toolkit.from_mcp()`
- **Sandboxed execution** -- restricted builtins, no file I/O, no networking, configurable timeout
- **Tool chaining** -- `assist_tool_chaining=True` documents return types so the LLM chains outputs correctly
- **Parallel execution** -- built-in `parallel()` helper lets LLMs run tools concurrently with a simple `parallel((tool, arg), ...)` pattern
- **Async tool support** -- `async def` tools auto-detected and handled transparently; no special LLM-side code needed

## Documentation

Full documentation is available in the [docs/](docs/) directory:

- [Getting Started](docs/getting-started.md) -- installation, first tool, first toolkit
- [Concepts](docs/concepts.md) -- tools, toolkits, two modes, execution engine
- [Prompt Mode](docs/prompt-mode.md) -- framework-free integration
- [Tool Mode](docs/tool-mode.md) -- native framework integration
- [MCP Tool Bridge](docs/mcp-bridge.md) -- wrap MCP server tools/resources as ez-ptc tools
- [Tool Chaining](docs/tool-chaining.md) -- return type documentation for reliable chaining
- [Framework Examples](docs/examples.md) -- integration code for 7+ frameworks
- [API Reference](docs/api-reference.md) -- full API docs
- [Security & Sandboxing](docs/security.md) -- execution environment details

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

Quick setup:

```bash
git clone https://github.com/abhisheksatish/ez-ptc.git
cd ez-ptc
uv sync
uv run pytest tests/
```

Found a bug or have a feature request? [Open an issue](https://github.com/abhisheksatish/ez-ptc/issues).

## License

[MIT](LICENSE)
