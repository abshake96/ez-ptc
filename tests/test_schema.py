"""Tests for schema.py — type hint to JSON schema conversion."""

from typing import Annotated, Literal, Optional, TypedDict

from ez_ptc.schema import (
    _return_type_to_schema,
    _type_to_schema,
    format_return_schema,
    function_to_schema,
)


def test_basic_types():
    def fn(name: str, age: int, score: float, active: bool) -> str:
        """A basic function."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["name"] == {"type": "string"}
    assert props["age"] == {"type": "integer"}
    assert props["score"] == {"type": "number"}
    assert props["active"] == {"type": "boolean"}
    assert schema["parameters"]["required"] == ["name", "age", "score", "active"]


def test_defaults():
    def fn(name: str, limit: int = 10, active: bool = True) -> None:
        """A function with defaults."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["limit"]["default"] == 10
    assert props["active"]["default"] is True
    assert schema["parameters"]["required"] == ["name"]


def test_list_type():
    def fn(items: list[str], nested: list[dict]) -> list[int]:
        """List params."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["items"] == {"type": "array", "items": {"type": "string"}}
    assert props["nested"] == {"type": "array", "items": {"type": "object"}}


def test_dict_type():
    def fn(data: dict[str, int]) -> dict:
        """Dict params."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["data"] == {"type": "object", "additionalProperties": {"type": "integer"}}


def test_optional_type():
    def fn(name: str, label: str | None = None) -> None:
        """Optional param."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["label"]["type"] == "string"
    assert props["label"]["default"] is None


def test_literal_type():
    def fn(unit: Literal["celsius", "fahrenheit"]) -> None:
        """Literal param."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["unit"]["type"] == "string"
    assert props["unit"]["enum"] == ["celsius", "fahrenheit"]


def test_annotated_type():
    def fn(name: Annotated[str, "The person's name"]) -> None:
        """Annotated param."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert props["name"]["type"] == "string"


def test_docstring_parsing():
    def fn(location: str, unit: str = "celsius") -> dict:
        """Get current weather for a location.

        Args:
            location: City and state, e.g. "San Francisco, CA"
            unit: Temperature unit - "celsius" or "fahrenheit"
        """
        ...

    schema = function_to_schema(fn)
    assert schema["description"] == 'Get current weather for a location.'
    props = schema["parameters"]["properties"]
    assert props["location"]["description"] == 'City and state, e.g. "San Francisco, CA"'
    assert props["unit"]["description"] == 'Temperature unit - "celsius" or "fahrenheit"'


def test_no_docstring():
    def fn(x: int) -> int:
        ...

    schema = function_to_schema(fn)
    assert schema["description"] == ""
    assert schema["name"] == "fn"


def test_signature_generation():
    def get_weather(location: str, unit: str = "celsius") -> dict:
        """Get weather."""
        ...

    schema = function_to_schema(get_weather)
    assert schema["signature"] == "get_weather(location: str, unit: str = 'celsius') -> dict"


def test_no_annotations():
    def fn(x, y=5):
        """No type hints."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    assert "x" in props
    assert "y" in props
    assert props["y"]["default"] == 5


def test_pydantic_model():
    from pydantic import BaseModel

    class Location(BaseModel):
        city: str
        state: str

    def fn(loc: Location) -> str:
        """Takes a pydantic model."""
        ...

    schema = function_to_schema(fn)
    props = schema["parameters"]["properties"]
    # Pydantic model generates a full schema
    assert "properties" in props["loc"]
    assert "city" in props["loc"]["properties"]


def test_complex_docstring_with_returns():
    def fn(query: str, limit: int = 10) -> list[dict]:
        """Search the database.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching records
        """
        ...

    schema = function_to_schema(fn)
    assert schema["description"] == "Search the database."
    props = schema["parameters"]["properties"]
    assert props["query"]["description"] == "Search query string"
    assert props["limit"]["description"] == "Maximum number of results"


# ── TypedDict schema tests ───────────────────────────────────────────


class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str


class Product(TypedDict):
    id: int
    name: str
    price: float
    tags: list[str]


def test_typed_dict_schema():
    schema = _type_to_schema(WeatherResult)
    assert schema["type"] == "object"
    assert schema["properties"]["location"] == {"type": "string"}
    assert schema["properties"]["temp"] == {"type": "integer"}
    assert schema["properties"]["unit"] == {"type": "string"}
    assert schema["properties"]["condition"] == {"type": "string"}
    assert sorted(schema["required"]) == ["condition", "location", "temp", "unit"]


def test_typed_dict_nested_types():
    schema = _type_to_schema(Product)
    assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
    assert schema["properties"]["price"] == {"type": "number"}


# ── _return_type_to_schema tests ─────────────────────────────────────


def test_return_type_typed_dict():
    def fn(x: str) -> WeatherResult:
        ...

    schema = _return_type_to_schema(fn)
    assert schema is not None
    assert schema["type"] == "object"
    assert "location" in schema["properties"]


def test_return_type_pydantic():
    from pydantic import BaseModel

    class Result(BaseModel):
        score: float
        label: str

    def fn(x: str) -> Result:
        ...

    schema = _return_type_to_schema(fn)
    assert schema is not None
    assert "properties" in schema
    assert "score" in schema["properties"]


def test_return_type_plain_dict_returns_none():
    def fn(x: str) -> dict:
        ...

    assert _return_type_to_schema(fn) is None


def test_return_type_plain_list_returns_none():
    def fn(x: str) -> list:
        ...

    assert _return_type_to_schema(fn) is None


def test_return_type_primitive_returns_none():
    def fn(x: str) -> str:
        ...

    assert _return_type_to_schema(fn) is None


def test_return_type_no_annotation_returns_none():
    def fn(x):
        ...

    assert _return_type_to_schema(fn) is None


def test_return_type_list_typed_dict():
    def fn(x: str) -> list[Product]:
        ...

    schema = _return_type_to_schema(fn)
    assert schema is not None
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "object"
    assert "name" in schema["items"]["properties"]


def test_return_type_list_plain_dict_returns_none():
    def fn(x: str) -> list[dict]:
        ...

    assert _return_type_to_schema(fn) is None


# ── format_return_schema tests ───────────────────────────────────────


def test_format_return_schema_object():
    schema = {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "temp": {"type": "integer"},
        },
    }
    result = format_return_schema(schema)
    assert result == "Returns: {location: str, temp: int}"


def test_format_return_schema_list():
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            },
        },
    }
    result = format_return_schema(schema)
    assert result == "Returns: list[{id: int, name: str}]"


# ── function_to_schema includes return_schema ────────────────────────


def test_function_to_schema_includes_return_schema():
    def fn(x: str) -> WeatherResult:
        """Get weather."""
        ...

    schema = function_to_schema(fn)
    assert "return_schema" in schema
    assert schema["return_schema"]["type"] == "object"


def test_function_to_schema_no_return_schema_for_plain_dict():
    def fn(x: str) -> dict:
        """Get something."""
        ...

    schema = function_to_schema(fn)
    assert "return_schema" not in schema


# ── _format_annotation tests ─────────────────────────────────────────


def test_format_annotation_generics():
    from ez_ptc.schema import _format_annotation

    assert _format_annotation(set[int]) == "set[int]"
    assert _format_annotation(tuple[str, int]) == "tuple[str, int]"
    assert _format_annotation(frozenset[str]) == "frozenset[str]"
    assert _format_annotation(list[dict[str, int]]) == "list[dict[str, int]]"
