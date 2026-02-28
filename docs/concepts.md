# Concepts

## Tools

A **Tool** is a Python function wrapped with `@ez_tool`. It carries metadata extracted from the function's signature and docstring:

```python
from ez_ptc import ez_tool

@ez_tool
def get_weather(location: str, unit: str = "celsius") -> dict:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    return {"location": location, "temp": 22, "unit": unit, "condition": "sunny"}
```

The resulting `Tool` object has:

| Attribute | Source | Example |
|-----------|--------|---------|
| `name` | Function name | `"get_weather"` |
| `description` | First line of docstring | `"Get current weather for a location."` |
| `parameters` | Type hints + docstring | JSON schema with types, descriptions, defaults |
| `signature` | Full signature | `"get_weather(location: str, unit: str = 'celsius') -> dict"` |
| `return_schema` | Return type annotation | JSON schema (for TypedDict/Pydantic), or `None` |
| `fn` | Original function | The unwrapped callable |

A `Tool` is still callable — `get_weather("NYC")` works exactly like calling the original function.

### Supported type hints

ez-ptc converts these Python types to JSON schema automatically:

| Python type | JSON schema type |
|-------------|-----------------|
| `str` | `"string"` |
| `int` | `"integer"` |
| `float` | `"number"` |
| `bool` | `"boolean"` |
| `list[X]` | `"array"` with items |
| `dict[K, V]` | `"object"` with additionalProperties |
| `Optional[X]` / `X \| None` | schema of X |
| `Literal["a", "b"]` | `"string"` with enum |
| `TypedDict` | `"object"` with properties |
| Pydantic `BaseModel` | Full model schema |

### Docstring format

ez-ptc parses Google-style docstrings:

```python
def my_tool(query: str, limit: int = 10) -> list[dict]:
    """Short description goes here.

    Args:
        query: What to search for
        limit: Maximum results to return
    """
```

The first paragraph becomes the tool's `description`. Each `Args:` entry becomes a parameter description in the JSON schema.

## Toolkit

A **Toolkit** groups tools and provides two modes of LLM integration:

```python
from ez_ptc import Toolkit

toolkit = Toolkit(
    tools=[get_weather, search_products],
    preamble="...",              # Optional: custom intro text
    postamble="...",             # Optional: custom instruction text
    assist_tool_chaining=False,  # Optional: enable return schema hints
)
```

### Two modes

**Mode 1: Prompt Mode** — The toolkit generates a text block you inject into the system prompt. The LLM writes Python code in a markdown block. You extract and execute it.

```
You (system prompt) → LLM (writes code) → extract_code() → execute() → result
```

**Mode 2: Tool Mode** — The toolkit provides a single meta-tool callable that any framework can register. The LLM calls it via native tool calling.

```
Framework registers tool → LLM calls tool → execute() → result → framework continues
```

In tool mode, the tool schema and `as_tool()` docstring already include instructions for single-call consolidation. You can optionally add `tool_prompt()` to the system prompt for extra reinforcement — this is helpful when models with parallel tool calling (e.g., OpenAI) split work into multiple separate calls instead of writing one code block.

Both modes use the same execution engine under the hood.

## Execution engine

When the LLM writes code (in either mode), ez-ptc executes it in a **sandboxed environment**:

- Tools are injected as global functions
- Only safe builtins are available (no file I/O, no networking, no shell access)
- Safe stdlib modules can be imported: `math`, `datetime`, `collections`, `itertools`, `re`, and others
- A configurable timeout prevents runaway execution
- stdout/stderr are captured
- Every tool call is logged with arguments and return values

```python
result = toolkit.execute(code)

result.output       # str: captured stdout (print output)
result.error_output # str: captured stderr/traceback
result.return_value # Any: last expression value
result.tool_calls   # list[dict]: log of tool calls
result.success      # bool: whether execution succeeded
result.error        # str | None: error message if failed
```

See [Security & Sandboxing](security.md) for details on what's allowed and blocked.

## Tool chaining

Programmatic tool calling shines when the LLM chains outputs — feeding one tool's result into another tool's input, or branching on a value. But this only works if the LLM knows the **shape** of each tool's return value.

Consider this LLM-generated code:

```python
weather = get_weather("NYC")
if weather["temperature"] > 80:     # KeyError! The actual key is "temp"
    products = search_products("cooling fans")
```

The LLM guessed `"temperature"` but the real key is `"temp"`. This is a common failure mode when tools return dicts.

### The solution: `assist_tool_chaining`

When you use structured return types (`TypedDict` or Pydantic `BaseModel`) and enable `assist_tool_chaining=True`, ez-ptc documents the exact return shape alongside each tool:

```python
from typing import TypedDict

class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str

@ez_tool
def get_weather(location: str) -> WeatherResult:
    """Get weather for a location."""
    return {"location": location, "temp": 22, "unit": "celsius", "condition": "sunny"}

toolkit = Toolkit([get_weather], assist_tool_chaining=True)
```

Now when the LLM sees the tool listing, it also sees:

```
# Returns: {location: str, temp: int, unit: str, condition: str}
```

The LLM knows the exact keys and types, so it writes `weather["temp"]` instead of guessing.

### Three ways to provide return schemas

| Method | When to use |
|--------|-------------|
| `TypedDict` return type | Recommended default — lightweight, no dependencies |
| Pydantic `BaseModel` return type | When you already use Pydantic models |
| `@ez_tool(return_schema={...})` | Explicit override for tools returning plain `dict` |

### Where return schemas appear

When `assist_tool_chaining=True`, return info shows up in all three output methods:

- **`prompt()`** — as a `# Returns: {...}` comment after each tool's docstring
- **`as_tool()`** — appended to each tool's line in the meta-tool docstring
- **`tool_schema()`** — appended to each tool's line in the description field

When `assist_tool_chaining=False` (the default), output is identical to a toolkit without any return schemas — fully backward compatible.

See [Tool Chaining](tool-chaining.md) for the full guide.

## How it fits together

```
┌──────────────────────────────────────────────────────────┐
│                     Your application                     │
│                                                          │
│  @ez_tool                  @ez_tool                      │
│  def get_weather()         def search_products()         │
│  -> WeatherResult          -> list[ProductResult]        │
│       │                          │                       │
│       └────────┬─────────────────┘                       │
│                ▼                                         │
│  Toolkit([...], assist_tool_chaining=True)               │
│       │               │                                  │
│   prompt()        as_tool() + tool_schema()              │
│   + return        + return schema in                     │
│     schema          docstring & description              │
│     comments      + tool_prompt() (optional)             │
│       │               │                                  │
│  Prompt Mode      Tool Mode                              │
│  (text block)     (native tool calling)                  │
│       │               │                                  │
│       └───────┬───────┘                                  │
│               ▼                                          │
│          execute()                                       │
│      Sandboxed Python                                    │
│      execution engine                                    │
│               │                                          │
│               ▼                                          │
│       ExecutionResult                                    │
│    (output, tool_calls, errors)                          │
└──────────────────────────────────────────────────────────┘
```
