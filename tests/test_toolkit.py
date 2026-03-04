"""Tests for toolkit.py — Toolkit class."""

from typing import TypedDict

import pytest

from ez_ptc import ExecutionResult, Toolkit, ez_tool
from ez_ptc.executor import ExecutionResult as ER
from ez_ptc.sandbox import LocalSandbox


@ez_tool
def get_weather(location: str, unit: str = "celsius") -> dict:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    return {"temp": 22, "condition": "sunny", "unit": unit}


@ez_tool
def search_database(query: str, limit: int = 10) -> list[dict]:
    """Search the product database.

    Args:
        query: Search query string
        limit: Maximum number of results
    """
    return [{"id": i, "name": f"Product {i}", "price": 9.99} for i in range(limit)]


def _make_toolkit(**kwargs):
    return Toolkit([get_weather, search_database], **kwargs)


# Tools with structured return types for chaining tests
class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str


class ProductResult(TypedDict):
    id: int
    name: str
    price: float


@ez_tool
def get_weather_typed(location: str) -> WeatherResult:
    """Get weather.

    Args:
        location: City name
    """
    return {"location": location, "temp": 22, "unit": "celsius", "condition": "sunny"}


@ez_tool
def search_products_typed(query: str) -> list[ProductResult]:
    """Search products.

    Args:
        query: Search query
    """
    return [{"id": 1, "name": "Umbrella", "price": 24.99}]


def _make_typed_toolkit(**kwargs):
    return Toolkit([get_weather_typed, search_products_typed], **kwargs)


# ── Prompt mode tests ────────────────────────────────────────────────


class TestPrompt:
    def test_default_prompt(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "get_weather" in prompt
        assert "search_database" in prompt
        assert "Available tools:" in prompt
        assert "location: str" in prompt
        assert "query: str" in prompt

    def test_custom_preamble_overrides_default(self):
        tk = _make_toolkit(preamble="Custom intro text here.")
        prompt = tk.prompt()
        assert "Custom intro text here." in prompt
        assert "You have access to" not in prompt

    def test_custom_postamble_overrides_default(self):
        tk = _make_toolkit(postamble="Always return JSON.")
        prompt = tk.prompt()
        assert "Always return JSON." in prompt
        assert "print() the final result" not in prompt

    def test_tool_docstrings_in_prompt(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "Get current weather" in prompt
        assert "Search the product database" in prompt

    def test_default_prompt_mentions_imports(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "json" in prompt
        assert "import" in prompt.lower()

    def test_default_prompt_mentions_restrictions(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "blocked" in prompt.lower() or "no file" in prompt.lower()

    def test_default_prompt_mentions_parallel(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "parallel(" in prompt

    def test_chaining_prompt_mentions_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        prompt = tk.prompt()
        assert "# Returns:" in prompt

    def test_no_chaining_prompt_no_schema_mention(self):
        tk = _make_typed_toolkit(assist_tool_chaining=False)
        prompt = tk.prompt()
        assert "# Returns:" not in prompt


class TestExtractCode:
    def test_python_fence(self):
        tk = _make_toolkit()
        response = '''Here's the code:

```python
weather = get_weather("SF")
print(weather)
```

That should work!'''
        code = tk.extract_code(response)
        assert code is not None
        assert 'get_weather("SF")' in code

    def test_generic_fence(self):
        tk = _make_toolkit()
        response = '''```
print("hello")
```'''
        code = tk.extract_code(response)
        assert code == 'print("hello")'

    def test_no_code_block(self):
        tk = _make_toolkit()
        response = "Just a regular text response with no code."
        code = tk.extract_code(response)
        assert code is None

    def test_multiple_code_blocks(self):
        tk = _make_toolkit()
        response = '''First block:
```python
x = 1
```

Second block:
```python
y = 2
```'''
        code = tk.extract_code(response)
        assert code == "x = 1"  # Returns first match

    def test_multiline_code(self):
        tk = _make_toolkit()
        response = '''```python
weather = get_weather("NYC")
if weather["condition"] == "sunny":
    products = search_database("sunglasses")
else:
    products = search_database("umbrellas")
print(products)
```'''
        code = tk.extract_code(response)
        assert code is not None
        assert "if weather" in code
        assert "search_database" in code


# ── Tool mode tests ──────────────────────────────────────────────────


class TestAsTool:
    def test_returns_callable(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        assert callable(fn)

    def test_function_metadata(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        assert fn.__name__ == "execute_tools"
        assert fn.__annotations__ == {"code": str, "return": str}
        assert "get_weather" in fn.__doc__
        assert "search_database" in fn.__doc__

    def test_sync_returns_callable(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        assert callable(fn)

    def test_sync_function_metadata(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        assert fn.__name__ == "execute_tools"
        assert fn.__annotations__ == {"code": str, "return": str}
        assert "get_weather" in fn.__doc__
        assert "search_database" in fn.__doc__

    def test_execution_success(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        result = fn('print("hello from tool mode")')
        assert "hello from tool mode" in result

    def test_execution_with_tools(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        result = fn('w = get_weather("SF")\nprint(w["condition"])')
        assert "sunny" in result

    def test_execution_failure(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        result = fn("x = undefined_var")
        assert "NameError" in result

    @pytest.mark.asyncio
    async def test_async_execution_success(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        result = await fn('print("hello async")')
        assert "hello async" in result

    @pytest.mark.asyncio
    async def test_async_execution_with_tools(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        result = await fn('w = get_weather("SF")\nprint(w["condition"])')
        assert "sunny" in result


class TestToolSchema:
    def test_openai_format(self):
        tk = _make_toolkit()
        schema = tk.tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "execute_tools"
        assert "code" in schema["function"]["parameters"]["properties"]
        assert schema["function"]["parameters"]["required"] == ["code"]
        assert "get_weather" in schema["function"]["description"]

    def test_anthropic_format(self):
        tk = _make_toolkit()
        schema = tk.tool_schema(format="anthropic")
        assert schema["name"] == "execute_tools"
        assert "code" in schema["input_schema"]["properties"]
        assert schema["input_schema"]["required"] == ["code"]
        assert "search_database" in schema["description"]


# ── Execute tests ────────────────────────────────────────────────────


class TestExecute:
    def test_basic_execute(self):
        tk = _make_toolkit()
        result = tk.execute_sync('print("test")')
        assert result.success
        assert "test" in result.output

    def test_execute_with_tools(self):
        tk = _make_toolkit()
        code = """
weather = get_weather("Boston", unit="fahrenheit")
products = search_database("coats", limit=3)
print(f"Temp: {weather['temp']}, Products: {len(products)}")
"""
        result = tk.execute_sync(code)
        assert result.success
        assert "22" in result.output
        assert "3" in result.output
        assert len(result.tool_calls) == 2

    def test_execute_error(self):
        tk = _make_toolkit()
        result = tk.execute_sync("1/0")
        assert not result.success
        assert "ZeroDivisionError" in result.error

    @pytest.mark.asyncio
    async def test_async_basic_execute(self):
        tk = _make_toolkit()
        result = await tk.execute('print("async test")')
        assert result.success
        assert "async test" in result.output

    @pytest.mark.asyncio
    async def test_async_execute_with_tools(self):
        tk = _make_toolkit()
        code = 'w = get_weather("NYC")\nprint(w["condition"])'
        result = await tk.execute(code)
        assert result.success
        assert "sunny" in result.output


# ── End-to-end tests ─────────────────────────────────────────────────


class TestEndToEnd:
    def test_prompt_mode_flow(self):
        """Simulate the full prompt mode flow."""
        tk = _make_toolkit()

        # 1. Generate prompt
        prompt = tk.prompt()
        assert "get_weather" in prompt

        # 2. Simulate LLM response with code
        llm_response = '''I'll check the weather and find products.

```python
weather = get_weather("San Francisco, CA")
if weather["condition"] == "sunny":
    products = search_database("sunglasses", limit=3)
else:
    products = search_database("umbrellas", limit=3)
print(f"Weather: {weather['condition']}, Found {len(products)} products")
```

This code checks the weather and searches for appropriate products.'''

        # 3. Extract code
        code = tk.extract_code(llm_response)
        assert code is not None

        # 4. Execute
        result = tk.execute_sync(code)
        assert result.success
        assert "sunny" in result.output
        assert "3" in result.output
        assert len(result.tool_calls) == 2

    def test_tool_mode_flow(self):
        """Simulate the full tool mode flow."""
        tk = _make_toolkit()

        # 1. Get meta-tool (sync version for sync test)
        execute_fn = tk.as_tool_sync()

        # 2. Get schema for framework registration
        schema = tk.tool_schema()
        assert schema["function"]["name"] == "execute_tools"

        # 3. Simulate LLM calling the tool
        code = """
results = []
for city in ["NYC", "LA", "Chicago"]:
    w = get_weather(city)
    results.append(f"{city}: {w['condition']}")
print(", ".join(results))
"""
        output = execute_fn(code)
        assert "NYC: sunny" in output
        assert "LA: sunny" in output
        assert "Chicago: sunny" in output


# ── assist_tool_chaining tests ──────────────────────────────────────


class TestAssistToolChaining:
    def test_disabled_by_default(self):
        """assist_tool_chaining=False should not change output."""
        tk_off = _make_typed_toolkit(assist_tool_chaining=False)
        tk_default = _make_typed_toolkit()

        assert tk_off.prompt() == tk_default.prompt()
        assert tk_off.as_tool().__doc__ == tk_default.as_tool().__doc__
        assert tk_off.tool_schema() == tk_default.tool_schema()

    def test_prompt_includes_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        prompt = tk.prompt()
        assert "# Returns:" in prompt
        assert "location: str" in prompt
        assert "temp: int" in prompt

    def test_prompt_no_return_schema_for_plain_dict(self):
        """Tools with plain dict return type should not get schema even with chaining on."""
        tk = Toolkit([get_weather], assist_tool_chaining=True)
        prompt = tk.prompt()
        # The preamble mentions "# Returns:" generically, but the tool block
        # for a plain dict return should not have a "# Returns: {" annotation.
        assert "# Returns: {" not in prompt

    def test_as_tool_includes_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        fn = tk.as_tool()
        assert "Returns:" in fn.__doc__
        assert "location: str" in fn.__doc__

    def test_tool_schema_includes_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        schema = tk.tool_schema()
        desc = schema["function"]["description"]
        assert "Returns:" in desc
        assert "location: str" in desc

    def test_tool_schema_anthropic_includes_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        schema = tk.tool_schema(format="anthropic")
        assert "Returns:" in schema["description"]

    def test_prompt_list_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        prompt = tk.prompt()
        # search_products_typed returns list[ProductResult]
        assert "list[{" in prompt

    def test_chaining_disabled_no_return_info(self):
        tk = _make_typed_toolkit(assist_tool_chaining=False)
        prompt = tk.prompt()
        assert "# Returns:" not in prompt


# ── tool_prompt() tests ──────────────────────────────────────────────


class TestToolPrompt:
    def test_tool_prompt_mentions_execute_tools(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "execute_tools" in tp
        assert "code" in tp

    def test_tool_prompt_lists_tools(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "get_weather" in tp
        assert "search_database" in tp
        assert "Get current weather" in tp
        assert "Search the product database" in tp

    def test_tool_prompt_chaining_mentions_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=True)
        tp = tk.tool_prompt()
        assert "Returns:" in tp
        assert "location: str" in tp

    def test_tool_prompt_no_chaining_no_return_schema(self):
        tk = _make_typed_toolkit(assist_tool_chaining=False)
        tp = tk.tool_prompt()
        assert "# Returns:" not in tp

    def test_tool_prompt_mentions_restrictions(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "blocked" in tp.lower() or "no file" in tp.lower()
        assert "os" in tp.lower()

    def test_tool_prompt_mentions_pre_imported(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "json" in tp
        assert "math" in tp
        assert "re" in tp


# ── Single-call instruction tests ────────────────────────────────────


class TestSingleCallInstructions:
    def test_tool_schema_mentions_single_call(self):
        tk = _make_toolkit()
        desc = tk.tool_schema()["function"]["description"]
        assert "SINGLE" in desc
        assert "do NOT" in desc

    def test_as_tool_mentions_single_call(self):
        tk = _make_toolkit()
        doc = tk.as_tool().__doc__
        assert "SINGLE" in doc
        assert "do NOT" in doc

    def test_tool_prompt_mentions_single_call(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "SINGLE" in tp
        assert "do NOT" in tp

    def test_default_postamble_mentions_single_call(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "Combine ALL operations into a single code block" in prompt


# ── Edge case tests ─────────────────────────────────────────────────


class TestEdgeCases:
    def test_extract_code_with_nested_backticks(self):
        tk = _make_toolkit()
        response = '''Here's the code:

```python
markdown_str = "```python\\nprint('hi')\\n```"
print(markdown_str)
```

That should work!'''
        code = tk.extract_code(response)
        assert code is not None
        assert "markdown_str" in code

    def test_to_string_empty_success(self):
        result = ExecutionResult(success=True, output="", return_value=None)
        assert result.to_string() == ""

    def test_to_string_returns_return_value_when_no_output(self):
        result = ExecutionResult(success=True, output="", return_value=42)
        assert result.to_string() == "42"


# ── Chaining language conditional tests ──────────────────────────────


class TestChainingLanguageConditional:
    """Chaining language should only appear when assist_tool_chaining=True."""

    def test_postamble_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        prompt = tk.prompt()
        assert "Chain results" not in prompt
        assert "do NOT access" in prompt
        assert "print(tool_a(...))" in prompt

    def test_postamble_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        prompt = tk.prompt()
        assert "Chain results" in prompt
        assert "do NOT access" not in prompt

    def test_tool_prompt_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        tp = tk.tool_prompt()
        assert "Chain results" not in tp
        assert "do NOT access" in tp
        assert "print(tool_a(...))" in tp

    def test_tool_prompt_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        tp = tk.tool_prompt()
        assert "Chain results" in tp
        assert "do NOT access" not in tp

    def test_as_tool_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        doc = tk.as_tool().__doc__
        assert "chain between" not in doc.lower()
        assert "do NOT access" in doc

    def test_as_tool_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        doc = tk.as_tool().__doc__
        assert "chain between" in doc.lower()
        assert "do NOT access" not in doc

    def test_tool_schema_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        desc = tk.tool_schema()["function"]["description"]
        assert "chain between" not in desc.lower()
        assert "do NOT access" in desc

    def test_tool_schema_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        desc = tk.tool_schema()["function"]["description"]
        assert "chain between" in desc.lower()
        assert "do NOT access" not in desc


# ── Do-not-import-tools tests ────────────────────────────────────────


class TestDoNotImportTools:
    """All surfaces should tell the LLM not to import the available tools."""

    def test_prompt_mentions_no_import(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "do NOT import" in prompt

    def test_tool_prompt_mentions_no_import(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "do NOT import" in tp

    def test_as_tool_mentions_no_import(self):
        tk = _make_toolkit()
        doc = tk.as_tool().__doc__
        assert "do NOT import" in doc

    def test_tool_schema_mentions_no_import(self):
        tk = _make_toolkit()
        desc = tk.tool_schema()["function"]["description"]
        assert "do NOT import" in desc


# ── Validation integration tests ──────────────────────────────────────


class TestValidation:
    def test_errors_block_execution(self):
        tk = _make_toolkit()
        result = tk.execute_sync("import get_weather")
        assert not result.success
        assert "Validation failed" in result.error

    def test_warnings_in_output(self):
        tk = _make_toolkit()
        result = tk.execute_sync("x = ''.__class__\nprint('hi')", validate=True)
        assert result.success
        assert "Validation warnings" in result.error_output

    def test_validate_false_skips(self):
        tk = _make_toolkit()
        result = tk.execute_sync("import get_weather", validate=False)
        assert not result.success
        assert "ImportError" in result.error

    def test_dangerous_attr_blocked(self):
        tk = _make_toolkit()
        result = tk.execute_sync("x = ''.__class__.__globals__")
        assert not result.success
        assert "Validation failed" in result.error
        assert "__globals__" in result.error


# ── Timeout tests ─────────────────────────────────────────────────────


class TestTimeout:
    def test_default_timeout_is_30(self):
        tk = _make_toolkit()
        assert tk._timeout == 30.0

    def test_custom_timeout(self):
        tk = _make_toolkit(timeout=5.0)
        assert tk._timeout == 5.0

    def test_per_call_override(self):
        tk = _make_toolkit(timeout=30.0)
        result = tk.execute_sync("while True: pass", timeout=1.0, validate=False)
        assert not result.success
        assert "timed out" in result.error

    def test_as_tool_respects_timeout(self):
        tk = Toolkit([get_weather, search_database], timeout=1.0)
        fn = tk.as_tool_sync()
        result = fn("while True: pass")
        assert "timed out" in result.lower() or "validation" in result.lower()


# ── Sandbox backend tests ─────────────────────────────────────────────


class _RecordingSandbox:
    def __init__(self):
        self.calls = []

    async def execute(self, code, tools, timeout):
        self.calls.append({"code": code, "timeout": timeout})
        return ER(success=True, output="recorded")


class TestSandboxBackend:
    def test_default_is_local_sandbox(self):
        tk = _make_toolkit()
        assert isinstance(tk._sandbox, LocalSandbox)

    def test_custom_backend_used(self):
        recorder = _RecordingSandbox()
        tk = Toolkit([get_weather], sandbox=recorder)
        result = tk.execute_sync('print("hi")', validate=False)
        assert result.output == "recorded"
        assert len(recorder.calls) == 1

    def test_sandbox_receives_timeout(self):
        recorder = _RecordingSandbox()
        tk = Toolkit([get_weather], sandbox=recorder, timeout=42.0)
        tk.execute_sync('print("hi")', validate=False)
        assert recorder.calls[0]["timeout"] == 42.0


# ── Error hint tests ──────────────────────────────────────────────────


class TestErrorHint:
    """Error recovery guidance in prompts and error responses."""

    # ── Default error hint in all four surfaces ──

    def test_prompt_includes_error_recovery(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "error" in prompt.lower()
        assert "try again" in prompt.lower()

    def test_tool_prompt_includes_error_recovery(self):
        tk = _make_toolkit()
        tp = tk.tool_prompt()
        assert "error" in tp.lower()
        assert "try again" in tp.lower()

    def test_as_tool_docstring_includes_error_recovery(self):
        tk = _make_toolkit()
        doc = tk.as_tool().__doc__
        assert "error" in doc.lower()
        assert "try again" in doc.lower()

    def test_tool_schema_includes_error_recovery(self):
        tk = _make_toolkit()
        desc = tk.tool_schema()["function"]["description"]
        assert "error" in desc.lower()
        assert "try again" in desc.lower()

    # ── Custom error hint ──

    def test_custom_error_hint_in_all_surfaces(self):
        tk = _make_toolkit(error_hint="Custom recovery hint")
        assert "Custom recovery hint" in tk.prompt()
        assert "Custom recovery hint" in tk.tool_prompt()
        assert "Custom recovery hint" in tk.as_tool().__doc__
        assert "Custom recovery hint" in tk.tool_schema()["function"]["description"]

    def test_empty_error_hint_disables(self):
        tk = _make_toolkit(error_hint="")
        assert "try again" not in tk.prompt().lower()
        assert "try again" not in tk.tool_prompt().lower()
        assert "try again" not in tk.as_tool().__doc__.lower()
        assert "try again" not in tk.tool_schema()["function"]["description"].lower()
        # No prefix on error responses either
        fn = tk.as_tool_sync()
        result = fn("x = undefined_var")
        assert not result.startswith("ERROR:")

    # ── Error prefix in tool responses ──

    def test_as_tool_sync_error_prefix(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        result = fn("x = undefined_var")
        assert result.startswith("ERROR:")
        assert "try again" in result.lower()
        assert "NameError" in result

    @pytest.mark.asyncio
    async def test_as_tool_async_error_prefix(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        result = await fn("x = undefined_var")
        assert result.startswith("ERROR:")
        assert "try again" in result.lower()
        assert "NameError" in result

    def test_as_tool_sync_success_no_prefix(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        result = fn('print("hi")')
        assert not result.startswith("ERROR:")
        assert "hi" in result


# ── Non-chaining code pattern tests ──────────────────────────────────


class TestNonChainingNoAccessPattern:
    """Non-chaining surfaces should forbid accessing return values and show print pattern."""

    def test_prompt_has_no_access_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        prompt = tk.prompt()
        assert "do NOT access" in prompt
        assert "print(tool_a(...))" in prompt

    def test_tool_prompt_has_no_access_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        tp = tk.tool_prompt()
        assert "do NOT access" in tp
        assert "print(tool_a(...))" in tp

    def test_as_tool_has_no_access_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        doc = tk.as_tool().__doc__
        assert "do NOT access" in doc
        assert "print(tool_a(...))" in doc

    def test_tool_schema_has_no_access_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        desc = tk.tool_schema()["function"]["description"]
        assert "do NOT access" in desc
        assert "print(tool_a(...))" in desc

    def test_no_access_absent_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        assert "do NOT access" not in tk.prompt()
        assert "do NOT access" not in tk.tool_prompt()
        assert "do NOT access" not in tk.as_tool().__doc__
        assert "do NOT access" not in tk.tool_schema()["function"]["description"]


# ── Empty output safety net tests ─────────────────────────────────────


class TestEmptyOutputSafetyNet:
    """When chaining=False, tools called but nothing printed → corrective message."""

    def test_sync_tools_called_no_print(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        fn = tk.as_tool_sync()
        result = fn('get_weather("SF")')
        assert "No output captured" in result

    @pytest.mark.asyncio
    async def test_async_tools_called_no_print(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        fn = tk.as_tool()
        result = await fn('get_weather("SF")')
        assert "No output captured" in result

    def test_chaining_enabled_no_warning(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        fn = tk.as_tool_sync()
        result = fn('get_weather("SF")')
        assert "No output captured" not in result

    def test_print_present_no_warning(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        fn = tk.as_tool_sync()
        result = fn('print(get_weather("SF"))')
        assert "No output captured" not in result
        assert "temp" in result

    def test_no_tools_called_no_warning(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        fn = tk.as_tool_sync()
        result = fn('x = 1 + 1')
        assert "No output captured" not in result

    def test_print_in_code_but_empty_output_no_warning(self):
        """If code contains print() but output is empty, don't fire safety net."""
        tk = _make_toolkit(assist_tool_chaining=False)
        fn = tk.as_tool_sync()
        result = fn('w = get_weather("SF")\nprint(end="")')
        assert "No output captured" not in result


# ── Native async tool tests ───────────────────────────────────────────


@ez_tool
async def async_fetch(key: str) -> dict:
    """Fetch data by key.

    Args:
        key: The key to fetch
    """
    return {"key": key, "value": 42}


@ez_tool
def sync_multiply(x: int) -> int:
    """Multiply by two.

    Args:
        x: Input number
    """
    return x * 2


def _make_async_toolkit(**kwargs):
    return Toolkit([async_fetch, sync_multiply], **kwargs)


def _make_pure_async_toolkit(**kwargs):
    return Toolkit([async_fetch], **kwargs)


class TestNativeAsyncTools:
    """Tests for native async tool support via sync wrappers + parallel()."""

    def test_ez_tool_detects_async(self):
        assert async_fetch.is_async is True
        assert sync_multiply.is_async is False

    def test_has_async_tools_property(self):
        tk_async = _make_async_toolkit()
        tk_sync = _make_toolkit()
        assert tk_async._has_async_tools is True
        assert tk_sync._has_async_tools is False

    def test_prompt_no_async_def(self):
        """Async tools should NOT show 'async def' prefix — they're wrapped sync."""
        tk = _make_async_toolkit()
        prompt = tk.prompt()
        assert "async def async_fetch" not in prompt
        assert "async def sync_multiply" not in prompt
        assert "def async_fetch" in prompt
        assert "def sync_multiply" in prompt

    def test_prompt_no_await(self):
        """Prompt should not mention await — tools are called synchronously."""
        tk = _make_async_toolkit()
        prompt = tk.prompt()
        assert "await" not in prompt
        assert "async context" not in prompt

    def test_prompt_no_async_prefix_when_all_sync(self):
        """All-sync toolkit should not prefix any tool with 'async def'."""
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "async def get_weather" not in prompt
        assert "async def search_database" not in prompt
        assert "async context" not in prompt

    def test_prompt_no_to_thread(self):
        tk = _make_async_toolkit()
        prompt = tk.prompt()
        assert "to_thread" not in prompt

    def test_prompt_no_asyncio_run(self):
        tk = _make_async_toolkit()
        prompt = tk.prompt()
        assert "asyncio.run()" not in prompt

    def test_prompt_mentions_parallel(self):
        tk = _make_async_toolkit()
        prompt = tk.prompt()
        assert "parallel(" in prompt

    def test_prompt_parallel_in_postamble(self):
        """Postamble should document the parallel() helper."""
        tk = _make_async_toolkit()
        prompt = tk.prompt()
        assert "parallel()" in prompt
        assert "Do NOT call the tools inside parallel()" in prompt

    def test_tool_prompt_no_async(self):
        tk = _make_async_toolkit()
        tp = tk.tool_prompt()
        assert "async async_fetch" not in tp
        assert "await" not in tp

    def test_tool_prompt_no_to_thread(self):
        tk = _make_async_toolkit()
        tp = tk.tool_prompt()
        assert "to_thread" not in tp

    def test_parallel_in_tool_prompt(self):
        tk = _make_async_toolkit()
        tp = tk.tool_prompt()
        assert "parallel(" in tp

    def test_as_tool_no_async(self):
        tk = _make_async_toolkit()
        doc = tk.as_tool().__doc__
        assert "async async_fetch" not in doc

    def test_parallel_in_as_tool_docstring(self):
        tk = _make_async_toolkit()
        doc = tk.as_tool().__doc__
        assert "parallel(" in doc

    def test_tool_schema_no_async(self):
        tk = _make_async_toolkit()
        desc = tk.tool_schema()["function"]["description"]
        assert "async async_fetch" not in desc
        assert "parallel(" in desc

    def test_execute_async_tool(self):
        """Async tools should work via sync wrappers (no await needed)."""
        tk = _make_pure_async_toolkit()
        result = tk.execute_sync('r = async_fetch("x")\nprint(r)')
        assert result.success, f"Failed: {result.error}"
        assert "value" in result.output
        assert "42" in result.output

    def test_execute_mixed_sync_async(self):
        tk = _make_async_toolkit()
        code = """
fetched = async_fetch("hello")
doubled = sync_multiply(fetched["value"])
print(f"key={fetched['key']}, doubled={doubled}")
"""
        result = tk.execute_sync(code)
        assert result.success, f"Failed: {result.error}"
        assert "key=hello" in result.output
        assert "doubled=84" in result.output

    def test_execute_parallel(self):
        tk = _make_pure_async_toolkit()
        code = """
a, b = parallel((async_fetch, "x"), (async_fetch, "y"))
print(f"a={a['key']}, b={b['key']}")
"""
        result = tk.execute_sync(code)
        assert result.success, f"Failed: {result.error}"
        assert "a=x" in result.output
        assert "b=y" in result.output

    @pytest.mark.asyncio
    async def test_async_execute_with_async_tool(self):
        tk = _make_pure_async_toolkit()
        result = await tk.execute('r = async_fetch("test")\nprint(r)')
        assert result.success, f"Failed: {result.error}"
        assert "42" in result.output

    def test_validation_passes_without_await(self):
        """Validation should pass for sync-style async tool calls."""
        tk = _make_async_toolkit()
        result = tk.execute_sync('r = async_fetch("x")\nprint(r)')
        assert result.success, f"Failed: {result.error}"
        assert "Validation failed" not in (result.error or "")


# ── Error enrichment through Toolkit tests ────────────────────────────


class TestErrorEnrichment:
    """Tests for KeyError/AttributeError enrichment in error output."""

    def test_key_error_shows_available_keys(self):
        tk = _make_toolkit()
        result = tk.execute_sync('r = get_weather("NYC")\nprint(r["mileage"])')
        assert not result.success
        assert "Hint" in result.error_output
        assert "temp" in result.error_output or "condition" in result.error_output

    def test_attribute_error_hints_dict_syntax(self):
        tk = _make_toolkit()
        result = tk.execute_sync('r = get_weather("NYC")\nprint(r.temp)')
        assert not result.success
        assert "dict" in result.error_output

    def test_enrichment_via_as_tool_sync(self):
        tk = _make_toolkit()
        fn = tk.as_tool_sync()
        result = fn('r = get_weather("NYC")\nprint(r["mileage"])')
        assert "Hint" in result or "kmpl" in result or "temp" in result
