"""Mock MCP session for self-contained examples (no real server needed).

This module provides a pre-configured mock session that simulates an MCP
server with two tools (search, get_document), one static resource
(system config), one resource template (user profile), and one prompt
template (code_review).

Used by example_mcp_bridge.py — keeps the example focused on ez-ptc APIs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import AsyncMock


# ── Minimal MCP type stubs ────────────────────────────────────────────


@dataclass
class TextContent:
    text: str
    type: str = "text"


@dataclass
class CallToolResult:
    content: list = field(default_factory=list)
    isError: bool = False


@dataclass
class MCPTool:
    name: str
    description: str | None = None
    inputSchema: dict | None = None
    outputSchema: dict | None = None


@dataclass
class ListToolsResult:
    tools: list = field(default_factory=list)


@dataclass
class Resource:
    name: str
    uri: str
    description: str | None = None
    mimeType: str | None = None


@dataclass
class ListResourcesResult:
    resources: list = field(default_factory=list)


@dataclass
class ResourceTemplate:
    name: str
    uriTemplate: str
    description: str | None = None
    mimeType: str | None = None


@dataclass
class ListResourceTemplatesResult:
    resourceTemplates: list = field(default_factory=list)


@dataclass
class ResourceContent:
    text: str


@dataclass
class ReadResourceResult:
    contents: list = field(default_factory=list)


@dataclass
class PromptArgument:
    name: str
    description: str | None = None
    required: bool = False


@dataclass
class Prompt:
    name: str
    description: str | None = None
    arguments: list | None = None


@dataclass
class ListPromptsResult:
    prompts: list = field(default_factory=list)


@dataclass
class PromptMessage:
    role: str
    content: str


@dataclass
class GetPromptResult:
    description: str | None = None
    messages: list = field(default_factory=list)


# ── Factory ───────────────────────────────────────────────────────────


def mock_session() -> AsyncMock:
    """Build a mock MCP session with sample tools, resources, and prompts."""
    session = AsyncMock()

    # Tools
    session.list_tools.return_value = ListToolsResult(tools=[
        MCPTool(
            name="search",
            description="Search the knowledge base",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        MCPTool(
            name="get_document",
            description="Retrieve a document by ID",
            inputSchema={
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        ),
    ])

    # Static resources
    session.list_resources.return_value = ListResourcesResult(resources=[
        Resource(
            name="system config",
            uri="config://system",
            description="System configuration",
            mimeType="application/json",
        ),
    ])

    # Resource templates
    session.list_resource_templates.return_value = ListResourceTemplatesResult(
        resourceTemplates=[
            ResourceTemplate(
                name="user profile",
                uriTemplate="users/{user_id}/profile",
                description="Get a user's profile",
            ),
        ]
    )

    # Prompts
    session.list_prompts.return_value = ListPromptsResult(prompts=[
        Prompt(
            name="code_review",
            description="Review code for best practices",
            arguments=[
                PromptArgument(name="language", description="Programming language", required=True),
                PromptArgument(name="focus", description="What to focus on", required=False),
            ],
        ),
    ])

    # call_tool handler
    def _call_tool(name, arguments=None):
        if name == "search":
            return CallToolResult(content=[TextContent(
                text=json.dumps([
                    {"title": "Python Best Practices", "score": 0.95},
                    {"title": "Async Programming Guide", "score": 0.87},
                ])
            )])
        elif name == "get_document":
            return CallToolResult(content=[TextContent(
                text=json.dumps({
                    "id": arguments.get("doc_id", "?"),
                    "title": "Python Best Practices",
                    "content": "Use type hints, write tests, follow PEP 8.",
                })
            )])
        return CallToolResult(content=[TextContent(text='"ok"')])

    session.call_tool.side_effect = _call_tool

    # read_resource handler
    def _read_resource(uri):
        if "config" in uri:
            return ReadResourceResult(contents=[ResourceContent(
                text=json.dumps({"version": "2.0", "debug": False, "max_workers": 4})
            )])
        elif "profile" in uri:
            return ReadResourceResult(contents=[ResourceContent(
                text=json.dumps({"name": "Alice", "role": "engineer"})
            )])
        return ReadResourceResult(contents=[ResourceContent(text='"unknown"')])

    session.read_resource.side_effect = _read_resource

    # get_prompt handler
    session.get_prompt.return_value = GetPromptResult(
        description="Code review prompt",
        messages=[
            PromptMessage(
                role="user",
                content="You are an expert code reviewer. Review the following code for best practices, "
                        "focusing on clarity, correctness, and maintainability.",
            ),
        ],
    )

    return session
