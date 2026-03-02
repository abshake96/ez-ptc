"""ez-ptc usage example — demonstrates prompt mode, tool mode, validation, and timeout.

No API keys required.

Usage:
    uv run python examples/basics/example_demo.py
"""

from ez_ptc import Toolkit, ez_tool, validate_code


# 1. Define tools with @ez_tool
@ez_tool
def get_weather(location: str, unit: str = "celsius") -> dict:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    # Simulated response
    return {"temp": 22, "condition": "sunny", "unit": unit}


@ez_tool
def search_database(query: str, limit: int = 10) -> list[dict]:
    """Search the product database.

    Args:
        query: Search query string
        limit: Maximum number of results
    """
    # Simulated response
    return [{"id": i, "name": f"{query} item {i}", "price": 9.99 + i} for i in range(limit)]


# 2. Create a toolkit
toolkit = Toolkit([get_weather, search_database])


def demo_prompt_mode():
    """Demonstrate Mode 1: Prompt mode (framework-free)."""
    print("=" * 60)
    print("MODE 1: Prompt Mode")
    print("=" * 60)

    # Generate instruction block for system prompt
    prompt = toolkit.prompt()
    print("\n--- Generated Prompt ---")
    print(prompt)

    # Simulate an LLM response containing a code block
    llm_response = '''I'll check the weather and find relevant products for you.

```python
weather = get_weather("San Francisco, CA")
if weather["condition"] == "sunny":
    products = search_database("sunglasses", limit=3)
else:
    products = search_database("umbrellas", limit=3)

print(f"Weather in SF: {weather['condition']}, {weather['temp']}°C")
print(f"Recommended products ({len(products)}):")
for p in products:
    print(f"  - {p['name']}: ${p['price']:.2f}")
```'''

    # Extract and execute
    code = toolkit.extract_code(llm_response)
    print("\n--- Extracted Code ---")
    print(code)

    result = toolkit.execute_sync(code)
    print("\n--- Execution Result ---")
    print(f"Output: {result.output}")
    print(f"Tool calls: {len(result.tool_calls)}")
    print(f"Success: {result.success}")


def demo_tool_mode():
    """Demonstrate Mode 2: Tool mode (native framework integration)."""
    print("\n" + "=" * 60)
    print("MODE 2: Tool Mode")
    print("=" * 60)

    # Get a meta-tool function any framework can register
    execute_fn = toolkit.as_tool_sync()
    print(f"\nFunction name: {execute_fn.__name__}")
    print(f"Annotations: {execute_fn.__annotations__}")

    # Get schema for framework registration
    schema = toolkit.tool_schema()
    print(f"\nOpenAI tool schema: {schema['function']['name']}")

    # Simulate LLM calling the meta-tool
    code = """
results = []
for city in ["New York", "Los Angeles", "Chicago"]:
    w = get_weather(city)
    results.append(f"{city}: {w['condition']} ({w['temp']}°C)")
print("Weather Report:")
print("\\n".join(results))
"""
    output = execute_fn(code)
    print(f"\n--- Tool Output ---")
    print(output)


def demo_validation():
    """Demonstrate Mode 3: Pre-flight code validation."""
    print("\n" + "=" * 60)
    print("VALIDATION: Pre-flight AST Checks")
    print("=" * 60)

    # Good code passes validation
    good_code = 'weather = get_weather("NYC")\nprint(weather)'
    vr = validate_code(good_code, {"get_weather", "search_database"})
    print(f"\n--- Valid Code ---")
    print(f"  is_safe: {vr.is_safe}, errors: {vr.errors}, warnings: {vr.warnings}")

    # LLM tries to import a tool (common mistake)
    bad_code = 'import get_weather\nget_weather("NYC")'
    vr = validate_code(bad_code, {"get_weather", "search_database"})
    print(f"\n--- Import Tool (blocked) ---")
    print(f"  is_safe: {vr.is_safe}")
    print(f"  errors: {vr.errors}")

    # Dangerous dunder access (blocked)
    bad_code2 = 'x = "".__class__.__bases__[0].__subclasses__()'
    vr = validate_code(bad_code2, {"get_weather"})
    print(f"\n--- Sandbox Escape Attempt (blocked) ---")
    print(f"  is_safe: {vr.is_safe}")
    print(f"  errors: {vr.errors}")

    # Integrated: validation blocks execution
    result = toolkit.execute_sync("import get_weather\nprint('hi')")
    print(f"\n--- Toolkit.execute_sync() with validation ---")
    print(f"  success: {result.success}")
    print(f"  error: {result.error}")


def demo_timeout():
    """Demonstrate configurable timeout."""
    print("\n" + "=" * 60)
    print("TIMEOUT: Configurable Execution Limits")
    print("=" * 60)

    # Toolkit-level timeout
    fast_toolkit = Toolkit([get_weather, search_database], timeout=2.0)
    print(f"\n  Toolkit timeout: {fast_toolkit._timeout}s")

    # Per-call timeout override
    result = fast_toolkit.execute_sync(
        "x = 0\nwhile True:\n    x += 1",
        timeout=1.0,
        validate=False,
    )
    print(f"  Infinite loop with timeout=1.0s:")
    print(f"    success: {result.success}")
    print(f"    error: {result.error}")

    # Return value capture (like a REPL)
    result = toolkit.execute_sync("get_weather('NYC')")
    print(f"\n  Return value (no print):")
    print(f"    return_value: {result.return_value}")
    print(f"    to_string(): {result.to_string()[:60]}...")


if __name__ == "__main__":
    demo_prompt_mode()
    demo_tool_mode()
    demo_validation()
    demo_timeout()
