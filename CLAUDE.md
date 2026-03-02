# ez-ptc Development Guide

## Architecture
- `src/ez_ptc/` — zero-dependency library: tool.py (@ez_tool), toolkit.py (Toolkit), executor.py (sandbox), schema.py (type introspection)
- Four prompt surfaces must stay in sync: `prompt()`, `tool_prompt()`, `as_tool()`, `tool_schema()` — any behavioral change needs all four updated
- `assist_tool_chaining` flag gates chaining-specific language — always test both True and False paths
- **Async-first**: `Toolkit.execute()` and `SandboxBackend.execute()` are async. Sync convenience: `execute_sync()`, `as_tool_sync()`
- `_run_sync()` helper in toolkit.py handles running async in sync contexts (detects running event loops)
- `execute_code()` in executor.py stays sync — `LocalSandbox.execute()` uses `asyncio.to_thread` to run it, passing the event loop for efficient async tool dispatch
- **MCP Tool Bridge**: `mcp.py` wraps MCP server tools/resources as ez-ptc `Tool` objects. `Toolkit.from_mcp(session)` for one-liner setup. `get_mcp_prompt()` / `list_mcp_prompts()` for prompt templates. Lazy import keeps core zero-dep. Optional extra: `ez-ptc[mcp]`

## Testing
- `uv run pytest tests/ -v` — 194+ tests, runs in ~10s
- When changing prompt text, add assertions for both presence (when enabled) AND absence (when disabled)
- Executor tests: `test_executor.py`, Toolkit/prompt tests: `test_toolkit.py`, Schema tests: `test_schema.py`, Sandbox tests: `test_sandbox.py`, Validator tests: `test_validator.py`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"` in pyproject.toml

## Release Workflow
- Bump version in `pyproject.toml` → update `CHANGELOG.md` → commit → `git push origin main` (needs SSH passphrase, user does manually) → `uv build` → `uv publish dist/ez_ptc-{version}*`
- SSH push always fails in CLI — just build the wheel and tell the user to push + publish

## Common LLM Failure Modes (inform prompt engineering)
- LLMs try to `import` tools that are pre-loaded globals — all surfaces must say "do NOT import"
- LLMs assume return value keys without schema — when chaining is off, surfaces must caution against key access
- LLMs make multiple separate tool calls instead of one code block — all surfaces must say "SINGLE" + "do NOT"
- `asyncio.run()` fails inside running event loops (Pydantic AI, FastAPI) — executor detects and uses thread fallback
