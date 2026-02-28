# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

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
