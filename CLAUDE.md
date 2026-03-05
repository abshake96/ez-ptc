# ez-ptc Development Guide

## Quick Start
- `uv sync` — install all dependencies
- `uv run pytest tests/ -v` — run tests
- `uv run python examples/basics/example_demo.py` — smoke test

## Architecture
- `src/ez_ptc/` — zero-dependency library: tool.py (@ez_tool), toolkit.py (Toolkit), executor.py (sandbox), schema.py (type introspection), validator.py (AST validation)
- Four prompt surfaces must stay in sync: `prompt()`, `tool_prompt()`, `as_tool()`, `tool_schema()` — any behavioral change needs all four updated
- `assist_tool_chaining` flag gates chaining-specific language — always test both True and False paths
- **Async-first**: `Toolkit.execute()` and `SandboxBackend.execute()` are async. Sync convenience: `execute_sync()`, `as_tool_sync()`
- `_run_sync()` helper in toolkit.py handles running async in sync contexts (detects running event loops)
- `execute_code()` in executor.py stays sync — `LocalSandbox.execute()` uses `asyncio.to_thread` to run it, passing the event loop for efficient async tool dispatch
- **`parallel()` helper**: Built-in concurrency primitive injected into every sandbox execution. `_make_parallel_helper()` in executor.py. `parallel((tool, arg1), (tool2, arg1, arg2))` runs via `ThreadPoolExecutor`, returns results in order. Batch pattern: `results = parallel(*[(tool, id) for id in ids])`. All four prompt surfaces advertise it.
- **Async tools handled transparently**: `Tool.is_async` auto-detected via `inspect.iscoroutinefunction()`. All tools wrapped as sync via `_make_tool_wrapper()` — async tools dispatched with `asyncio.run_coroutine_threadsafe()`. `has_async_tools` param in `execute_code()` is deprecated/ignored.
- **Error enrichment**: `_enrich_error()` in executor.py appends available dict keys on `KeyError` and hints bracket syntax on `AttributeError`. Only enriches errors from LLM code (checks `co_filename` against both `"<string>"` and `"<llm_code>"`).
- **MCP Tool Bridge**: `mcp.py` wraps MCP server tools/resources as ez-ptc `Tool` objects (`is_async=True`). `Toolkit.from_mcp(session)` / `Toolkit.from_mcp_sync(session)` for one-liner setup. `get_mcp_prompt()` / `list_mcp_prompts()` for prompt templates. MCP `outputSchema` auto-used as `return_schema`; `return_schemas` kwarg overrides. `descriptions` kwarg overrides MCP tool descriptions per tool. Lazy import keeps core zero-dep. Optional extra: `ez-ptc[mcp]`
- **MCP naming conventions**: Tools keep their MCP name. Static resources get `read_` prefix. Resource templates get `query_` prefix. Name deduplication appends `_2`, `_3`, etc. on collision across all three categories.
- **Toolkit utilities**: `Toolkit.__iter__` and `Toolkit.__len__` allow iteration/counting of tools. `execute()`/`execute_sync()` accept `validate: bool = True` to control AST validation.
- **Optional extras**: `ez-ptc[mcp]` (requires `mcp>=1.0`), `ez-ptc[pydantic]` (requires `pydantic>=2.0`)

### Observability & Hooks
- **`on_tool_call` callback**: `Toolkit(tools, on_tool_call=fn)` — called with `ToolCallRecord` after each tool invocation (includes timing via `duration_ms`). Passed through to `execute_code()` and streaming execution.
- **`ToolCallRecord` dataclass**: Replaces raw dicts for tool call logging. Fields: `name`, `args`, `kwargs`, `result`, `duration_ms`. All tool calls timed via `time.perf_counter()` in `_make_tool_wrapper()`.

### Dynamic Tool Filtering
- **`Toolkit.filter(*names)`**: Returns a new `Toolkit` with only the named tools. Preserves all settings (timeout, chaining, on_tool_call, sandbox).
- **`Toolkit.get_tool(name)`**: Returns a single `Tool` by name, raises `KeyError` if not found.

### Auto-Retry with Error Feedback
- `execute(code, max_retries=N, retry_handler=async_fn)` / `execute_sync(..., retry_handler=sync_fn)` — on failure, calls `retry_handler(failed_code, error_msg)` which returns new code to try. Tool calls accumulate across attempts. `result.attempts` tracks total attempts (1 = first try only).
- Validation failures are retryable. `retry_handler` is required when `max_retries > 0`.

### Human-in-the-Loop Approval
- `Tool(requires_approval=True)` or `@ez_tool(requires_approval=True)` — marks tools needing user approval before execution.
- `execute(code, approved_calls=["tool_name"])` — pre-approve specific tools. Unapproved tools cause `result.is_paused == True` with `result.pending_tool_calls` listing what needs approval.
- `_find_called_tool_names()` uses AST-based scanning to detect which tools are called in code.
- `PendingToolCall` dataclass: `tool_name: str`.
- `ExecutionResult.is_paused` is a derived `@property` (not a stored field) — `bool(self.pending_tool_calls)`.

### Streaming Execution
- `execute_streaming(code)` (async) / `execute_streaming_sync(code)` (sync) — yield `ExecutionEvent` objects in real-time.
- Event types: `Literal["output", "tool_call", "error", "done"]`. Final event is always `"done"` with `ExecutionResult` as data.
- Implementation: shared `_start_streaming_execution()` helper starts a daemon thread running `execute_code()` with a `queue.Queue` for events. `_finalize_streaming_result()` builds the done event.
- Streaming calls `execute_code()` directly (not through sandbox abstraction) but passes `on_tool_call`.
- `_QueueWriter` in executor.py captures stdout/stderr and puts `ExecutionEvent`s on the queue.

### Multi-Model Schema Formats
- `tool_schema(format="openai"|"anthropic"|"gemini"|"mistral"|"raw")` — generates tool schemas in provider-specific formats. Default is `"openai"`.

## Key Exports (`__init__.py`)
- `ez_tool`, `Tool`, `Toolkit`, `ExecutionResult`
- `ExecutionEvent`, `ToolCallRecord`, `PendingToolCall`
- `function_to_schema`, `validate_code`, `ValidationResult`
- `SandboxBackend`, `LocalSandbox`

## Testing
- `uv run pytest tests/ -v` — ~399 tests, runs in ~30s
- When changing prompt text, add assertions for both presence (when enabled) AND absence (when disabled)
- Test files: `test_executor.py`, `test_toolkit.py`, `test_schema.py`, `test_sandbox.py`, `test_validator.py`, `test_mcp.py`, `test_tool.py`, `test_approval.py`, `test_retry.py`, `test_streaming.py`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"` in pyproject.toml

## Internal Helpers
- `_validation_error_result(errors, **kwargs)` in toolkit.py — builds `ExecutionResult` for validation failures (used in execute, streaming async, streaming sync)
- `_find_called_tool_names(code, tool_names)` in toolkit.py — AST-based detection of tool calls in code
- `_tool_name_set` and `_tools_needing_approval` cached at `Toolkit.__init__` for performance

## Release Workflow
- Bump version in `pyproject.toml` → update `CHANGELOG.md` → commit → `git push origin main` (needs SSH passphrase, user does manually) → `uv build` → `uv publish dist/ez_ptc-{version}*`
- `git push origin main` or `gh` CLI usually works; SSH passphrase may block in some sessions — fall back to telling user to push manually if needed
- PyPI publish needs `UV_PUBLISH_TOKEN` — use `source ~/.zshrc 2>/dev/null` before publishing. NEVER grep/export the token directly.

## Common LLM Failure Modes (inform prompt engineering)
- LLMs try to `import` tools that are pre-loaded globals — all surfaces must say "do NOT import"
- LLMs assume return value keys without schema — non-chaining surfaces say "do NOT access, index, or filter return values"
- LLMs make multiple separate tool calls instead of one code block — all surfaces must say "SINGLE" + "do NOT"
- `asyncio.run()` fails inside running event loops (Pydantic AI, FastAPI) — executor detects and uses thread fallback
- LLMs call tools inside `parallel()` instead of passing as tuples — `parallel()` helper validates and gives specific error message
- Non-chaining mode fundamentally fails on multi-step filtering tasks — LLMs ignore "do NOT access" when task requires chaining
