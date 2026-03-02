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
    timeout: float = 30.0,
    sandbox: SandboxBackend | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tools` | `list[Tool]` | required | List of tools to include. Duplicate names raise `ValueError`. |
| `preamble` | `str \| None` | `None` | Custom intro text for `prompt()`. Uses default if `None`. |
| `postamble` | `str \| None` | `None` | Custom instruction text for `prompt()`. Uses default if `None`. |
| `assist_tool_chaining` | `bool` | `False` | When `True`, appends return schema info to tool listings |
| `timeout` | `float` | `30.0` | Default execution timeout in seconds |
| `sandbox` | `SandboxBackend \| None` | `None` | Custom sandbox backend. Uses `LocalSandbox` if `None`. |

### Class Methods

#### `await Toolkit.from_mcp(session, *, tool_names=None, include_resources=True, extra_tools=None, return_schemas=None, **kwargs) -> Toolkit`

Create a Toolkit from an MCP server session. Discovers tools and resources, wraps them as `Tool` objects. Requires `pip install ez-ptc[mcp]`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ClientSession` | required | An active MCP ClientSession |
| `tool_names` | `list[str] \| None` | `None` | Only include tools whose names match this list |
| `include_resources` | `bool` | `True` | Whether to wrap resources/templates as tools |
| `extra_tools` | `list[Tool] \| None` | `None` | Additional local `Tool` objects to include |
| `return_schemas` | `dict[str, dict] \| None` | `None` | Map of tool name → JSON schema for return types. Applied to matching MCP tools for `assist_tool_chaining`. |
| `**kwargs` | | | Passed to `Toolkit.__init__` (preamble, postamble, etc.) |

```python
toolkit = await Toolkit.from_mcp(session, extra_tools=[my_tool], assist_tool_chaining=True)
```

#### `Toolkit.from_mcp_sync(session, **kwargs) -> Toolkit`

Sync version of `from_mcp()`. Same parameters.

```python
toolkit = Toolkit.from_mcp_sync(session, include_resources=False)
```

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

#### `await execute(code: str, timeout: float | None = None, validate: bool = True) -> ExecutionResult`

Execute LLM-generated Python code with tools available in a sandboxed environment. This is an async method.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | `str` | required | Python code to execute |
| `timeout` | `float \| None` | `None` | Maximum execution time in seconds. Uses the toolkit's default if `None`. |
| `validate` | `bool` | `True` | Run AST pre-flight validation before execution |

```python
result = await toolkit.execute('print(get_weather("NYC"))')
```

#### `execute_sync(code: str, timeout: float | None = None, validate: bool = True) -> ExecutionResult`

Sync convenience wrapper around `execute()`. Same parameters.

```python
result = toolkit.execute_sync('print(get_weather("NYC"))')
```

#### `as_tool() -> Callable[[str], Awaitable[str]]`

Return an async callable function that any framework can register as a tool.

The returned function:
- Accepts `code: str` — Python code to execute
- Returns `str` — stdout on success, stderr/error on failure
- Has `__name__`, `__doc__`, and `__annotations__` set for framework introspection
- When `assist_tool_chaining=True`, the docstring includes return schema info

```python
execute_fn = toolkit.as_tool()
output = await execute_fn('print("hello")')  # "hello\n"
```

#### `as_tool_sync() -> Callable[[str], str]`

Return a sync callable function. Same behavior as `as_tool()` but synchronous.

```python
execute_fn = toolkit.as_tool_sync()
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

---

## `SandboxBackend`

```python
from ez_ptc import SandboxBackend
```

A `Protocol` class defining the interface for sandbox backends. Any class with an `async execute(code, tools, timeout)` method satisfies this protocol.

### Methods

#### `async execute(code: str, tools: dict[str, Tool], timeout: float) -> ExecutionResult`

Execute code in the sandbox.

---

## `LocalSandbox`

```python
from ez_ptc import LocalSandbox
```

Default sandbox backend. Uses the built-in restricted `exec()` engine with `asyncio.to_thread` for non-blocking execution.

```python
from ez_ptc import Toolkit, LocalSandbox

# Explicit (equivalent to default behavior)
toolkit = Toolkit(tools, sandbox=LocalSandbox())
```

---

## `validate_code`

```python
from ez_ptc import validate_code
```

```python
validate_code(code: str, tool_names: set[str]) -> ValidationResult
```

Run AST pre-flight validation on LLM-generated code. Returns a `ValidationResult` with any warnings and errors.

| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | `str` | Python source code to validate |
| `tool_names` | `set[str]` | Names of tools available in the sandbox |

```python
result = validate_code(code, {"get_weather", "search_products"})
if not result.is_safe:
    print(result.errors)
```

---

## `ValidationResult`

```python
from ez_ptc import ValidationResult
```

Result of static code validation.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `warnings` | `list[str]` | Non-blocking issues (code still executes) |
| `errors` | `list[str]` | Blocking issues (code will NOT execute) |

### Properties

#### `is_safe -> bool`

`True` when there are no blocking errors.

---

## MCP Bridge Functions

These functions require `pip install "ez-ptc[mcp]"` and are imported from `ez_ptc.mcp`:

```python
from ez_ptc.mcp import tools_from_mcp, get_mcp_prompt, list_mcp_prompts
```

### `tools_from_mcp`

```python
await tools_from_mcp(
    session: ClientSession,
    *,
    tool_names: list[str] | None = None,
    include_resources: bool = True,
    return_schemas: dict[str, dict] | None = None,
) -> list[Tool]
```

Discover MCP tools and resources, wrap them as ez-ptc `Tool` objects.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ClientSession` | required | An active MCP ClientSession |
| `tool_names` | `list[str] \| None` | `None` | Only include tools whose names match. Applies to MCP tools AND resource tools. |
| `include_resources` | `bool` | `True` | Whether to wrap static resources and resource templates |
| `return_schemas` | `dict[str, dict] \| None` | `None` | Map of tool name → JSON schema for return types |

**Returns:** `list[Tool]`

```python
tools = await tools_from_mcp(session, tool_names=["search", "fetch"])
toolkit = Toolkit(tools + [my_local_tool])
```

### `get_mcp_prompt`

```python
await get_mcp_prompt(
    session: ClientSession,
    name: str,
    arguments: dict[str, str] | None = None,
) -> str
```

Fetch and expand an MCP prompt template. Returns the text content of all messages joined together.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ClientSession` | required | An active MCP ClientSession |
| `name` | `str` | required | The prompt name to fetch |
| `arguments` | `dict[str, str] \| None` | `None` | Arguments to fill the prompt template |

**Returns:** `str`

```python
system_text = await get_mcp_prompt(session, "code_review", {"language": "python"})
```

### `list_mcp_prompts`

```python
await list_mcp_prompts(session: ClientSession) -> list[dict]
```

List available MCP prompts with their arguments.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ClientSession` | required | An active MCP ClientSession |

**Returns:** `list[dict]` — each dict contains:

```python
{
    "name": "prompt_name",
    "description": "What this prompt does",
    "arguments": [
        {"name": "arg_name", "description": "...", "required": True},
    ]
}
```

```python
prompts = await list_mcp_prompts(session)
for p in prompts:
    print(f"{p['name']}: {p['description']}")
```

See [MCP Tool Bridge](mcp-bridge.md) for the full guide.
