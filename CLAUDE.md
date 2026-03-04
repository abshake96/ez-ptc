# ez-ptc Development Guide

## Architecture
- `src/ez_ptc/` — zero-dependency library: tool.py (@ez_tool), toolkit.py (Toolkit), executor.py (sandbox), schema.py (type introspection)
- Four prompt surfaces must stay in sync: `prompt()`, `tool_prompt()`, `as_tool()`, `tool_schema()` — any behavioral change needs all four updated
- `assist_tool_chaining` flag gates chaining-specific language — always test both True and False paths
- **Async-first**: `Toolkit.execute()` and `SandboxBackend.execute()` are async. Sync convenience: `execute_sync()`, `as_tool_sync()`
- `_run_sync()` helper in toolkit.py handles running async in sync contexts (detects running event loops)
- `execute_code()` in executor.py stays sync — `LocalSandbox.execute()` uses `asyncio.to_thread` to run it, passing the event loop for efficient async tool dispatch
- **Native async tools**: `Tool.is_async` field auto-detected via `inspect.iscoroutinefunction()`. When any tool is async, executor wraps LLM code in `async def` so `await` works natively. `_make_async_tool_wrapper()` creates proper async wrappers. Prompt surfaces show `async def` prefix.
- **Error enrichment**: `_enrich_error()` in executor.py appends available dict keys on `KeyError` and hints bracket syntax on `AttributeError`. Only enriches errors from LLM code (checks `co_filename`).
- **MCP Tool Bridge**: `mcp.py` wraps MCP server tools/resources as ez-ptc `Tool` objects (`is_async=True`). `Toolkit.from_mcp(session)` for one-liner setup. `get_mcp_prompt()` / `list_mcp_prompts()` for prompt templates. Lazy import keeps core zero-dep. Optional extra: `ez-ptc[mcp]`

## Testing
- `uv run pytest tests/ -v` — 300 tests, runs in ~23s
- When changing prompt text, add assertions for both presence (when enabled) AND absence (when disabled)
- Executor tests: `test_executor.py`, Toolkit/prompt tests: `test_toolkit.py`, Schema tests: `test_schema.py`, Sandbox tests: `test_sandbox.py`, Validator tests: `test_validator.py`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"` in pyproject.toml

## Release Workflow
- Bump version in `pyproject.toml` → update `CHANGELOG.md` → commit → `git push origin main` (needs SSH passphrase, user does manually) → `uv build` → `uv publish dist/ez_ptc-{version}*`
- `git push origin main` or `gh` CLI usually works; SSH passphrase may block in some sessions — fall back to telling user to push manually if needed
- PyPI publish needs `UV_PUBLISH_TOKEN` — it's in `~/.zshrc` but `source ~/.zshrc` may silently fail; grep and export directly

## Common LLM Failure Modes (inform prompt engineering)
- LLMs try to `import` tools that are pre-loaded globals — all surfaces must say "do NOT import"
- LLMs assume return value keys without schema — non-chaining surfaces say "do NOT access, index, or filter return values"
- LLMs make multiple separate tool calls instead of one code block — all surfaces must say "SINGLE" + "do NOT"
- `asyncio.run()` fails inside running event loops (Pydantic AI, FastAPI) — executor detects and uses thread fallback
- LLMs pass `async def` to `asyncio.to_thread` (silently returns coroutine objects) — prompt warns against this
- Non-chaining mode fundamentally fails on multi-step filtering tasks — LLMs ignore "do NOT access" when task requires chaining
