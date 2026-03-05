"""Pluggable sandbox backend for code execution."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .executor import ExecutionResult, ToolCallRecord
    from .tool import Tool


@runtime_checkable
class SandboxBackend(Protocol):
    """Protocol for sandbox backends.

    Any class with an ``async execute(code, tools, timeout)`` method satisfies this.
    """

    async def execute(
        self,
        code: str,
        tools: dict[str, Tool],
        timeout: float,
        on_tool_call: Callable[[ToolCallRecord], None] | None = None,
    ) -> ExecutionResult: ...


class LocalSandbox:
    """Default sandbox using the built-in restricted exec() engine."""

    async def execute(
        self,
        code: str,
        tools: dict[str, Tool],
        timeout: float,
        on_tool_call: Callable[[ToolCallRecord], None] | None = None,
    ) -> ExecutionResult:
        from .executor import execute_code

        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(
            execute_code, code, tools, timeout, loop, False, on_tool_call
        )
