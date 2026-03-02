# ez-ptc Examples

## Directory Structure

```
examples/
    shared_tools.py              # Shared tool definitions for framework examples

    basics/                      # No API keys needed
        example_demo.py          # Both modes + validation + timeout
        example_custom_prompts.py # Custom preamble/postamble

    frameworks/                  # Require OPENAI_API_KEY (or provider-specific key)
        example_openai.py        # OpenAI SDK
        example_anthropic.py     # Anthropic SDK
        example_litellm.py       # LiteLLM (any provider)
        example_langchain.py     # LangChain
        example_pydantic_ai.py   # Pydantic AI
        example_google_genai.py  # Google GenAI

    prompt_mode/                 # Require OPENAI_API_KEY
        example_prompt_mode.py   # Basic prompt mode flow
        example_error_recovery.py # Multi-turn error recovery

    advanced/                    # No API keys needed (mock-based; for real LLM + MCP see mcp_live/)
        example_mcp_bridge.py    # MCP Tool Bridge — wrap MCP server tools (mock)
        example_validation.py    # AST pre-flight code validation
        example_custom_sandbox.py # Pluggable sandbox backends
        example_error_handling.py # Errors, timeouts, recovery patterns
        example_async_tools.py   # Async tool definitions
        example_pydantic_models.py # Pydantic return types for chaining
        example_advanced_schemas.py # Explicit schemas, introspection, Literal/Optional

    mcp_live/                    # Require API key + Node.js/npx + ez-ptc[mcp]
        _mcp_session.py              # Shared: MCP session setup helper
        example_mcp_prompt_mode.py   # Prompt mode with real filesystem MCP server
        example_mcp_chaining.py      # return_schemas + assist_tool_chaining comparison
        example_mcp_openai.py        # Tool mode — OpenAI
        example_mcp_anthropic.py     # Tool mode — Anthropic
        example_mcp_langchain.py     # Tool mode — LangChain
        example_mcp_pydantic_ai.py   # Tool mode — Pydantic AI
        example_mcp_litellm.py       # Tool mode — LiteLLM
        example_mcp_google_genai.py  # Tool mode — Google GenAI
```

## Quick Start

### No API keys needed

```bash
# Core demo — prompt mode, tool mode, validation, timeout
uv run python examples/basics/example_demo.py

# All advanced examples run without API keys
uv run python examples/advanced/example_mcp_bridge.py
uv run python examples/advanced/example_validation.py
uv run python examples/advanced/example_custom_sandbox.py
uv run python examples/advanced/example_error_handling.py
uv run python examples/advanced/example_async_tools.py
uv run python examples/advanced/example_pydantic_models.py
uv run python examples/advanced/example_advanced_schemas.py
uv run python examples/basics/example_custom_prompts.py
```

### With OpenAI API key

```bash
# Set your key
export OPENAI_API_KEY=sk-...
# Or put it in .env at the repo root

# Framework integrations
uv run python examples/frameworks/example_openai.py
uv run python examples/frameworks/example_litellm.py
uv run python examples/frameworks/example_langchain.py
uv run python examples/frameworks/example_pydantic_ai.py

# Prompt mode
uv run python examples/prompt_mode/example_prompt_mode.py
uv run python examples/prompt_mode/example_error_recovery.py
```

### With OpenAI API key + Node.js (real MCP server)

```bash
# These connect to a real @modelcontextprotocol/server-filesystem via npx
uv run python examples/mcp_live/example_mcp_prompt_mode.py
uv run python examples/mcp_live/example_mcp_chaining.py
uv run python examples/mcp_live/example_mcp_openai.py
uv run python examples/mcp_live/example_mcp_langchain.py
uv run python examples/mcp_live/example_mcp_pydantic_ai.py
uv run python examples/mcp_live/example_mcp_litellm.py
```

### With Anthropic API key + Node.js (real MCP server)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run python examples/frameworks/example_anthropic.py
uv run python examples/mcp_live/example_mcp_anthropic.py
```

### With Google API key + Node.js (real MCP server)

```bash
export GOOGLE_API_KEY=...
uv run python examples/frameworks/example_google_genai.py
uv run python examples/mcp_live/example_mcp_google_genai.py
```

## What Each Example Covers

| Feature | Example |
|---------|---------|
| `@ez_tool` decorator | `basics/example_demo.py` |
| `Toolkit.prompt()` (prompt mode) | `basics/example_demo.py`, `prompt_mode/` |
| `Toolkit.as_tool()` / `as_tool_sync()` (tool mode) | `basics/example_demo.py`, `frameworks/` |
| `Toolkit.execute()` / `execute_sync()` | `basics/example_demo.py`, `advanced/example_error_handling.py` |
| `validate_code()` / `ValidationResult` | `advanced/example_validation.py` |
| `SandboxBackend` / custom sandbox | `advanced/example_custom_sandbox.py` |
| Toolkit-level `timeout` | `basics/example_demo.py`, `advanced/example_error_handling.py` |
| `execute_sync(validate=False)` | `advanced/example_validation.py` |
| Error handling / `ExecutionResult` | `advanced/example_error_handling.py` |
| Async tools | `advanced/example_async_tools.py` |
| Pydantic return types | `advanced/example_pydantic_models.py` |
| `@ez_tool(return_schema={...})` | `advanced/example_advanced_schemas.py` |
| `function_to_schema()` | `advanced/example_advanced_schemas.py` |
| `Literal` / `Optional` types | `advanced/example_advanced_schemas.py` |
| Tool introspection | `advanced/example_advanced_schemas.py` |
| Custom `preamble` / `postamble` | `basics/example_custom_prompts.py` |
| `Toolkit.from_mcp()` | `advanced/example_mcp_bridge.py` |
| `tools_from_mcp()` / filtering | `advanced/example_mcp_bridge.py` |
| `get_mcp_prompt()` / `list_mcp_prompts()` | `advanced/example_mcp_bridge.py` |
| MCP resource wrapping | `advanced/example_mcp_bridge.py` |
| Mixing MCP + local tools | `advanced/example_mcp_bridge.py` |
| `assist_tool_chaining` | `frameworks/` (all), `advanced/example_pydantic_models.py` |
| `Toolkit.from_mcp()` with real server | `mcp_live/example_mcp_prompt_mode.py` |
| Real MCP tool discovery + prompt mode | `mcp_live/example_mcp_prompt_mode.py` |
| Real MCP tool mode agentic loop | `mcp_live/example_mcp_openai.py` |
| `return_schemas` for MCP tool chaining | `mcp_live/example_mcp_chaining.py` |
| `tool_names` filter with real server | `mcp_live/example_mcp_chaining.py` |
| MCP + OpenAI integration | `mcp_live/example_mcp_openai.py` |
| MCP + Anthropic integration | `mcp_live/example_mcp_anthropic.py` |
| MCP + LangChain integration | `mcp_live/example_mcp_langchain.py` |
| MCP + Pydantic AI integration | `mcp_live/example_mcp_pydantic_ai.py` |
| MCP + LiteLLM integration | `mcp_live/example_mcp_litellm.py` |
| MCP + Google GenAI integration | `mcp_live/example_mcp_google_genai.py` |
| Multi-turn error recovery | `prompt_mode/example_error_recovery.py` |
| OpenAI integration | `frameworks/example_openai.py` |
| Anthropic integration | `frameworks/example_anthropic.py` |
| LangChain integration | `frameworks/example_langchain.py` |
| Pydantic AI integration | `frameworks/example_pydantic_ai.py` |
| LiteLLM integration | `frameworks/example_litellm.py` |
| Google GenAI integration | `frameworks/example_google_genai.py` |
