# Getting Started

## Installation

```bash
# Using uv (recommended)
uv add ez-ptc

# Using pip
pip install ez-ptc
```

## Define your first tools

Use the `@ez_tool` decorator to wrap any Python function. ez-ptc reads type hints and docstrings automatically.

```python
from typing import TypedDict
from ez_ptc import ez_tool

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
    # Your actual implementation here (API call, database query, etc.)
    return {"location": location, "temp": 22, "unit": unit, "condition": "sunny"}

@ez_tool
def search_products(query: str, limit: int = 5) -> list[dict]:
    """Search the product catalog.

    Args:
        query: Search query string
        limit: Maximum number of results to return
    """
    return [{"id": 1, "name": "Umbrella", "price": 24.99}]
```

What `@ez_tool` does:
- Extracts the function name, description (from docstring), and parameter schemas (from type hints)
- Auto-detects return type schemas from `TypedDict` and Pydantic `BaseModel` annotations
- Returns a `Tool` object that is still callable like the original function
- Supports Google-style docstrings for parameter descriptions

Using `TypedDict` (or Pydantic) return types is recommended — it enables [tool chaining](#enable-tool-chaining) so the LLM knows the exact shape of each tool's output.

## Create a Toolkit

Group your tools into a `Toolkit`:

```python
from ez_ptc import Toolkit

toolkit = Toolkit([get_weather, search_products])
```

## Choose your mode

### Option A: Prompt Mode (no framework needed)

Inject tool descriptions into your system prompt. The LLM writes code in a markdown block, you extract and execute it.

```python
# 1. Generate system prompt instructions
prompt = toolkit.prompt()

# 2. Send to any LLM (shown with OpenAI, but works with any API)
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": "What's the weather in NYC?"},
    ],
)

# 3. Extract code from LLM response
code = toolkit.extract_code(response.choices[0].message.content)

# 4. Execute safely
result = toolkit.execute(code)
print(result.output)       # Captured stdout
print(result.tool_calls)   # Log of which tools were called
```

See [Prompt Mode](prompt-mode.md) for the full guide.

### Option B: Tool Mode (framework integration)

Register a single meta-tool with your framework. The LLM calls it natively.

```python
# Get a callable function and its schema
execute_fn = toolkit.as_tool()
tool_schema = toolkit.tool_schema(format="openai")  # or "anthropic"

# Register with your framework and let the agentic loop handle it
# See examples for OpenAI, Anthropic, LangChain, Pydantic AI, etc.
```

The tool schema and `as_tool()` docstring already instruct the LLM to combine all operations into a single code block. If your model still makes multiple separate calls (common with models that support parallel tool calling), add `tool_prompt()` to your system prompt:

```python
system_message = f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"
```

See [Tool Mode](tool-mode.md) for integration guides.

## What the LLM sees

When the LLM receives your tools (in either mode), it can write code like this:

```python
# Check weather in two cities
sf_weather = get_weather("San Francisco, CA")
ny_weather = get_weather("New York, NY")

# Decide what to search based on conditions
if sf_weather["condition"] == "rainy":
    products = search_products("umbrellas", limit=3)
else:
    products = search_products("sunglasses", limit=3)

print(f"SF: {sf_weather['condition']}, NY: {ny_weather['condition']}")
print(f"Found {len(products)} products")
```

This is the key advantage: **multiple tool calls, branching logic, and result processing in a single execution** — no multi-turn back-and-forth needed.

## Enable tool chaining

There's a problem with the code above: how does the LLM know the weather dict has a key called `"condition"` and not `"weather_status"`? Or that it's `"temp"` and not `"temperature"`? Without knowing return types, the LLM guesses — and often guesses wrong, causing `KeyError` at runtime.

**Tool chaining** solves this. When you use `TypedDict` (or Pydantic) return types, ez-ptc can document the exact return shape for the LLM:

```python
toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)
```

Now the LLM sees each tool annotated with its return structure:

```python
def get_weather(location: str, unit: str = 'celsius') -> WeatherResult:
    """Get current weather for a location.
    ...
    """
    # Returns: {location: str, temp: int, unit: str, condition: str}
```

The LLM now knows the exact keys and types — `weather["temp"]`, `weather["condition"]` — and can chain tool outputs confidently without guessing.

This works in all three output methods: `prompt()`, `as_tool()`, and `tool_schema()`. You can also provide explicit schemas for tools that return plain `dict`:

```python
@ez_tool(return_schema={"type": "object", "properties": {
    "location": {"type": "string"},
    "temp": {"type": "integer"},
}})
def get_weather(location: str) -> dict:
    ...
```

See [Tool Chaining](tool-chaining.md) for the full guide.

## Next steps

- [Concepts](concepts.md) — understand the core architecture
- [Tool Chaining](tool-chaining.md) — TypedDict, Pydantic, and explicit return schemas
- [Framework Examples](examples.md) — copy-paste integration code
