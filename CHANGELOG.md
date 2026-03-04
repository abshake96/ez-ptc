# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.3.0] - 2026-03-03

### Added

- **Native async tool support**: Async tools (`async def`) are automatically detected via `Tool.is_async`. When any tool is async, LLM code runs in an async context — `await` works natively, no more `asyncio.to_thread` gymnastics. Prompts show `async def` prefix for async tools and guide the LLM to use `await`/`asyncio.gather` patterns.
- **Error enrichment**: On `KeyError`, error output now shows available dict keys in scope. On `AttributeError` against a dict, hints to use `['key']` bracket syntax. Only enriches errors from LLM code, not tool internals. Enables LLM self-correction in 1 retry instead of 3+.
- **`allow_await` validator param**: `validate_code()` accepts `allow_await=True` to permit `await` syntax in pre-flight AST validation (used automatically when toolkit has async tools).

### Changed

- All four prompt surfaces (`prompt()`, `tool_prompt()`, `as_tool()`, `tool_schema()`) now prefix async tools with `async def`/`async ` and show simplified await-based patterns instead of `asyncio.to_thread` when async tools are present
- `execute_code()` accepts `has_async_tools` param — when True, wraps LLM code in `async def` and runs with `asyncio.run()`
- `LocalSandbox.execute()` auto-detects async tools and passes `has_async_tools` to executor
- MCP tools, resources, and resource templates are now created with `is_async=True` (they were always async internally)

## [0.2.2] - 2026-03-02

### Added

- **Error hint system**: `Toolkit(error_hint=...)` customizes error recovery guidance in all prompt surfaces and tool responses; default hint tells the LLM to analyze tracebacks and retry; set to `""` to disable
- **Empty-output safety net**: `as_tool()` / `as_tool_sync()` detect when tools were called without `print()` (non-chaining mode only) and return a corrective message instead of empty string
- **Non-chaining prompt overhaul**: Replaced vague "don't assume key names" text with explicit "do NOT access, index, or filter return values" + `print(tool_a(...))` pattern across all four prompt surfaces — directly prevents LLMs from guessing return schemas
- **Asyncio prompt fix**: Added sync wrapper pattern for grouping multiple tool calls + explicit warning that `asyncio.to_thread` only works with sync functions — prevents LLMs from passing `async def` to `to_thread` (which silently returns coroutine objects)

## [0.2.1] - 2026-03-02

### Fixed

- **Security**: Remove `io` from safe modules (prevented filesystem bypass via `io.open()`)
- **Security**: Block unauthorized urllib submodule imports (e.g. `from urllib import request`)
- **Security**: Use `inspect.isawaitable` instead of `asyncio.iscoroutine` for broader awaitable coverage
- **Security**: Use `math.ceil` for `signal.alarm` timeout to prevent premature truncation
- Detect duplicate tool names in `Toolkit` constructor (raises `ValueError`)
- Fix `_body_has_exit` validator to properly recurse into compound statements (`if`/`for`/`while`)
- Fix variable shadowing in MCP tool wrapper
- Fix `read_file` → `read_text_file` in MCP chaining example
- Fix async-shown-as-sync across all documentation (`execute()` → `execute_sync()`, `as_tool()` → `as_tool_sync()` in sync contexts)
- Fix 7 broken example file paths in `docs/examples.md`
- Add missing v0.2.0 APIs to `docs/api-reference.md` (`SandboxBackend`, `LocalSandbox`, `validate_code`, `ValidationResult`, `timeout`/`sandbox` params, `return_schemas`)
- Add AST validation section to `docs/security.md`
- Document `ez-ptc[pydantic]` optional dependency

## [0.2.0] - 2026-03-02

### Added

- **Async-first execution**: `Toolkit.execute()` and `SandboxBackend.execute()` are now async; sync convenience methods `execute_sync()` and `as_tool_sync()` provided for non-async contexts
- **Pluggable sandbox backend**: New `SandboxBackend` abstract base class and `LocalSandbox` implementation — pass custom sandboxes via `Toolkit(sandbox=...)`
- **AST code validator**: `validate_code()` pre-flight checks for dangerous patterns (imports, file I/O, system calls) before execution; `ValidationResult` dataclass for structured results
- **MCP Tool Bridge**: `Toolkit.from_mcp(session)` wraps MCP server tools/resources as ez-ptc `Tool` objects; `get_mcp_prompt()` / `list_mcp_prompts()` for prompt templates; lazy import keeps core zero-dependency; optional extra: `ez-ptc[mcp]`
- **Toolkit-level timeout**: `Toolkit(timeout=30.0)` sets default execution timeout
- **Per-framework MCP live examples**: `example_mcp_openai.py`, `example_mcp_anthropic.py`, `example_mcp_langchain.py`, `example_mcp_pydantic_ai.py`, `example_mcp_litellm.py`, `example_mcp_google_genai.py` — each runs a real agentic loop against a live MCP filesystem server
- **Final LLM response display**: All MCP live examples now print a `--- Final Response ---` section and handle loop exhaustion gracefully
- Custom `preamble` / `postamble` support in `Toolkit` constructor
- `examples/README.md` with full directory structure and run instructions
- Reorganized examples into `basics/`, `frameworks/`, `prompt_mode/`, `advanced/`, `mcp_live/`
- Advanced examples: custom sandbox, error handling, async tools, Pydantic models, advanced schemas, validation, MCP bridge (mock)
- Multi-turn error recovery example (`prompt_mode/example_error_recovery.py`)
- Expanded documentation: MCP bridge guide, updated API reference, concepts, getting started

### Changed

- `_run_sync()` helper in toolkit.py detects running event loops and falls back to thread-based execution
- `execute_code()` in executor.py stays sync — `LocalSandbox.execute()` wraps it with `asyncio.to_thread`
- Existing framework examples updated with `as_tool_sync()` for sync contexts

## [0.1.4] - 2026-03-01

### Added

- All prompt surfaces now explicitly tell the LLM that tools are pre-loaded globals and must NOT be imported — prevents `import search_cars` failures
- Refined no-chaining usage hints to reinforce single code block usage

## [0.1.3] - 2026-02-28

### Added

- When `assist_tool_chaining=False`, all prompt surfaces now include a caution telling the LLM not to assume return value structure or key names — prevents hallucinated key access on tool outputs

## [0.1.2] - 2026-02-28

### Fixed

- Chaining language no longer appears in prompts when `assist_tool_chaining=False` — all four prompt surfaces (`prompt()`, `tool_prompt()`, `as_tool()`, `tool_schema()`) now correctly show neutral "print all results" language when chaining is disabled
- `asyncio.run()` in LLM-generated code now works when the executor is called from within a running event loop (e.g., Pydantic AI, FastAPI) — executor detects the loop and falls back to thread-based execution

## [0.1.1] - 2026-02-28

### Added

- Anthropic attribution in README and documentation
- Tool chaining documentation and improved README examples

## [0.1.0] - 2026-02-28

### Added

- Core `@ez_tool` decorator for wrapping Python functions as tools
- `Toolkit` class with two modes: prompt mode and tool mode
- Sandboxed code execution engine with configurable timeouts
- Safe import system allowing curated stdlib modules
- `assist_tool_chaining` for documenting return types to LLMs
- Support for TypedDict and Pydantic BaseModel return schemas
- Framework examples: OpenAI, Anthropic, LangChain, Pydantic AI, LiteLLM, Google GenAI
- Async tool support with `asyncio.gather` parallel execution
- Single-call consolidation instructions across all prompt surfaces
