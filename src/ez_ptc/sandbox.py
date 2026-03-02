"""Pluggable sandbox backend for code execution."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .executor import ExecutionResult
    from .tool import Tool


@runtime_checkable
class SandboxBackend(Protocol):
    """Protocol for sandbox backends.

    Any class with an ``async execute(code, tools, timeout)`` method satisfies this.
    """

    async def execute(
        self, code: str, tools: dict[str, Tool], timeout: float
    ) -> ExecutionResult: ...


class LocalSandbox:
    """Default sandbox using the built-in restricted exec() engine."""

    async def execute(
        self, code: str, tools: dict[str, Tool], timeout: float
    ) -> ExecutionResult:
        from .executor import execute_code

        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(execute_code, code, tools, timeout, loop)
