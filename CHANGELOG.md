# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.3] - 2026-02-28

### Added

- When `assist_tool_chaining=False`, all prompt surfaces now include a caution telling the LLM not to assume return value structure or key names — prevents hallucinated key access on tool outputs

## [0.1.2] - 2026-02-28

### Fixed

- Chaining language no longer appears in prompts when `assist_tool_chaining=False` — all four prompt surfaces (`prompt()`, `tool_prompt()`, `as_tool()`, `tool_schema()`) now correctly show neutral "print all results" language when chaining is disabled
- `asyncio.run()` in LLM-generated code now works when the executor is called from within a running event loop (e.g., Pydantic AI, FastAPI) — executor detects the loop and falls back to thread-based execution

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
