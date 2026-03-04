"""MCP Tool Bridge — wrap MCP server tools and resources as ez-ptc Tool objects."""

from __future__ import annotations

import json
import re
from typing import Any

try:
    from mcp import ClientSession
except ImportError:
    raise ImportError(
        "MCP support requires the 'mcp' package. Install it with: "
        "uv add 'ez-ptc[mcp]'  or  pip install 'ez-ptc[mcp]'"
    )

from .tool import Tool


# ── JSON Schema type → Python type string ────────────────────────────

_JSON_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def _schema_to_python_type(schema: dict[str, Any]) -> str:
    """Convert a JSON Schema type to a Python type string."""
    json_type = schema.get("type", "")
    if json_type == "array":
        items = schema.get("items")
        if items:
            return f"list[{_schema_to_python_type(items)}]"
        return "list"
    if json_type == "object":
        props = schema.get("properties")
        if props:
            parts = [f"{k}: {_schema_to_python_type(v)}" for k, v in props.items()]
            return "dict"  # Keep signature simple
        return "dict"
    return _JSON_TYPE_MAP.get(json_type, "Any")


# ── Name sanitization ────────────────────────────────────────────────

def _sanitize_name(name: str) -> str:
    """Convert a name to a valid Python identifier."""
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # Ensure it doesn't start with a digit
    if sanitized and sanitized[0].isdigit():
        sanitized = "_" + sanitized
    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Strip trailing underscores (but not leading — they may be needed for digit-prefixed names)
    sanitized = sanitized.rstrip("_")
    return sanitized or "unnamed"


# ── URI template parsing ─────────────────────────────────────────────

def _parse_uri_template(template: str) -> list[str]:
    """Extract {variable} placeholder names from a URI template."""
    return re.findall(r"\{(\w+)\}", template)


# ── Signature synthesis ──────────────────────────────────────────────

def _synthesize_signature(name: str, input_schema: dict[str, Any] | None) -> str:
    """Build a human-readable signature from an MCP tool's inputSchema.

    Example: "search(query: str, limit: int = 10)"
    """
    if not input_schema:
        return f"{name}()"

    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    parts = []
    for param_name, param_schema in properties.items():
        type_str = _schema_to_python_type(param_schema)
        if param_name in required:
            parts.append(f"{param_name}: {type_str}")
        else:
            default = param_schema.get("default")
            default_repr = repr(default) if default is not None else "None"
            parts.append(f"{param_name}: {type_str} = {default_repr}")

    return f"{name}({', '.join(parts)})"


# ── Result processing ────────────────────────────────────────────────

def _process_call_result(result: Any) -> Any:
    """Convert a CallToolResult to a plain Python value.

    - If isError is True, raises RuntimeError.
    - Text content is JSON-parsed if valid, else returned as string.
    - Multiple content blocks are returned as a list.
    """
    if result.isError:
        texts = []
        for block in result.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        raise RuntimeError("MCP tool error: " + "\n".join(texts))

    values = []
    for block in result.content:
        if hasattr(block, "text"):
            try:
                values.append(json.loads(block.text))
            except (json.JSONDecodeError, TypeError):
                values.append(block.text)
        elif hasattr(block, "data"):
            values.append(block.data)

    if len(values) == 1:
        return values[0]
    return values


def _process_resource_result(result: Any) -> Any:
    """Convert a ReadResourceResult to a plain Python value."""
    values = []
    for block in result.contents:
        if hasattr(block, "text"):
            try:
                values.append(json.loads(block.text))
            except (json.JSONDecodeError, TypeError):
                values.append(block.text)
        elif hasattr(block, "data"):
            values.append(block.data)

    if len(values) == 1:
        return values[0]
    return values


# ── Wrapper factories ────────────────────────────────────────────────

def _make_mcp_tool_fn(
    session: ClientSession,
    tool_name: str,
    param_names: list[str],
    description: str = "",
) -> Any:
    """Factory: returns an async wrapper that calls session.call_tool().

    Supports positional args by mapping them to param_names order.
    """
    async def _mcp_tool_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Map positional args to named params
        arguments = {}
        for i, val in enumerate(args):
            if i < len(param_names):
                arguments[param_names[i]] = val
        arguments.update(kwargs)

        result = await session.call_tool(tool_name, arguments=arguments)
        return _process_call_result(result)

    _mcp_tool_wrapper.__name__ = tool_name
    _mcp_tool_wrapper.__doc__ = description
    return _mcp_tool_wrapper


def _make_resource_fn(session: ClientSession, uri: str, name: str = "", description: str = "") -> Any:
    """Factory: returns an async zero-arg wrapper that reads a static resource."""
    async def _resource_wrapper() -> Any:
        result = await session.read_resource(uri)
        return _process_resource_result(result)

    _resource_wrapper.__name__ = name
    _resource_wrapper.__doc__ = description
    return _resource_wrapper


def _make_resource_template_fn(
    session: ClientSession,
    uri_template: str,
    param_names: list[str],
    name: str = "",
    description: str = "",
) -> Any:
    """Factory: returns an async wrapper that fills a URI template and reads."""
    async def _template_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Map positional args to named params
        arguments = {}
        for i, val in enumerate(args):
            if i < len(param_names):
                arguments[param_names[i]] = val
        arguments.update(kwargs)

        # Fill template
        uri = uri_template
        for param_name, value in arguments.items():
            uri = uri.replace(f"{{{param_name}}}", str(value))

        result = await session.read_resource(uri)
        return _process_resource_result(result)

    _template_wrapper.__name__ = name
    _template_wrapper.__doc__ = description
    return _template_wrapper


# ── Build parameter schema for resource templates ────────────────────

def _build_template_params_schema(param_names: list[str]) -> dict[str, Any]:
    """Build a JSON Schema parameters dict for URI template variables."""
    properties = {name: {"type": "string"} for name in param_names}
    return {
        "type": "object",
        "properties": properties,
        "required": param_names,
    }


def _build_template_signature(name: str, param_names: list[str]) -> str:
    """Build a human-readable signature for a resource template tool."""
    parts = [f"{p}: str" for p in param_names]
    return f"{name}({', '.join(parts)})"


# ── Public API ───────────────────────────────────────────────────────

async def tools_from_mcp(
    session: ClientSession,
    *,
    tool_names: list[str] | None = None,
    include_resources: bool = True,
    return_schemas: dict[str, dict[str, Any]] | None = None,
) -> list[Tool]:
    """Discover MCP tools and resources, wrap as ez-ptc Tool objects.

    Args:
        session: An active MCP ClientSession.
        tool_names: Optional filter — only include tools whose names match.
        include_resources: Whether to wrap resources/templates as tools (default True).
        return_schemas: Optional mapping of tool name → return schema dict.
            Overrides MCP ``outputSchema`` when provided. Use this to enable
            ``assist_tool_chaining`` for MCP tools that lack ``outputSchema``.

    Returns:
        List of ez-ptc Tool objects ready for use in a Toolkit.
    """
    tools: list[Tool] = []

    # ── Wrap MCP tools ──
    list_tools_result = await session.list_tools()
    for mcp_tool in list_tools_result.tools:
        name = mcp_tool.name

        input_schema = mcp_tool.inputSchema
        param_names = list((input_schema or {}).get("properties", {}).keys())
        signature = _synthesize_signature(name, input_schema)
        description = mcp_tool.description or ""
        fn = _make_mcp_tool_fn(session, name, param_names, description)

        # Build ez-ptc parameter schema
        parameters: dict[str, Any] = {"type": "object", "properties": {}}
        if input_schema:
            parameters["properties"] = input_schema.get("properties", {})
            if "required" in input_schema:
                parameters["required"] = input_schema["required"]

        # Priority: user-provided return_schemas > MCP outputSchema
        return_schema = None
        if return_schemas and name in return_schemas:
            return_schema = return_schemas[name]
        elif getattr(mcp_tool, "outputSchema", None):
            return_schema = mcp_tool.outputSchema

        tool = Tool(
            name=name,
            description=description,
            parameters=parameters,
            fn=fn,
            signature=signature,
            return_schema=return_schema,
            is_async=True,
        )
        tools.append(tool)

    # ── Wrap static resources ──
    if include_resources:
        list_resources_result = await session.list_resources()
        for resource in list_resources_result.resources:
            resource_name = "read_" + _sanitize_name(resource.name)
            desc = resource.description or f"Read resource: {resource.name}"
            if resource.mimeType:
                desc += f" (MIME: {resource.mimeType})"
            fn = _make_resource_fn(session, str(resource.uri), resource_name, desc)

            # Check user-provided return schema for resource tools
            resource_return_schema = None
            if return_schemas and resource_name in return_schemas:
                resource_return_schema = return_schemas[resource_name]

            tool = Tool(
                name=resource_name,
                description=desc,
                parameters={"type": "object", "properties": {}},
                fn=fn,
                signature=f"{resource_name}()",
                return_schema=resource_return_schema,
                is_async=True,
            )
            tools.append(tool)

        # ── Wrap resource templates ──
        list_templates_result = await session.list_resource_templates()
        for template in list_templates_result.resourceTemplates:
            template_name = "read_" + _sanitize_name(template.name)
            param_names = _parse_uri_template(template.uriTemplate)
            desc = template.description or f"Read resource: {template.name}"
            if template.mimeType:
                desc += f" (MIME: {template.mimeType})"
            fn = _make_resource_template_fn(
                session, template.uriTemplate, param_names, template_name, desc
            )

            parameters = _build_template_params_schema(param_names)
            signature = _build_template_signature(template_name, param_names)

            # Check user-provided return schema for template tools
            template_return_schema = None
            if return_schemas and template_name in return_schemas:
                template_return_schema = return_schemas[template_name]

            tool = Tool(
                name=template_name,
                description=desc,
                parameters=parameters,
                fn=fn,
                signature=signature,
                return_schema=template_return_schema,
                is_async=True,
            )
            tools.append(tool)

    # Apply name filter
    if tool_names is not None:
        name_set = set(tool_names)
        tools = [t for t in tools if t.name in name_set]

    return tools


async def get_mcp_prompt(
    session: ClientSession,
    name: str,
    arguments: dict[str, str] | None = None,
) -> str:
    """Fetch and expand an MCP prompt template.

    Args:
        session: An active MCP ClientSession.
        name: The prompt name to fetch.
        arguments: Optional arguments to fill the prompt template.

    Returns:
        The expanded prompt text content.
    """
    result = await session.get_prompt(name, arguments=arguments)

    texts = []
    for message in result.messages:
        content = message.content
        if hasattr(content, "text"):
            texts.append(content.text)
        elif isinstance(content, str):
            texts.append(content)

    return "\n\n".join(texts)


async def list_mcp_prompts(session: ClientSession) -> list[dict[str, Any]]:
    """List available MCP prompts with their arguments.

    Args:
        session: An active MCP ClientSession.

    Returns:
        List of dicts with name, description, and arguments info.
    """
    result = await session.list_prompts()

    prompts = []
    for prompt in result.prompts:
        args = []
        if prompt.arguments:
            for arg in prompt.arguments:
                args.append({
                    "name": arg.name,
                    "description": getattr(arg, "description", None),
                    "required": getattr(arg, "required", False),
                })

        prompts.append({
            "name": prompt.name,
            "description": prompt.description or "",
            "arguments": args,
        })

    return prompts
