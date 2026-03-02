"""Tests for MCP Tool Bridge (mock-based, no real MCP server needed)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ez_ptc.tool import Tool


# ── Mock MCP types ───────────────────────────────────────────────────


@dataclass
class MockTextContent:
    text: str
    type: str = "text"


@dataclass
class MockImageContent:
    data: str
    mimeType: str = "image/png"
    type: str = "image"


@dataclass
class MockCallToolResult:
    content: list = field(default_factory=list)
    isError: bool = False


@dataclass
class MockMCPTool:
    name: str
    description: str | None = None
    inputSchema: dict | None = None
    outputSchema: dict | None = None


@dataclass
class MockListToolsResult:
    tools: list[MockMCPTool] = field(default_factory=list)


@dataclass
class MockResource:
    name: str
    uri: str
    description: str | None = None
    mimeType: str | None = None


@dataclass
class MockListResourcesResult:
    resources: list[MockResource] = field(default_factory=list)


@dataclass
class MockResourceTemplate:
    name: str
    uriTemplate: str
    description: str | None = None
    mimeType: str | None = None


@dataclass
class MockListResourceTemplatesResult:
    resourceTemplates: list[MockResourceTemplate] = field(default_factory=list)


@dataclass
class MockResourceContent:
    text: str


@dataclass
class MockReadResourceResult:
    contents: list = field(default_factory=list)


@dataclass
class MockPromptArgument:
    name: str
    description: str | None = None
    required: bool = False


@dataclass
class MockPrompt:
    name: str
    description: str | None = None
    arguments: list[MockPromptArgument] | None = None


@dataclass
class MockListPromptsResult:
    prompts: list[MockPrompt] = field(default_factory=list)


@dataclass
class MockPromptMessage:
    role: str
    content: str


@dataclass
class MockGetPromptResult:
    description: str | None = None
    messages: list[MockPromptMessage] = field(default_factory=list)


def _make_session(
    tools: list[MockMCPTool] | None = None,
    resources: list[MockResource] | None = None,
    resource_templates: list[MockResourceTemplate] | None = None,
    prompts: list[MockPrompt] | None = None,
    call_tool_result: MockCallToolResult | None = None,
    read_resource_result: MockReadResourceResult | None = None,
    get_prompt_result: MockGetPromptResult | None = None,
) -> AsyncMock:
    """Build a mock MCP ClientSession."""
    session = AsyncMock()
    session.list_tools.return_value = MockListToolsResult(tools=tools or [])
    session.list_resources.return_value = MockListResourcesResult(
        resources=resources or []
    )
    session.list_resource_templates.return_value = MockListResourceTemplatesResult(
        resourceTemplates=resource_templates or []
    )
    session.list_prompts.return_value = MockListPromptsResult(
        prompts=prompts or []
    )
    if call_tool_result:
        session.call_tool.return_value = call_tool_result
    if read_resource_result:
        session.read_resource.return_value = read_resource_result
    if get_prompt_result:
        session.get_prompt.return_value = get_prompt_result
    return session


# ── Helper import ────────────────────────────────────────────────────
# Import from mcp module — these will raise ImportError if mcp not installed,
# but our tests mock at a different level so we import the actual functions.

from ez_ptc.mcp import (
    _parse_uri_template,
    _sanitize_name,
    _synthesize_signature,
    get_mcp_prompt,
    list_mcp_prompts,
    tools_from_mcp,
)


# ═══════════════════════════════════════════════════════════════════════
# Test internal helpers
# ═══════════════════════════════════════════════════════════════════════


class TestSanitizeName:
    def test_simple_name(self):
        assert _sanitize_name("my_tool") == "my_tool"

    def test_dashes_and_spaces(self):
        assert _sanitize_name("my-tool name") == "my_tool_name"

    def test_leading_digit(self):
        assert _sanitize_name("3d_model") == "_3d_model"

    def test_special_chars(self):
        assert _sanitize_name("foo@bar.baz") == "foo_bar_baz"

    def test_multiple_underscores_collapsed(self):
        assert _sanitize_name("foo---bar") == "foo_bar"

    def test_empty_string(self):
        assert _sanitize_name("") == "unnamed"


class TestParseUriTemplate:
    def test_single_variable(self):
        assert _parse_uri_template("users/{id}") == ["id"]

    def test_multiple_variables(self):
        assert _parse_uri_template("repos/{owner}/{repo}/pulls") == ["owner", "repo"]

    def test_no_variables(self):
        assert _parse_uri_template("static/path") == []


class TestSynthesizeSignature:
    def test_no_schema(self):
        assert _synthesize_signature("foo", None) == "foo()"

    def test_empty_schema(self):
        assert _synthesize_signature("foo", {}) == "foo()"

    def test_required_params(self):
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query", "limit"],
        }
        sig = _synthesize_signature("search", schema)
        assert sig == "search(query: str, limit: int)"

    def test_optional_params(self):
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }
        sig = _synthesize_signature("search", schema)
        assert sig == "search(query: str, limit: int = 10)"

    def test_optional_without_default(self):
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "format": {"type": "string"},
            },
            "required": ["query"],
        }
        sig = _synthesize_signature("search", schema)
        assert sig == "search(query: str, format: str = None)"


# ═══════════════════════════════════════════════════════════════════════
# Test tool discovery
# ═══════════════════════════════════════════════════════════════════════


class TestToolsFromMcp:
    async def test_single_tool(self):
        mcp_tool = MockMCPTool(
            name="search",
            description="Search the web",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        session = _make_session(tools=[mcp_tool])
        tools = await tools_from_mcp(session, include_resources=False)

        assert len(tools) == 1
        t = tools[0]
        assert isinstance(t, Tool)
        assert t.name == "search"
        assert t.description == "Search the web"
        assert "query" in t.parameters["properties"]
        assert t.signature == "search(query: str)"

    async def test_multiple_tools(self):
        tools_list = [
            MockMCPTool(name="search", description="Search"),
            MockMCPTool(name="calculate", description="Calculate"),
        ]
        session = _make_session(tools=tools_list)
        tools = await tools_from_mcp(session, include_resources=False)
        assert len(tools) == 2
        assert {t.name for t in tools} == {"search", "calculate"}

    async def test_tool_names_filter(self):
        tools_list = [
            MockMCPTool(name="search", description="Search"),
            MockMCPTool(name="calculate", description="Calculate"),
            MockMCPTool(name="translate", description="Translate"),
        ]
        session = _make_session(tools=tools_list)
        tools = await tools_from_mcp(
            session, tool_names=["search", "translate"], include_resources=False
        )
        assert len(tools) == 2
        assert {t.name for t in tools} == {"search", "translate"}

    async def test_output_schema_as_return_schema(self):
        output_schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
        }
        mcp_tool = MockMCPTool(
            name="search",
            description="Search",
            inputSchema={"type": "object", "properties": {}},
            outputSchema=output_schema,
        )
        session = _make_session(tools=[mcp_tool])
        tools = await tools_from_mcp(session, include_resources=False)
        assert tools[0].return_schema == output_schema

    async def test_no_output_schema(self):
        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool])
        tools = await tools_from_mcp(session, include_resources=False)
        assert tools[0].return_schema is None

    async def test_fn_is_async(self):
        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool])
        tools = await tools_from_mcp(session, include_resources=False)
        assert asyncio.iscoroutinefunction(tools[0].fn)

    async def test_empty_description(self):
        mcp_tool = MockMCPTool(name="search", description=None)
        session = _make_session(tools=[mcp_tool])
        tools = await tools_from_mcp(session, include_resources=False)
        assert tools[0].description == ""


# ═══════════════════════════════════════════════════════════════════════
# Test return_schemas parameter
# ═══════════════════════════════════════════════════════════════════════


class TestReturnSchemas:
    async def test_return_schemas_applied(self):
        """User-provided return_schemas become tool.return_schema."""
        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool])
        user_schema = {
            "type": "object",
            "properties": {"results": {"type": "array"}, "total": {"type": "integer"}},
        }
        tools = await tools_from_mcp(
            session,
            include_resources=False,
            return_schemas={"search": user_schema},
        )
        assert tools[0].return_schema == user_schema

    async def test_return_schemas_priority_over_output_schema(self):
        """User return_schemas override MCP outputSchema."""
        output_schema = {"type": "object", "properties": {"old": {"type": "string"}}}
        user_schema = {"type": "object", "properties": {"new": {"type": "string"}}}
        mcp_tool = MockMCPTool(
            name="search",
            description="Search",
            outputSchema=output_schema,
        )
        session = _make_session(tools=[mcp_tool])
        tools = await tools_from_mcp(
            session,
            include_resources=False,
            return_schemas={"search": user_schema},
        )
        assert tools[0].return_schema == user_schema

    async def test_return_schemas_partial(self):
        """Only matching tools get schemas; unmatched tools fall back to outputSchema or None."""
        tool_with_output = MockMCPTool(
            name="search",
            description="Search",
            outputSchema={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        tool_without = MockMCPTool(name="echo", description="Echo")
        session = _make_session(tools=[tool_with_output, tool_without])
        user_schema = {"type": "object", "properties": {"items": {"type": "array"}}}
        tools = await tools_from_mcp(
            session,
            include_resources=False,
            return_schemas={"echo": user_schema},
        )
        by_name = {t.name: t for t in tools}
        # search: no user schema, falls back to outputSchema
        assert by_name["search"].return_schema == {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        # echo: user schema applied
        assert by_name["echo"].return_schema == user_schema

    async def test_return_schemas_for_resources(self):
        """return_schemas works on resource tool names (read_* prefix)."""
        resource = MockResource(
            name="config",
            uri="file:///config.json",
            description="App config",
        )
        session = _make_session(resources=[resource])
        user_schema = {
            "type": "object",
            "properties": {"version": {"type": "string"}, "debug": {"type": "boolean"}},
        }
        tools = await tools_from_mcp(
            session,
            return_schemas={"read_config": user_schema},
        )
        resource_tool = [t for t in tools if t.name == "read_config"][0]
        assert resource_tool.return_schema == user_schema

    async def test_return_schemas_for_resource_templates(self):
        """return_schemas works on resource template tool names."""
        template = MockResourceTemplate(
            name="user profile",
            uriTemplate="users/{user_id}/profile",
            description="Get user profile",
        )
        session = _make_session(resource_templates=[template])
        user_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "role": {"type": "string"}},
        }
        tools = await tools_from_mcp(
            session,
            return_schemas={"read_user_profile": user_schema},
        )
        template_tool = [t for t in tools if t.name == "read_user_profile"][0]
        assert template_tool.return_schema == user_schema

    async def test_toolkit_from_mcp_chaining_with_return_schemas(self):
        """Integration: return_schemas + assist_tool_chaining shows Returns hints in prompt."""
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(
            name="search",
            description="Search the web",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        session = _make_session(tools=[mcp_tool])
        user_schema = {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "total": {"type": "integer"},
            },
        }
        toolkit = await Toolkit.from_mcp(
            session,
            include_resources=False,
            return_schemas={"search": user_schema},
            assist_tool_chaining=True,
        )
        prompt = toolkit.prompt()
        assert "# Returns:" in prompt
        assert "results" in prompt
        assert "total" in prompt


# ═══════════════════════════════════════════════════════════════════════
# Test MCP tool execution
# ═══════════════════════════════════════════════════════════════════════


class TestMcpToolExecution:
    async def test_json_result(self):
        mcp_tool = MockMCPTool(
            name="search",
            description="Search",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        call_result = MockCallToolResult(
            content=[MockTextContent(text='{"results": [1, 2, 3]}')],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        result = await tools[0].fn(query="test")
        assert result == {"results": [1, 2, 3]}
        session.call_tool.assert_called_once_with(
            "search", arguments={"query": "test"}
        )

    async def test_plain_text_result(self):
        mcp_tool = MockMCPTool(name="echo", description="Echo")
        call_result = MockCallToolResult(
            content=[MockTextContent(text="hello world")],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        result = await tools[0].fn()
        assert result == "hello world"

    async def test_error_raises_runtime_error(self):
        mcp_tool = MockMCPTool(name="fail", description="Fail")
        call_result = MockCallToolResult(
            content=[MockTextContent(text="something went wrong")],
            isError=True,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        with pytest.raises(RuntimeError, match="MCP tool error"):
            await tools[0].fn()

    async def test_positional_arg_mapping(self):
        mcp_tool = MockMCPTool(
            name="add",
            description="Add two numbers",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )
        call_result = MockCallToolResult(
            content=[MockTextContent(text="3")],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        # Call with positional args
        await tools[0].fn(1, 2)
        session.call_tool.assert_called_once_with(
            "add", arguments={"a": 1, "b": 2}
        )

    async def test_mixed_positional_and_keyword_args(self):
        mcp_tool = MockMCPTool(
            name="search",
            description="Search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
        call_result = MockCallToolResult(
            content=[MockTextContent(text='"ok"')],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        await tools[0].fn("test query", limit=5)
        session.call_tool.assert_called_once_with(
            "search", arguments={"query": "test query", "limit": 5}
        )

    async def test_multiple_content_blocks(self):
        mcp_tool = MockMCPTool(name="multi", description="Multi")
        call_result = MockCallToolResult(
            content=[
                MockTextContent(text="first"),
                MockTextContent(text="second"),
            ],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        result = await tools[0].fn()
        assert result == ["first", "second"]

    async def test_image_content(self):
        mcp_tool = MockMCPTool(name="screenshot", description="Screenshot")
        call_result = MockCallToolResult(
            content=[MockImageContent(data="base64data")],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        tools = await tools_from_mcp(session, include_resources=False)

        result = await tools[0].fn()
        assert result == "base64data"


# ═══════════════════════════════════════════════════════════════════════
# Test resource wrapping
# ═══════════════════════════════════════════════════════════════════════


class TestResourceWrapping:
    async def test_static_resource_zero_arg(self):
        resource = MockResource(
            name="config",
            uri="file:///config.json",
            description="App config",
            mimeType="application/json",
        )
        read_result = MockReadResourceResult(
            contents=[MockResourceContent(text='{"key": "value"}')]
        )
        session = _make_session(
            resources=[resource], read_resource_result=read_result
        )
        tools = await tools_from_mcp(session)

        resource_tools = [t for t in tools if t.name.startswith("read_")]
        assert len(resource_tools) == 1
        t = resource_tools[0]
        assert t.name == "read_config"
        assert t.signature == "read_config()"
        assert "application/json" in t.description

        result = await t.fn()
        assert result == {"key": "value"}
        session.read_resource.assert_called_once_with("file:///config.json")

    async def test_resource_template_parameterized(self):
        template = MockResourceTemplate(
            name="user profile",
            uriTemplate="users/{user_id}/profile",
            description="Get user profile",
        )
        read_result = MockReadResourceResult(
            contents=[MockResourceContent(text='{"name": "Alice"}')]
        )
        session = _make_session(
            resource_templates=[template], read_resource_result=read_result
        )
        tools = await tools_from_mcp(session)

        template_tools = [t for t in tools if t.name.startswith("read_")]
        assert len(template_tools) == 1
        t = template_tools[0]
        assert t.name == "read_user_profile"
        assert "user_id" in t.parameters["properties"]
        assert t.signature == "read_user_profile(user_id: str)"

        result = await t.fn(user_id="42")
        assert result == {"name": "Alice"}
        session.read_resource.assert_called_once_with("users/42/profile")

    async def test_resource_template_positional_args(self):
        template = MockResourceTemplate(
            name="repo file",
            uriTemplate="repos/{owner}/{repo}/file",
            description="Get repo file",
        )
        read_result = MockReadResourceResult(
            contents=[MockResourceContent(text='"content"')]
        )
        session = _make_session(
            resource_templates=[template], read_resource_result=read_result
        )
        tools = await tools_from_mcp(session)

        t = [t for t in tools if t.name == "read_repo_file"][0]
        await t.fn("alice", "myrepo")
        session.read_resource.assert_called_once_with("repos/alice/myrepo/file")

    async def test_include_resources_false(self):
        resource = MockResource(name="config", uri="file:///config.json")
        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool], resources=[resource])
        tools = await tools_from_mcp(session, include_resources=False)

        assert len(tools) == 1
        assert tools[0].name == "search"

    async def test_resource_plain_text(self):
        resource = MockResource(
            name="readme",
            uri="file:///README.md",
            mimeType="text/plain",
        )
        read_result = MockReadResourceResult(
            contents=[MockResourceContent(text="Hello World")]
        )
        session = _make_session(
            resources=[resource], read_resource_result=read_result
        )
        tools = await tools_from_mcp(session)

        t = [t for t in tools if t.name == "read_readme"][0]
        result = await t.fn()
        assert result == "Hello World"

    async def test_tool_names_filter_on_resources(self):
        resource = MockResource(name="config", uri="file:///config.json")
        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool], resources=[resource])
        tools = await tools_from_mcp(session, tool_names=["read_config"])

        assert len(tools) == 1
        assert tools[0].name == "read_config"


# ═══════════════════════════════════════════════════════════════════════
# Test prompt utility
# ═══════════════════════════════════════════════════════════════════════


class TestPromptUtility:
    async def test_get_mcp_prompt(self):
        prompt_result = MockGetPromptResult(
            description="A helpful prompt",
            messages=[
                MockPromptMessage(role="user", content="You are a helpful assistant."),
                MockPromptMessage(role="user", content="Please help with: {topic}"),
            ],
        )
        session = _make_session(get_prompt_result=prompt_result)

        text = await get_mcp_prompt(session, "helper", arguments={"topic": "math"})
        assert "helpful assistant" in text
        assert "Please help with" in text
        session.get_prompt.assert_called_once_with(
            "helper", arguments={"topic": "math"}
        )

    async def test_get_mcp_prompt_no_args(self):
        prompt_result = MockGetPromptResult(
            messages=[MockPromptMessage(role="user", content="Hello")]
        )
        session = _make_session(get_prompt_result=prompt_result)

        text = await get_mcp_prompt(session, "greeting")
        assert text == "Hello"
        session.get_prompt.assert_called_once_with("greeting", arguments=None)

    async def test_list_mcp_prompts(self):
        prompts = [
            MockPrompt(
                name="helper",
                description="A helper prompt",
                arguments=[
                    MockPromptArgument(
                        name="topic", description="The topic", required=True
                    ),
                    MockPromptArgument(
                        name="style", description="Response style", required=False
                    ),
                ],
            ),
            MockPrompt(name="greeting", description="A greeting"),
        ]
        session = _make_session(prompts=prompts)

        result = await list_mcp_prompts(session)
        assert len(result) == 2
        assert result[0]["name"] == "helper"
        assert result[0]["description"] == "A helper prompt"
        assert len(result[0]["arguments"]) == 2
        assert result[0]["arguments"][0]["name"] == "topic"
        assert result[0]["arguments"][0]["required"] is True
        assert result[1]["name"] == "greeting"
        assert result[1]["arguments"] == []

    async def test_list_mcp_prompts_no_arguments(self):
        prompts = [MockPrompt(name="simple", description="Simple", arguments=None)]
        session = _make_session(prompts=prompts)

        result = await list_mcp_prompts(session)
        assert result[0]["arguments"] == []


# ═══════════════════════════════════════════════════════════════════════
# Test Toolkit integration
# ═══════════════════════════════════════════════════════════════════════


class TestMcpToolkitIntegration:
    async def test_toolkit_from_mcp(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(
            name="search",
            description="Search the web",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        session = _make_session(tools=[mcp_tool])
        toolkit = await Toolkit.from_mcp(session, include_resources=False)

        assert len(toolkit) == 1
        assert toolkit.tools[0].name == "search"

    async def test_toolkit_from_mcp_prompt_includes_tools(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(
            name="search",
            description="Search the web",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        session = _make_session(tools=[mcp_tool])
        toolkit = await Toolkit.from_mcp(session, include_resources=False)

        prompt = toolkit.prompt()
        assert "search" in prompt
        assert "Search the web" in prompt

    async def test_toolkit_from_mcp_with_extra_tools(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool])

        local_tool = Tool(
            name="calculate",
            description="Calculate",
            parameters={"type": "object", "properties": {}},
            fn=lambda x: x,
            signature="calculate(x: int)",
        )
        toolkit = await Toolkit.from_mcp(
            session,
            include_resources=False,
            extra_tools=[local_tool],
        )

        assert len(toolkit) == 2
        names = {t.name for t in toolkit.tools}
        assert names == {"search", "calculate"}

    async def test_toolkit_from_mcp_kwargs_passthrough(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool])

        toolkit = await Toolkit.from_mcp(
            session,
            include_resources=False,
            assist_tool_chaining=True,
            timeout=60.0,
        )
        assert toolkit._assist_tool_chaining is True
        assert toolkit._timeout == 60.0

    async def test_toolkit_from_mcp_with_resources(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(name="search", description="Search")
        resource = MockResource(
            name="config", uri="file:///config.json", description="Config"
        )
        session = _make_session(tools=[mcp_tool], resources=[resource])

        toolkit = await Toolkit.from_mcp(session)
        assert len(toolkit) == 2
        names = {t.name for t in toolkit.tools}
        assert "search" in names
        assert "read_config" in names

    async def test_toolkit_from_mcp_execute(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(
            name="greet",
            description="Greet someone",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        call_result = MockCallToolResult(
            content=[MockTextContent(text='"Hello, Alice!"')],
            isError=False,
        )
        session = _make_session(tools=[mcp_tool], call_tool_result=call_result)
        toolkit = await Toolkit.from_mcp(session, include_resources=False)

        result = await toolkit.execute('result = greet(name="Alice")\nprint(result)')
        assert result.success
        assert "Hello, Alice!" in result.output

    def test_toolkit_from_mcp_sync(self):
        from ez_ptc.toolkit import Toolkit

        mcp_tool = MockMCPTool(name="search", description="Search")
        session = _make_session(tools=[mcp_tool])

        toolkit = Toolkit.from_mcp_sync(session, include_resources=False)
        assert len(toolkit) == 1
        assert toolkit.tools[0].name == "search"
