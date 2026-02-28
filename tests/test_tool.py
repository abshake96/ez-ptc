"""Tests for tool.py — Tool class and @ez_tool decorator."""

from typing import TypedDict

from ez_ptc import Tool, ez_tool


def test_ez_tool_decorator():
    @ez_tool
    def greet(name: str) -> str:
        """Greet someone.

        Args:
            name: Person's name
        """
        return f"Hello, {name}!"

    assert isinstance(greet, Tool)
    assert greet.name == "greet"
    assert greet.description == "Greet someone."
    assert "name" in greet.parameters["properties"]


def test_tool_callable():
    @ez_tool
    def add(a: int, b: int) -> int:
        """Add two numbers.

        Args:
            a: First number
            b: Second number
        """
        return a + b

    result = add(3, 4)
    assert result == 7

    result = add(a=10, b=20)
    assert result == 30


def test_tool_repr():
    @ez_tool
    def my_func(x: str) -> str:
        """A function."""
        return x

    assert repr(my_func) == "Tool(my_func)"


def test_tool_preserves_function_metadata():
    @ez_tool
    def documented_func(x: str) -> str:
        """This is the docstring."""
        return x

    # functools.update_wrapper should preserve these
    assert documented_func.__doc__ == "This is the docstring."
    assert documented_func.__wrapped__ is not None


def test_tool_with_defaults():
    @ez_tool
    def search(query: str, limit: int = 10) -> list:
        """Search.

        Args:
            query: Query string
            limit: Max results
        """
        return []

    assert search.parameters["properties"]["limit"]["default"] == 10
    assert search.parameters["required"] == ["query"]


def test_tool_signature():
    @ez_tool
    def get_weather(location: str, unit: str = "celsius") -> dict:
        """Get weather.

        Args:
            location: Location string
            unit: Unit of temp
        """
        return {}

    assert "get_weather(" in get_weather.signature
    assert "location: str" in get_weather.signature
    assert "-> dict" in get_weather.signature


# ── return_schema tests ──────────────────────────────────────────────


class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str


def test_ez_tool_bare_still_works():
    @ez_tool
    def greet(name: str) -> str:
        """Say hi."""
        return f"Hi {name}"

    assert isinstance(greet, Tool)
    assert greet("world") == "Hi world"


def test_ez_tool_auto_detects_return_schema():
    @ez_tool
    def get_weather(location: str) -> WeatherResult:
        """Get weather."""
        return {"location": location, "temp": 22, "unit": "celsius"}

    assert get_weather.return_schema is not None
    assert get_weather.return_schema["type"] == "object"
    assert "location" in get_weather.return_schema["properties"]


def test_ez_tool_explicit_return_schema():
    explicit_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
    }

    @ez_tool(return_schema=explicit_schema)
    def get_point(name: str) -> dict:
        """Get a point."""
        return {"x": 1, "y": 2}

    assert get_point.return_schema is explicit_schema


def test_ez_tool_no_return_schema_for_plain_dict():
    @ez_tool
    def get_data(x: str) -> dict:
        """Get data."""
        return {}

    assert get_data.return_schema is None


def test_ez_tool_explicit_overrides_auto():
    explicit_schema = {"type": "object", "properties": {"custom": {"type": "string"}}}

    @ez_tool(return_schema=explicit_schema)
    def get_weather(location: str) -> WeatherResult:
        """Get weather."""
        return {"location": location, "temp": 22, "unit": "celsius"}

    assert get_weather.return_schema is explicit_schema
