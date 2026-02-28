# ez-ptc

**Easy Programmatic Tool Calling** — a lightweight, zero-dependency, framework-agnostic library for multi-tool execution with any LLM.

[![PyPI version](https://img.shields.io/pypi/v/ez-ptc.svg)](https://pypi.org/project/ez-ptc/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## The problem

Traditional tool calling requires one round-trip per tool call. If the LLM needs to call 3 tools and branch on results, that's 3+ back-and-forth exchanges.

## The solution

ez-ptc exposes a **single meta-tool** that accepts Python code. The LLM writes code that calls multiple tools, uses variables, loops, and conditionals — and ez-ptc executes it in a sandboxed environment. Multiple tool calls, branching logic, and result processing happen in **one round-trip**.

## Installation

```bash
# Using uv (recommended)
uv add ez-ptc

# Using pip
pip install ez-ptc
```

Zero runtime dependencies. Bring your own LLM client.

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

**Prompt mode** — framework-free, inject into any system prompt:

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
result = toolkit.execute(code)
print(result.output)
```

**Tool mode** — native integration with any framework:

```python
from openai import OpenAI
import json

client = OpenAI()
execute_fn = toolkit.as_tool()
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
import asyncio

async def main():
    sf, ny = await asyncio.gather(
        asyncio.to_thread(get_weather, "San Francisco, CA"),
        asyncio.to_thread(get_weather, "New York, NY"),
    )
    print(f"SF: {sf['temp']}°C, {sf['condition']}")
    print(f"NY: {ny['temp']}°C, {ny['condition']}")

asyncio.run(main())
```

Multiple tool calls, parallel execution, variable passing — one round-trip.

## Framework support

ez-ptc works with any LLM provider or framework:

| Framework | Mode | Example |
|-----------|------|---------|
| Raw API (OpenAI, Anthropic) | Prompt or Tool | [prompt mode](examples/example_prompt_mode.py), [openai](examples/example_openai.py), [anthropic](examples/example_anthropic.py) |
| LangChain | Tool | [example](examples/example_langchain.py) |
| Pydantic AI | Tool | [example](examples/example_pydantic_ai.py) |
| LiteLLM | Tool | [example](examples/example_litellm.py) |
| Google GenAI | Tool | [example](examples/example_google_genai.py) |

## Key features

- **Zero dependencies** — pure Python, bring your own LLM client
- **Two modes** — prompt mode (framework-free) or tool mode (native integration)
- **Sandboxed execution** — restricted builtins, no file I/O, no networking, configurable timeout
- **Tool chaining** — `assist_tool_chaining=True` documents return types so the LLM chains outputs correctly
- **Async support** — `asyncio` is pre-imported, LLMs can use `asyncio.gather` for parallel execution

## Documentation

Full documentation is available in the [docs/](docs/) directory:

- [Getting Started](docs/getting-started.md) — installation, first tool, first toolkit
- [Concepts](docs/concepts.md) — tools, toolkits, two modes, execution engine
- [Prompt Mode](docs/prompt-mode.md) — framework-free integration
- [Tool Mode](docs/tool-mode.md) — native framework integration
- [Tool Chaining](docs/tool-chaining.md) — return type documentation for reliable chaining
- [Framework Examples](docs/examples.md) — integration code for 7 frameworks
- [API Reference](docs/api-reference.md) — full API docs
- [Security & Sandboxing](docs/security.md) — execution environment details

## License

[MIT](LICENSE)
