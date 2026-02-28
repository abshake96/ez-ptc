"""Type hint to JSON schema conversion for tool functions."""

import inspect
import re
import types
import typing
from typing import Any, Callable, get_args, get_origin


def _parse_docstring(fn: Callable) -> tuple[str, dict[str, str]]:
    """Parse a function's docstring to extract description and parameter docs.

    Supports Google-style docstrings:
        Args:
            param_name: Description of param

    Returns:
        Tuple of (function description, {param_name: param_description})
    """
    doc = inspect.getdoc(fn)
    if not doc:
        return "", {}

    lines = doc.strip().split("\n")
    description_lines: list[str] = []
    param_docs: dict[str, str] = {}

    in_args = False
    current_param: str | None = None
    current_desc_lines: list[str] = []

    _SECTION_HEADERS = {
        "Args", "Arguments", "Parameters", "Params",
        "Returns", "Return", "Raises", "Yields", "Note",
        "Notes", "Example", "Examples", "References",
        "Attributes", "Todo", "See Also", "Warnings",
    }

    in_section = False  # True once we've entered any section (Args or other)

    for line in lines:
        stripped = line.strip()

        # Detect any section header like "Args:", "Returns:", etc.
        if stripped.endswith(":") and stripped.rstrip(":") in _SECTION_HEADERS:
            section_name = stripped.rstrip(":")

            # Save last param if leaving Args
            if in_args and current_param:
                param_docs[current_param] = " ".join(current_desc_lines).strip()
                current_param = None
                current_desc_lines = []

            if section_name in ("Args", "Arguments", "Parameters", "Params"):
                in_args = True
            else:
                in_args = False

            in_section = True
            continue

        if in_args:
            # Try to match "param_name: description" or "param_name (type): description"
            param_match = re.match(r"^\s{0,8}(\w+)(?:\s*\([^)]*\))?\s*:\s*(.*)", line)
            if param_match:
                # Save previous param
                if current_param:
                    param_docs[current_param] = " ".join(current_desc_lines).strip()
                current_param = param_match.group(1)
                current_desc_lines = [param_match.group(2).strip()] if param_match.group(2).strip() else []
            elif current_param and stripped:
                # Continuation line for current param
                current_desc_lines.append(stripped)
            elif not stripped and current_param:
                # Empty line may end param description
                param_docs[current_param] = " ".join(current_desc_lines).strip()
                current_param = None
                current_desc_lines = []
        elif not in_section:
            # Only collect description lines before any section header
            if stripped:
                description_lines.append(stripped)

    # Save last param if still in args
    if current_param:
        param_docs[current_param] = " ".join(current_desc_lines).strip()

    description = " ".join(description_lines).strip()
    return description, param_docs


def _type_to_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON schema dict."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Handle Optional[X] which is Union[X, None] or X | None
    if origin is typing.Union or isinstance(annotation, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            # Optional[X]
            return _type_to_schema(non_none[0])
        # General Union — just use first non-None type
        if non_none:
            return _type_to_schema(non_none[0])
        return {}

    # Handle Literal
    if origin is typing.Literal:
        values = list(args)
        if all(isinstance(v, str) for v in values):
            return {"type": "string", "enum": values}
        elif all(isinstance(v, int) for v in values):
            return {"type": "integer", "enum": values}
        return {"enum": values}

    # Handle Annotated — just use the first arg (the actual type)
    if origin is typing.Annotated:
        return _type_to_schema(args[0])

    # Handle list[X]
    if origin is list:
        schema: dict[str, Any] = {"type": "array"}
        if args:
            schema["items"] = _type_to_schema(args[0])
        return schema

    # Handle dict[K, V]
    if origin is dict:
        schema = {"type": "object"}
        if len(args) >= 2:
            schema["additionalProperties"] = _type_to_schema(args[1])
        return schema

    # Handle tuple
    if origin is tuple:
        return {"type": "array"}

    # Handle set/frozenset
    if origin in (set, frozenset):
        schema = {"type": "array"}
        if args:
            schema["items"] = _type_to_schema(args[0])
        return schema

    # Primitive types
    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }
    if annotation in type_map:
        return {"type": type_map[annotation]}

    # Plain list/dict without parameters
    if annotation is list:
        return {"type": "array"}
    if annotation is dict:
        return {"type": "object"}

    # TypedDict
    if _is_typed_dict(annotation):
        hints = typing.get_type_hints(annotation)
        properties = {k: _type_to_schema(v) for k, v in hints.items()}
        required = sorted(annotation.__required_keys__)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    # Pydantic model
    if _is_pydantic_model(annotation):
        return annotation.model_json_schema()

    return {}


def _is_pydantic_model(cls: Any) -> bool:
    """Check if a class is a Pydantic BaseModel."""
    try:
        from pydantic import BaseModel
        return isinstance(cls, type) and issubclass(cls, BaseModel)
    except ImportError:
        return False


def _is_typed_dict(cls: Any) -> bool:
    """Check if a class is a TypedDict."""
    return isinstance(cls, type) and issubclass(cls, dict) and hasattr(cls, "__required_keys__")


def _format_annotation(annotation: Any) -> str:
    """Format a type annotation as a readable string."""
    if annotation is inspect.Parameter.empty:
        return ""

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is typing.Union or isinstance(annotation, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and len(args) == 2:
            # Optional[X]
            inner = _format_annotation(non_none[0])
            return f"{inner} | None"
        return " | ".join(_format_annotation(a) for a in args)

    if origin is typing.Literal:
        return f"Literal[{', '.join(repr(a) for a in args)}]"

    if origin is typing.Annotated:
        return _format_annotation(args[0])

    if origin is list:
        if args:
            return f"list[{_format_annotation(args[0])}]"
        return "list"

    if origin is dict:
        if args:
            return f"dict[{_format_annotation(args[0])}, {_format_annotation(args[1])}]"
        return "dict"

    if origin is tuple:
        if args:
            return f"tuple[{', '.join(_format_annotation(a) for a in args)}]"
        return "tuple"

    if origin is set:
        if args:
            return f"set[{_format_annotation(args[0])}]"
        return "set"

    if origin is frozenset:
        if args:
            return f"frozenset[{_format_annotation(args[0])}]"
        return "frozenset"

    if hasattr(annotation, "__name__"):
        return annotation.__name__

    return str(annotation)


def _return_type_to_schema(fn: Callable) -> dict[str, Any] | None:
    """Extract a JSON schema from a function's return type annotation.

    Returns None for unstructured types (plain dict, list, primitives, Any, no annotation)
    that aren't useful for chaining. Returns a schema dict for structured types
    (TypedDict, Pydantic, list[TypedDict], etc.).
    """
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        sig = inspect.signature(fn)
        if sig.return_annotation is not inspect.Signature.empty:
            hints = {"return": sig.return_annotation}
        else:
            return None

    ret = hints.get("return")
    if ret is None or ret is inspect.Signature.empty:
        return None

    # Skip unstructured types
    if ret is Any:
        return None
    if ret in (dict, list, str, int, float, bool):
        return None

    origin = get_origin(ret)
    args = get_args(ret)

    # list[X] — only useful if X is structured
    if origin is list:
        if args and (_is_typed_dict(args[0]) or _is_pydantic_model(args[0])):
            return {"type": "array", "items": _type_to_schema(args[0])}
        return None

    # dict[K, V] without further structure
    if origin is dict:
        return None

    # TypedDict or Pydantic — structured
    if _is_typed_dict(ret) or _is_pydantic_model(ret):
        return _type_to_schema(ret)

    return None


def _schema_to_type_str(schema: dict[str, Any]) -> str:
    """Convert a JSON schema to a compact Python-dict-like type string.

    Examples:
        {"type": "object", "properties": {"temp": {"type": "integer"}}}
        → "{temp: int}"

        {"type": "array", "items": {"type": "object", "properties": ...}}
        → "list[{...}]"
    """
    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
    }

    schema_type = schema.get("type")

    if schema_type == "object" and "properties" in schema:
        parts = []
        for key, prop in schema["properties"].items():
            parts.append(f"{key}: {_schema_to_type_str(prop)}")
        return "{" + ", ".join(parts) + "}"

    if schema_type == "array":
        items = schema.get("items")
        if items:
            return f"list[{_schema_to_type_str(items)}]"
        return "list"

    if schema_type in type_map:
        return type_map[schema_type]

    return "Any"


def format_return_schema(schema: dict[str, Any]) -> str:
    """Format a return schema as a compact comment string.

    Returns a string like "Returns: {location: str, temp: int}"
    """
    return f"Returns: {_schema_to_type_str(schema)}"


def function_to_schema(fn: Callable) -> dict[str, Any]:
    """Extract a complete schema from a Python function.

    Returns a dict with:
        - name: function name
        - description: from docstring
        - parameters: JSON schema for the function's parameters
        - signature: human-readable function signature string
    """
    sig = inspect.signature(fn)
    description, param_docs = _parse_docstring(fn)

    # Resolve string annotations from `from __future__ import annotations`
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        # Fall back to raw annotations (e.g. for locally-defined classes)
        hints = {
            name: param.annotation
            for name, param in sig.parameters.items()
            if param.annotation is not inspect.Parameter.empty
        }
        if sig.return_annotation is not inspect.Signature.empty:
            hints["return"] = sig.return_annotation

    properties: dict[str, Any] = {}
    required: list[str] = []

    # Build signature parts
    sig_parts: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        prop: dict[str, Any] = {}

        # Get resolved type annotation
        annotation = hints.get(name, inspect.Parameter.empty)

        # Get type schema
        if annotation is not inspect.Parameter.empty:
            prop.update(_type_to_schema(annotation))

        # Add description from docstring
        if name in param_docs:
            prop["description"] = param_docs[name]

        # Handle default
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)

        properties[name] = prop

        # Build signature part
        type_str = _format_annotation(annotation)
        if param.default is not inspect.Parameter.empty:
            default_repr = repr(param.default)
            sig_parts.append(f"{name}: {type_str} = {default_repr}" if type_str else f"{name}={default_repr}")
        else:
            sig_parts.append(f"{name}: {type_str}" if type_str else name)

    # Build return type
    return_annotation = hints.get("return", inspect.Signature.empty)
    return_str = ""
    if return_annotation is not inspect.Signature.empty:
        return_str = f" -> {_format_annotation(return_annotation)}"

    signature = f"{fn.__name__}({', '.join(sig_parts)}){return_str}"

    schema: dict[str, Any] = {
        "name": fn.__name__,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
        "signature": signature,
    }

    if required:
        schema["parameters"]["required"] = required

    ret_schema = _return_type_to_schema(fn)
    if ret_schema is not None:
        schema["return_schema"] = ret_schema

    return schema
