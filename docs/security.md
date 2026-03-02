# Security & Sandboxing

ez-ptc executes LLM-generated Python code. This page documents the security measures in place.

## Execution model

All code runs in a **restricted namespace** with:
- A curated set of safe builtins (no `eval()`, `exec()`, `compile()`)
- A guarded `__import__` that only allows safe stdlib modules
- No file system access
- No network access
- Configurable timeout (default 30 seconds)

## What's available

### Safe builtins

The execution environment provides these builtins:

**Types & constructors:**
`str`, `int`, `float`, `bool`, `dict`, `list`, `tuple`, `set`, `frozenset`, `bytes`, `bytearray`, `complex`, `object`, `slice`, `memoryview`

**Iteration & sequences:**
`range`, `enumerate`, `zip`, `map`, `filter`, `sorted`, `reversed`, `next`, `iter`

**Math & aggregation:**
`min`, `max`, `sum`, `abs`, `round`, `pow`, `divmod`

**Logic & length:**
`any`, `all`, `len`, `callable`

**Data conversion:**
`repr`, `chr`, `ord`, `hex`, `bin`, `oct`, `format`, `ascii`

**Type checking & introspection:**
`isinstance`, `issubclass`, `type`, `hasattr`, `getattr`, `setattr`, `delattr`, `dir`, `id`, `hash`, `super`, `property`, `staticmethod`, `classmethod`

**Output:**
`print`

**Constants:**
`True`, `False`, `None`

**Exceptions:**
`ValueError`, `TypeError`, `KeyError`, `IndexError`, `AttributeError`, `RuntimeError`, `StopIteration`, `ImportError`, `ZeroDivisionError`, `NotImplementedError`, `OverflowError`, `AssertionError`, `OSError`, `StopAsyncIteration`, `Exception`

### Pre-imported modules

These modules are available as globals without needing an `import` statement:

- `json` — data serialization
- `math` — mathematical functions
- `re` — regular expressions
- `asyncio` — async/await and parallel execution

### Importable modules

The following safe stdlib modules can be imported with `import` statements:

**Data & computation:**
`json`, `math`, `re`, `datetime`, `time`, `calendar`, `random`, `statistics`, `decimal`, `fractions`

**Collections & algorithms:**
`collections`, `itertools`, `functools`, `operator`, `bisect`, `heapq`

**Type system:**
`typing`, `types`, `dataclasses`, `enum`, `abc`

**Text & formatting:**
`string`, `textwrap`, `pprint`

**Utilities:**
`copy`, `base64`, `hashlib`, `uuid`

**Async:**
`asyncio`, `concurrent.futures`

**URL parsing:**
`urllib.parse`

### Tool functions

All tools registered with the `Toolkit` are available as global functions.

## What's blocked

- `os`, `sys`, `subprocess`, `shutil` — no shell or filesystem access
- `socket`, `http`, `urllib.request`, `requests` — no network access
- `pickle`, `shelve`, `marshal` — no deserialization
- `eval()`, `exec()`, `compile()` — not in safe builtins
- `globals()`, `locals()` manipulation — not in safe builtins
- Any module not in the allowlist raises `ImportError` with a helpful message listing available modules
- Relative imports are blocked

## Async patterns

LLM-generated code can use `asyncio` for parallel tool execution:

```python
import asyncio

async def main():
    a, b = await asyncio.gather(
        asyncio.to_thread(tool1, ...),
        asyncio.to_thread(tool2, ...),
    )
    print(a, b)

asyncio.run(main())
```

`asyncio` is pre-imported, so the `import asyncio` line is optional.

## AST pre-flight validation

Before execution, `validate_code()` performs lightweight AST checks to catch common LLM mistakes early:

- **Tool imports** — errors if the LLM tries to `import` a tool that is already a global function
- **Dangerous attributes** — errors on access to `__import__`, `__builtins__`, `__globals__`, `__code__`, `__subclasses__`, etc.
- **Unknown calls** — warns about calls to functions not in tools, builtins, or locally defined names
- **Infinite loops** — warns about `while True` without `break` or `return`
- **Excessive resources** — warns about large exponents or multiplications (e.g., `10 ** 10_000_000`)

Validation is defense-in-depth (not a security boundary). The `execute()` and `execute_sync()` methods run validation automatically by default. You can also call `validate_code()` directly:

```python
from ez_ptc import validate_code

result = validate_code(code, tool_names={"get_weather", "search_products"})
if not result.is_safe:
    print("Errors:", result.errors)
print("Warnings:", result.warnings)
```

## Timeout protection

Code execution has a configurable timeout (default 30 seconds):

```python
result = toolkit.execute_sync(code, timeout=10.0)  # 10 second timeout
# Or: result = await toolkit.execute(code, timeout=10.0)  # async version
```

Implementation:
- **Unix (main thread):** Uses `signal.SIGALRM` for precise timeout
- **Other platforms / non-main thread:** Uses a daemon thread with `join(timeout=...)`

If execution exceeds the timeout:
```python
result.success  # False
result.error    # "Execution timed out after 30 seconds"
```

## Error handling

When code raises an exception:
- `result.success` is set to `False`
- `result.error` contains the exception type and message
- `result.error_output` contains the full traceback
- The traceback is returned to the LLM (via `to_string()`) for self-correction
- In tool mode (`as_tool()` / `as_tool_sync()`), the error output is prefixed with `ERROR: <error_hint>` to guide the LLM toward recovery. The default hint is: *"If execution returns an error, analyze the traceback, fix your code, and try again."* Customize via `Toolkit(error_hint="...")` or disable with `error_hint=""`.

## Tool call logging

Every tool call during execution is logged:

```python
result.tool_calls
# [
#     {
#         "name": "get_weather",
#         "args": ("San Francisco, CA",),
#         "kwargs": {"unit": "celsius"},
#         "result": {"temp": 22, "condition": "sunny"},
#     }
# ]
```

This gives you full visibility into what the LLM's code did.

## Async tool support

If a tool function is `async`, ez-ptc handles it automatically:
- If no event loop is running: uses `asyncio.run()`
- If an event loop is running: runs the coroutine in a thread pool

No special handling needed from the tool author.

## Recommendations

1. **Validate tool outputs** — if your tools interact with external systems (APIs, databases), validate inputs within the tool functions themselves.

2. **Use timeouts** — set appropriate timeouts for your use case. The default 30 seconds is generous; most tool-calling code should complete in under 5 seconds.

3. **Review tool calls** — use `result.tool_calls` to audit what the LLM did. Log these in production.

4. **Limit tool scope** — only expose tools that the LLM needs. Don't add tools with destructive side effects (deleting data, sending emails) without appropriate safeguards in the tool implementation.

5. **Handle errors gracefully** — always check `result.success` before using `result.output`. The error output is designed to help the LLM self-correct on the next turn.

## See also

- [Concepts](concepts.md) — core architecture overview
- [API Reference](api-reference.md) — full API docs for `execute()` and `ExecutionResult`
