"""Tests for toolkit.py — Toolkit class."""

from typing import TypedDict

from ez_ptc import ExecutionResult, Toolkit, ez_tool


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
        assert "asyncio" in prompt
        assert "import" in prompt.lower()

    def test_default_prompt_mentions_restrictions(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "blocked" in prompt.lower() or "no file" in prompt.lower()

    def test_default_prompt_mentions_parallel(self):
        tk = _make_toolkit()
        prompt = tk.prompt()
        assert "asyncio" in prompt
        assert "parallel" in prompt.lower() or "gather" in prompt.lower()

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

    def test_execution_success(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        result = fn('print("hello from tool mode")')
        assert "hello from tool mode" in result

    def test_execution_with_tools(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        result = fn('w = get_weather("SF")\nprint(w["condition"])')
        assert "sunny" in result

    def test_execution_failure(self):
        tk = _make_toolkit()
        fn = tk.as_tool()
        result = fn("x = undefined_var")
        assert "NameError" in result


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
        result = tk.execute('print("test")')
        assert result.success
        assert "test" in result.output

    def test_execute_with_tools(self):
        tk = _make_toolkit()
        code = """
weather = get_weather("Boston", unit="fahrenheit")
products = search_database("coats", limit=3)
print(f"Temp: {weather['temp']}, Products: {len(products)}")
"""
        result = tk.execute(code)
        assert result.success
        assert "22" in result.output
        assert "3" in result.output
        assert len(result.tool_calls) == 2

    def test_execute_error(self):
        tk = _make_toolkit()
        result = tk.execute("1/0")
        assert not result.success
        assert "ZeroDivisionError" in result.error


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
        result = tk.execute(code)
        assert result.success
        assert "sunny" in result.output
        assert "3" in result.output
        assert len(result.tool_calls) == 2

    def test_tool_mode_flow(self):
        """Simulate the full tool mode flow."""
        tk = _make_toolkit()

        # 1. Get meta-tool
        execute_fn = tk.as_tool()

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
        assert "asyncio" in tp
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
        assert "print()" in prompt

    def test_postamble_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        prompt = tk.prompt()
        assert "Chain results" in prompt

    def test_tool_prompt_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        tp = tk.tool_prompt()
        assert "Chain results" not in tp

    def test_tool_prompt_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        tp = tk.tool_prompt()
        assert "Chain results" in tp

    def test_as_tool_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        doc = tk.as_tool().__doc__
        assert "chain between" not in doc.lower()

    def test_as_tool_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        doc = tk.as_tool().__doc__
        assert "chain between" in doc.lower()

    def test_tool_schema_no_chain_when_disabled(self):
        tk = _make_toolkit(assist_tool_chaining=False)
        desc = tk.tool_schema()["function"]["description"]
        assert "chain between" not in desc.lower()

    def test_tool_schema_chains_when_enabled(self):
        tk = _make_toolkit(assist_tool_chaining=True)
        desc = tk.tool_schema()["function"]["description"]
        assert "chain between" in desc.lower()
