"""ez-ptc usage example — demonstrates both prompt mode and tool mode."""

from ez_ptc import Toolkit, ez_tool


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

    result = toolkit.execute(code)
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
    execute_fn = toolkit.as_tool()
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


if __name__ == "__main__":
    demo_prompt_mode()
    demo_tool_mode()
