# ez-ptc Documentation

**Easy Programmatic Tool Calling** — a lightweight, framework-agnostic library for multi-tool execution with any LLM.

## What is ez-ptc?

ez-ptc lets you define Python functions as tools and expose them to any LLM. Instead of registering one tool per function with your framework, you register a **single meta-tool** that accepts Python code. The LLM writes code that calls your tools, uses variables, loops, conditionals — and ez-ptc executes it in a sandboxed environment.

This means the LLM can chain multiple tool calls, handle branching logic, and process results — all in a single round-trip.

```python
from typing import TypedDict
from ez_ptc import Toolkit, ez_tool

class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str

@ez_tool
def get_weather(location: str) -> WeatherResult:
    """Get current weather for a location."""
    return {"location": location, "temp": 22, "unit": "celsius", "condition": "sunny"}

@ez_tool
def search_products(query: str, limit: int = 5) -> list[dict]:
    """Search the product catalog."""
    return [{"name": "Umbrella", "price": 24.99}]

# assist_tool_chaining tells the LLM the exact shape of each tool's return value
toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)
```

With `assist_tool_chaining=True`, the LLM sees return type hints like `# Returns: {location: str, temp: int, unit: str, condition: str}` alongside each tool — so it knows to write `weather["temp"]` instead of guessing `weather["temperature"]`. See [Tool Chaining](tool-chaining.md) for details.

## Documentation

| Page | Description |
|------|-------------|
| [Getting Started](getting-started.md) | Installation, first tool, first toolkit |
| [Concepts](concepts.md) | Core ideas: tools, toolkits, two modes, execution |
| [Prompt Mode](prompt-mode.md) | Framework-free integration via system prompts |
| [Tool Mode](tool-mode.md) | Native framework integration (OpenAI, Anthropic, etc.) |
| [Tool Chaining](tool-chaining.md) | Teach the LLM the exact return shape of each tool — eliminates KeyError guessing |
| [API Reference](api-reference.md) | Full API docs for all public classes and functions |
| [Framework Examples](examples.md) | Integration examples for 7 frameworks |
| [Security & Sandboxing](security.md) | How code execution is sandboxed |

## Quick comparison: Prompt Mode vs Tool Mode

| | Prompt Mode | Tool Mode |
|---|---|---|
| **How it works** | LLM writes code in markdown; you extract and execute | LLM calls a native tool; framework handles the loop |
| **Framework needed** | No | Yes (OpenAI, Anthropic, LangChain, etc.) |
| **Best for** | Simple scripts, raw API calls | Production agents, agentic loops |
| **Setup** | `toolkit.prompt()` in system message | `toolkit.as_tool()` + `toolkit.tool_schema()` + optionally `toolkit.tool_prompt()` |

## Requirements

- Python 3.11+
- No required LLM provider dependencies — bring your own client
