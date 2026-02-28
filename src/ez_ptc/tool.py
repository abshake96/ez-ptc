"""Tool class and @ez_tool decorator."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Callable

from .schema import function_to_schema


@dataclass
class Tool:
    """A wrapped function with metadata for use in a Toolkit.

    Attributes:
        name: Function name
        description: Human-readable description from docstring
        parameters: JSON schema for the function's parameters
        fn: The actual callable function
        signature: Human-readable signature string
        return_schema: Optional JSON schema for the return type
    """

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable
    signature: str
    return_schema: dict[str, Any] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Tool({self.name})"


def ez_tool(
    fn: Callable | None = None,
    *,
    return_schema: dict[str, Any] | None = None,
) -> Tool | Callable[[Callable], Tool]:
    """Decorator that wraps a function as a Tool.

    Named ez_tool to avoid clashing with @tool from LangChain/CrewAI/etc.

    Usage:
        @ez_tool
        def get_weather(location: str) -> dict:
            \"\"\"Get weather for a location.\"\"\"
            return {"temp": 22}

        @ez_tool(return_schema={"type": "object", "properties": {...}})
        def get_weather(location: str) -> dict:
            \"\"\"Get weather for a location.\"\"\"
            return {"temp": 22}
    """
    def _wrap(f: Callable) -> Tool:
        schema = function_to_schema(f)
        # Explicit return_schema takes priority over auto-detected
        rs = return_schema if return_schema is not None else schema.get("return_schema")
        tool = Tool(
            name=schema["name"],
            description=schema["description"],
            parameters=schema["parameters"],
            fn=f,
            signature=schema["signature"],
            return_schema=rs,
        )
        functools.update_wrapper(tool, f)
        return tool

    if fn is not None:
        # Bare @ez_tool usage
        return _wrap(fn)
    # @ez_tool(...) usage — return the decorator
    return _wrap
