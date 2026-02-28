# Tool Chaining

When an LLM chains tool outputs (e.g., passes `get_weather()` result into conditional logic), it needs to know the **shape** of return values. Without this, the LLM might try `weather.get('temperature')` when the actual key is `'temp'`.

The `assist_tool_chaining` feature adds opt-in return schema documentation so the LLM knows the exact structure each tool returns.

## Enabling tool chaining

```python
toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)
```

When `False` (default): no change to current behavior.
When `True`: return schema info is appended to tool listings in `prompt()`, `as_tool()`, and `tool_schema()`.

## Providing return schemas

There are two ways to document return types:

### 1. Auto-detected via TypedDict

Define a `TypedDict` for your return type and use it as the return annotation:

```python
from typing import TypedDict
from ez_ptc import ez_tool

class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str

@ez_tool
def get_weather(location: str) -> WeatherResult:
    """Get weather for a location."""
    return {"location": location, "temp": 22, "unit": "celsius", "condition": "sunny"}
```

ez-ptc reads the TypedDict's fields and types automatically. This also works with Pydantic `BaseModel` return types.

### 2. Auto-detected via Pydantic BaseModel

```python
from pydantic import BaseModel
from ez_ptc import ez_tool

class WeatherResult(BaseModel):
    location: str
    temp: int
    unit: str
    condition: str

@ez_tool
def get_weather(location: str) -> WeatherResult:
    """Get weather for a location."""
    return WeatherResult(location=location, temp=22, unit="celsius", condition="sunny")
```

### 3. Explicit override

For tools that return plain `dict`, you can pass the schema directly:

```python
@ez_tool(return_schema={
    "type": "object",
    "properties": {
        "location": {"type": "string"},
        "temp": {"type": "integer"},
        "unit": {"type": "string"},
        "condition": {"type": "string"},
    },
})
def get_weather(location: str) -> dict:
    """Get weather for a location."""
    return {"location": location, "temp": 22, "unit": "celsius", "condition": "sunny"}
```

An explicit `return_schema` always takes priority over auto-detection.

### What gets skipped

Return types that aren't useful for chaining produce no schema:

- `-> dict` (plain dict, no structure info)
- `-> list` (plain list)
- `-> str`, `-> int`, `-> float`, `-> bool` (primitives)
- `-> list[dict]` (list of unstructured dicts)
- No return annotation

These return `None` for `return_schema`, and no hint is shown to the LLM.

## What the LLM sees

### In `prompt()` output

```
def get_weather(location: str, unit: str = 'celsius') -> WeatherResult:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    # Returns: {location: str, temp: int, unit: str, condition: str}

def search_products(query: str, limit: int = 5) -> list[ProductResult]:
    """Search the product catalog.

    Args:
        query: Search query string
        limit: Maximum number of results to return
    """
    # Returns: list[{id: int, name: str, price: float, tags: list[str]}]
```

The `# Returns:` comment uses a compact, Python-dict-like notation that's easy for LLMs to parse.

### In `as_tool()` docstring and `tool_schema()` description

Return info is appended with a `|` separator:

```
- get_weather(location: str, unit: str = 'celsius') -> WeatherResult
  Get current weather for a location. | Returns: {location: str, temp: int, unit: str, condition: str}
```

## Supported return type structures

| Return type | Schema generated? | Example output |
|-------------|-------------------|----------------|
| `-> WeatherResult` (TypedDict) | Yes | `{location: str, temp: int, ...}` |
| `-> WeatherModel` (Pydantic) | Yes | `{location: str, temp: int, ...}` |
| `-> list[Product]` (list of TypedDict) | Yes | `list[{id: int, name: str, ...}]` |
| `-> list[ProductModel]` (list of Pydantic) | Yes | `list[{id: int, name: str, ...}]` |
| `-> dict` | No | — |
| `-> list[dict]` | No | — |
| `-> str` | No | — |
| No annotation | No | — |

## Example: full workflow with chaining

```python
from typing import TypedDict
from ez_ptc import Toolkit, ez_tool

class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str

class ProductResult(TypedDict):
    id: int
    name: str
    price: float
    tags: list[str]

@ez_tool
def get_weather(location: str) -> WeatherResult:
    """Get weather for a location."""
    return {"location": location, "temp": 22, "unit": "celsius", "condition": "sunny"}

@ez_tool
def search_products(query: str, limit: int = 5) -> list[ProductResult]:
    """Search the product catalog."""
    return [{"id": 1, "name": "Sunglasses", "price": 49.99, "tags": ["sun"]}]

toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)

# Now the LLM knows exactly what keys to use:
# weather["condition"], weather["temp"], product["price"], etc.
```

The LLM can now confidently write:

```python
weather = get_weather("San Francisco, CA")
if weather["condition"] == "sunny":
    products = search_products("sunglasses")
    total = sum(p["price"] for p in products)
    print(f"Sunny! Found {len(products)} products totaling ${total:.2f}")
```

Without chaining hints, the LLM might guess `weather["temperature"]` or `product["cost"]` — leading to `KeyError` at runtime.

## See also

- [Getting Started](getting-started.md) — quick introduction to tool chaining
- [API Reference](api-reference.md) — full API docs
- [Framework Examples](examples.md) — see tool chaining in action
