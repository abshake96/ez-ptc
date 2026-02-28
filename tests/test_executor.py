"""Tests for executor.py — safe code execution engine."""

import asyncio

from ez_ptc import ez_tool
from ez_ptc.executor import ExecutionResult, execute_code


def _make_tools():
    """Create test tools."""

    @ez_tool
    def get_weather(location: str) -> dict:
        """Get weather.

        Args:
            location: City name
        """
        return {"temp": 22, "condition": "sunny"}

    @ez_tool
    def search(query: str, limit: int = 5) -> list:
        """Search.

        Args:
            query: Query string
            limit: Max results
        """
        return [{"id": i, "name": f"Result {i}"} for i in range(limit)]

    return {"get_weather": get_weather, "search": search}


def test_basic_execution():
    tools = _make_tools()
    result = execute_code('print("hello")', tools)
    assert result.success
    assert result.output.strip() == "hello"
    assert result.error is None


def test_tool_call():
    tools = _make_tools()
    code = """
weather = get_weather("San Francisco")
print(weather["condition"])
"""
    result = execute_code(code, tools)
    assert result.success
    assert "sunny" in result.output
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["args"] == ("San Francisco",)


def test_multiple_tool_calls():
    tools = _make_tools()
    code = """
weather = get_weather("NYC")
results = search("umbrellas", limit=3)
print(f"Weather: {weather['condition']}, Found: {len(results)}")
"""
    result = execute_code(code, tools)
    assert result.success
    assert "sunny" in result.output
    assert "3" in result.output
    assert len(result.tool_calls) == 2


def test_tool_call_with_control_flow():
    tools = _make_tools()
    code = """
weather = get_weather("London")
if weather["condition"] == "sunny":
    items = search("sunglasses")
else:
    items = search("umbrellas")
print(f"Recommended {len(items)} items")
"""
    result = execute_code(code, tools)
    assert result.success
    assert "5" in result.output  # default limit is 5


def test_error_handling():
    tools = _make_tools()
    code = """
x = undefined_variable
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "NameError" in result.error
    assert "undefined_variable" in result.error


def test_tool_call_logging():
    tools = _make_tools()
    code = """
r1 = search("cats", limit=2)
r2 = search("dogs", limit=3)
print("done")
"""
    result = execute_code(code, tools)
    assert result.success
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0]["args"] == ("cats",)
    assert result.tool_calls[0]["kwargs"]["limit"] == 2
    assert result.tool_calls[1]["args"] == ("dogs",)


def test_exception_in_code():
    tools = _make_tools()
    code = """
raise ValueError("something went wrong")
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "ValueError" in result.error
    assert "something went wrong" in result.error
    assert "Traceback" in result.error_output


def test_restricted_namespace():
    tools = _make_tools()
    # Trying to import a blocked module should raise ImportError
    code = """
import os
print(os.getcwd())
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "ImportError" in result.error


def test_safe_builtins_available():
    tools = _make_tools()
    code = """
items = list(range(5))
print(len(items))
print(sorted([3, 1, 2]))
print(min(items), max(items))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "5" in result.output
    assert "[1, 2, 3]" in result.output


def test_json_available():
    tools = _make_tools()
    code = """
data = json.dumps({"key": "value"})
print(data)
"""
    result = execute_code(code, tools)
    assert result.success
    assert '"key"' in result.output


def test_timeout():
    tools = _make_tools()
    code = """
while True:
    pass
"""
    result = execute_code(code, tools, timeout=1.0)
    assert not result.success
    assert "timed out" in result.error


def test_execution_result_to_string_success():
    result = ExecutionResult(output="hello world", success=True)
    assert result.to_string() == "hello world"


def test_execution_result_to_string_failure():
    result = ExecutionResult(
        error_output="Traceback: ...",
        success=False,
        error="NameError: x",
    )
    assert result.to_string() == "Traceback: ..."


def test_execution_result_to_string_failure_no_stderr():
    result = ExecutionResult(success=False, error="Something failed")
    assert result.to_string() == "Something failed"


def test_tool_raising_exception():
    @ez_tool
    def failing_tool(x: str) -> str:
        """Always fails.

        Args:
            x: Input
        """
        raise RuntimeError("tool broke")

    tools = {"failing_tool": failing_tool}
    code = """
result = failing_tool("test")
print(result)
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "RuntimeError" in result.error
    assert "tool broke" in result.error


def test_positional_args():
    tools = _make_tools()
    code = """
weather = get_weather("Paris")
print(weather["temp"])
"""
    result = execute_code(code, tools)
    assert result.success
    assert "22" in result.output
    assert result.tool_calls[0]["args"] == ("Paris",)


def test_async_tool():
    @ez_tool
    def sync_wrapper(x: str) -> str:
        """Wrap async.

        Args:
            x: Input
        """
        async def _inner():
            return f"async: {x}"
        return asyncio.run(_inner())

    tools = {"sync_wrapper": sync_wrapper}
    code = """
result = sync_wrapper("test")
print(result)
"""
    result = execute_code(code, tools)
    assert result.success
    assert "async: test" in result.output


# ── Safe import tests ─────────────────────────────────────────────────


def test_safe_import_math():
    tools = _make_tools()
    code = """
import math
print(math.sqrt(16))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "4.0" in result.output


def test_safe_import_re():
    tools = _make_tools()
    code = """
import re
m = re.match(r'(\\w+)', 'hello world')
print(m.group(1))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "hello" in result.output


def test_safe_import_datetime():
    tools = _make_tools()
    code = """
import datetime
d = datetime.date(2024, 1, 15)
print(d.isoformat())
"""
    result = execute_code(code, tools)
    assert result.success
    assert "2024-01-15" in result.output


def test_safe_import_collections():
    tools = _make_tools()
    code = """
from collections import Counter
c = Counter("abracadabra")
print(c.most_common(2))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "a" in result.output


def test_safe_import_urllib_parse():
    tools = _make_tools()
    code = """
from urllib.parse import urlencode
print(urlencode({"q": "hello world"}))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "q=hello" in result.output


# ── Blocked import tests ─────────────────────────────────────────────


def test_blocked_import_os():
    tools = _make_tools()
    code = """
import os
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "ImportError" in result.error


def test_blocked_import_subprocess():
    tools = _make_tools()
    code = """
import subprocess
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "ImportError" in result.error


def test_blocked_import_socket():
    tools = _make_tools()
    code = """
import socket
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "ImportError" in result.error


def test_blocked_import_urllib_request():
    tools = _make_tools()
    code = """
from urllib.request import urlopen
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "ImportError" in result.error


def test_import_error_message():
    """Error message should list available modules for LLM self-correction."""
    tools = _make_tools()
    code = """
import os
"""
    result = execute_code(code, tools)
    assert not result.success
    assert "Available modules:" in result.error
    assert "math" in result.error
    assert "json" in result.error


# ── Pre-injected modules tests ───────────────────────────────────────


def test_pre_injected_modules():
    """json, asyncio, math, re should be available without import."""
    tools = _make_tools()
    code = """
# All of these should work without import statements
j = json.dumps({"x": 1})
m = math.sqrt(9)
r = re.match(r'\\w+', 'hello')
print(f"{j} {m} {r.group()}")
"""
    result = execute_code(code, tools)
    assert result.success
    assert '"x": 1' in result.output
    assert "3.0" in result.output
    assert "hello" in result.output


def test_asyncio_pre_injected():
    """asyncio.run() should work without import."""
    tools = _make_tools()
    code = """
async def greet():
    return "hello async"
print(asyncio.run(greet()))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "hello async" in result.output


# ── Async parallel execution tests ───────────────────────────────────


def test_async_parallel_execution():
    """asyncio.gather + asyncio.to_thread with tools should work."""
    tools = _make_tools()
    code = """
import asyncio

async def main():
    a, b = await asyncio.gather(
        asyncio.to_thread(get_weather, "NYC"),
        asyncio.to_thread(search, "test", limit=2),
    )
    print(f"weather={a['condition']}, results={len(b)}")

asyncio.run(main())
"""
    result = execute_code(code, tools)
    assert result.success
    assert "weather=sunny" in result.output
    assert "results=2" in result.output


# ── Expanded builtins tests ──────────────────────────────────────────


def test_expanded_builtins():
    """New builtins should be available."""
    tools = _make_tools()
    code = """
# Data conversion
print(repr("hello"))
print(chr(65))
print(ord("A"))
print(hex(255))
print(bin(10))
print(oct(8))

# Iteration
it = iter([1, 2, 3])
print(next(it))
print(callable(print))

# Types
print(type(frozenset({1, 2})))
print(type(bytes(3)))
print(type(bytearray(3)))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "'hello'" in result.output
    assert "A" in result.output
    assert "65" in result.output
    assert "0xff" in result.output
    assert "0b1010" in result.output
    assert "0o10" in result.output
    assert "1" in result.output
    assert "True" in result.output
    assert "frozenset" in result.output


def test_expanded_builtins_introspection():
    """dir, id, hash, super, etc. should be available."""
    tools = _make_tools()
    code = """
class Base:
    x = 1

class Child(Base):
    pass

print(issubclass(Child, Base))
print(id(42) > 0)
print(isinstance(hash("test"), int))
print("x" in dir(Child))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "True" in result.output


def test_expanded_builtins_exceptions():
    """New exception types should be available."""
    tools = _make_tools()
    code = """
exceptions = [
    AttributeError, RuntimeError, StopIteration, ImportError,
    ZeroDivisionError, NotImplementedError, OverflowError,
    OSError, StopAsyncIteration,
]
print(len(exceptions))
"""
    result = execute_code(code, tools)
    assert result.success
    assert "9" in result.output
