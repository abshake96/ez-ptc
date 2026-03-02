"""ez-ptc — Advanced schema features example.

Demonstrates explicit return_schema overrides, function_to_schema()
standalone usage, Literal and Optional parameter types, and Tool
object introspection.

No API keys required.

Usage:
    uv run python examples/advanced/example_advanced_schemas.py
"""

import json
from typing import Literal, Optional

from ez_ptc import Tool, Toolkit, ez_tool, function_to_schema


# ── Explicit return_schema override ───────────────────────────────────


@ez_tool(return_schema={
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "temp_f": {"type": "number"},
        "conditions": {"type": "string"},
    },
})
def get_weather_api(city: str) -> dict:
    """Get weather from an external API (returns plain dict).

    When a tool returns a plain dict, auto-detection can't infer the
    schema. Use explicit return_schema to tell the LLM what keys
    to expect.

    Args:
        city: City name
    """
    return {"city": city, "temp_f": 72.0, "conditions": "sunny"}


def demo_explicit_return_schema():
    print("=" * 60)
    print("1. Explicit return_schema Override")
    print("=" * 60)

    # Without explicit schema, plain dict tools get no Returns: hint
    @ez_tool
    def get_weather_plain(city: str) -> dict:
        """Get weather (plain dict, no schema).

        Args:
            city: City name
        """
        return {"city": city, "temp_f": 72.0}

    toolkit_no_schema = Toolkit([get_weather_plain], assist_tool_chaining=True)
    toolkit_with_schema = Toolkit([get_weather_api], assist_tool_chaining=True)

    print("  Plain dict (no explicit schema):")
    for line in toolkit_no_schema.prompt().split("\n"):
        if "def " in line or "Returns:" in line:
            print(f"    {line}")

    print()
    print("  With explicit return_schema:")
    for line in toolkit_with_schema.prompt().split("\n"):
        if "def " in line or "Returns:" in line:
            print(f"    {line}")
    print()


# ── Literal and Optional parameter types ──────────────────────────────


@ez_tool
def search(
    query: str,
    sort_by: Literal["relevance", "price", "rating"] = "relevance",
    category: Optional[str] = None,
    max_results: int = 10,
) -> list:
    """Search products with filtering.

    Args:
        query: Search query
        sort_by: Sort order
        category: Optional category filter
        max_results: Maximum results to return
    """
    return [{"name": f"Result for '{query}'", "sort": sort_by, "category": category}]


def demo_literal_and_optional():
    print("=" * 60)
    print("2. Literal and Optional Parameter Types")
    print("=" * 60)

    # function_to_schema() shows exactly what the LLM sees
    schema = function_to_schema(search.fn)

    print("  Schema properties:")
    for name, prop in schema["parameters"]["properties"].items():
        print(f"    {name}: {json.dumps(prop)}")
    print()
    print(f"  Signature: {schema['signature']}")
    print()


# ── function_to_schema() standalone usage ─────────────────────────────


def demo_function_to_schema():
    print("=" * 60)
    print("3. function_to_schema() — Standalone Schema Extraction")
    print("=" * 60)

    # Works on any function, not just @ez_tool-decorated ones
    def calculate_shipping(
        weight_kg: float,
        destination: str,
        express: bool = False,
    ) -> dict:
        """Calculate shipping cost.

        Args:
            weight_kg: Package weight in kilograms
            destination: Destination country code
            express: Whether to use express shipping
        """
        return {"cost": weight_kg * 5.0}

    schema = function_to_schema(calculate_shipping)

    print(f"  Name: {schema['name']}")
    print(f"  Description: {schema['description']}")
    print(f"  Signature: {schema['signature']}")
    print(f"  Parameters: {json.dumps(schema['parameters'], indent=4)}")
    print(f"  Return schema: {schema.get('return_schema', 'None (plain dict)')}")
    print()


# ── Tool object introspection ─────────────────────────────────────────


def demo_tool_introspection():
    print("=" * 60)
    print("4. Tool Object Introspection")
    print("=" * 60)

    tool: Tool = get_weather_api  # @ez_tool returns a Tool instance

    print(f"  tool.name: {tool.name}")
    print(f"  tool.description: {tool.description}")
    print(f"  tool.signature: {tool.signature}")
    print(f"  tool.return_schema: {tool.return_schema}")
    print(f"  tool.parameters: {json.dumps(tool.parameters, indent=4)}")
    print()

    # Tool is callable
    result = tool("San Francisco")
    print(f"  Direct call result: {result}")
    print()

    # Iterate toolkit
    toolkit = Toolkit([get_weather_api, search])
    print(f"  Toolkit has {len(toolkit)} tools:")
    for t in toolkit:
        print(f"    - {t.name}: {t.description}")
    print()


if __name__ == "__main__":
    demo_explicit_return_schema()
    demo_literal_and_optional()
    demo_function_to_schema()
    demo_tool_introspection()
