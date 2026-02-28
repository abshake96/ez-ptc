# API Reference

## `ez_tool`

```python
from ez_ptc import ez_tool
```

Decorator that wraps a function as a `Tool`.

### Bare decorator

```python
@ez_tool
def my_function(param: str) -> dict:
    """Description."""
    return {"result": param}
```

### With keyword arguments

```python
@ez_tool(return_schema={"type": "object", "properties": {"result": {"type": "string"}}})
def my_function(param: str) -> dict:
    """Description."""
    return {"result": param}
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `return_schema` | `dict \| None` | `None` | Explicit JSON schema for the return type. Overrides auto-detection. |

**Returns:** `Tool`

---

## `Tool`

```python
from ez_ptc import Tool
```

A wrapped function with metadata. Created by `@ez_tool`.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Function name |
| `description` | `str` | From first line of docstring |
| `parameters` | `dict` | JSON schema for function parameters |
| `fn` | `Callable` | The original unwrapped function |
| `signature` | `str` | Human-readable signature string |
| `return_schema` | `dict \| None` | JSON schema for return type, or `None` |

### Methods

#### `__call__(*args, **kwargs)`

Calls the underlying function. A `Tool` is callable like the original function.

```python
result = my_tool("hello")  # Same as my_tool.fn("hello")
```

---

## `Toolkit`

```python
from ez_ptc import Toolkit
```

Groups tools and provides two modes of LLM integration.

### Constructor

```python
Toolkit(
    tools: list[Tool],
    preamble: str | None = None,
    postamble: str | None = None,
    assist_tool_chaining: bool = False,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tools` | `list[Tool]` | required | List of tools to include |
| `preamble` | `str \| None` | `None` | Custom intro text for `prompt()`. Uses default if `None`. |
| `postamble` | `str \| None` | `None` | Custom instruction text for `prompt()`. Uses default if `None`. |
| `assist_tool_chaining` | `bool` | `False` | When `True`, appends return schema info to tool listings |

### Methods

#### `prompt() -> str`

Generate the instruction block for LLM system prompts.

Returns a string containing the preamble, tool signatures with docstrings, and the postamble. When `assist_tool_chaining=True`, each tool with a return schema gets a `# Returns: ...` comment.

```python
toolkit = Toolkit([my_tool])
system_message = toolkit.prompt()
```

#### `extract_code(llm_response: str) -> str | None`

Extract Python code from a markdown-formatted LLM response.

Searches for `` ```python ... ``` `` blocks first, then generic `` ``` ... ``` `` blocks. Returns the first match, or `None`.

```python
code = toolkit.extract_code(llm_response_text)
```

#### `execute(code: str, timeout: float = 30.0) -> ExecutionResult`

Execute LLM-generated Python code with tools available in a sandboxed environment.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | `str` | required | Python code to execute |
| `timeout` | `float` | `30.0` | Maximum execution time in seconds |

```python
result = toolkit.execute('print(get_weather("NYC"))')
```

#### `as_tool() -> Callable[[str], str]`

Return a callable function that any framework can register as a tool.

The returned function:
- Accepts `code: str` — Python code to execute
- Returns `str` — stdout on success, stderr/error on failure
- Has `__name__`, `__doc__`, and `__annotations__` set for framework introspection
- When `assist_tool_chaining=True`, the docstring includes return schema info

```python
execute_fn = toolkit.as_tool()
output = execute_fn('print("hello")')  # "hello\n"
```

#### `tool_prompt() -> str`

Generate a system prompt block for tool mode.

This tells the LLM how to use the `execute_tools` meta-tool, listing available functions, their signatures, and environment capabilities. Include this in your system prompt alongside the tool schema when the LLM isn't consolidating operations into a single call on its own.

The prompt includes explicit instructions to combine all operations into a single `execute_tools` call, which helps with models/frameworks that support parallel tool calling and might otherwise split work into multiple separate calls.

```python
system_message = f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"
```

> **Note:** `tool_prompt()` is optional. The tool schema description and `as_tool()` docstring already include single-call instructions. Use `tool_prompt()` as reinforcement when you observe the LLM making multiple separate calls instead of one.

#### `tool_schema(format: str = "openai") -> dict`

Return a tool definition dict in the specified provider format.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | `str` | `"openai"` | `"openai"` or `"anthropic"` |

When `assist_tool_chaining=True`, the description includes return schema info for each tool.

```python
schema = toolkit.tool_schema(format="openai")
schema = toolkit.tool_schema(format="anthropic")
```

---

## `ExecutionResult`

```python
from ez_ptc import ExecutionResult
```

Result of executing LLM-generated code.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `output` | `str` | Captured stdout (print output) |
| `error_output` | `str` | Captured stderr/traceback |
| `return_value` | `Any` | Last expression value if available |
| `tool_calls` | `list[dict]` | Log of tool calls made during execution |
| `success` | `bool` | Whether execution completed without error |
| `error` | `str \| None` | Error message if failed |

### Tool call log format

Each entry in `tool_calls`:

```python
{
    "name": "get_weather",
    "args": ("San Francisco, CA",),
    "kwargs": {"unit": "celsius"},
    "result": {"temp": 22, "condition": "sunny", ...},
}
```

### Methods

#### `to_string() -> str`

Return a string optimized for token efficiency.

- **On success:** returns stdout, or `repr(return_value)` if stdout is empty, or `""`.
- **On failure:** returns stderr/traceback, or the error message.

This is what `as_tool()` returns to the LLM.

---

## `function_to_schema`

```python
from ez_ptc import function_to_schema
```

```python
function_to_schema(fn: Callable) -> dict
```

Extract a complete schema from a Python function. Lower-level utility used internally by `@ez_tool`.

**Returns:**

```python
{
    "name": "function_name",
    "description": "From docstring",
    "parameters": {
        "type": "object",
        "properties": {...},
        "required": [...]
    },
    "signature": "function_name(param: type, ...) -> return_type",
    "return_schema": {...}  # Only present for structured return types
}
```
