"""Tests for sandbox.py — pluggable sandbox backend."""

import pytest

from ez_ptc import Toolkit, ez_tool
from ez_ptc.executor import ExecutionResult
from ez_ptc.sandbox import LocalSandbox, SandboxBackend


@ez_tool
def greet(name: str) -> str:
    """Say hello.

    Args:
        name: Who to greet
    """
    return f"Hello, {name}!"


# ── LocalSandbox tests ────────────────────────────────────────────────


class TestLocalSandbox:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        sandbox = LocalSandbox()
        result = await sandbox.execute('print("hi")', {}, timeout=5.0)
        assert result.success
        assert "hi" in result.output

    @pytest.mark.asyncio
    async def test_with_tools(self):
        sandbox = LocalSandbox()
        result = await sandbox.execute(
            'print(greet("World"))', {"greet": greet}, timeout=5.0
        )
        assert result.success
        assert "Hello, World!" in result.output


# ── Custom backend tests ──────────────────────────────────────────────


class _MockSandbox:
    """Custom sandbox that records calls and returns a fixed result."""

    def __init__(self):
        self.calls = []

    async def execute(self, code, tools, timeout):
        self.calls.append({"code": code, "tools": tools, "timeout": timeout})
        return ExecutionResult(success=True, output="mock output")


class _FailingSandbox:
    """Custom sandbox that always returns an error."""

    async def execute(self, code, tools, timeout):
        return ExecutionResult(
            success=False, error="sandbox error", error_output="sandbox failed"
        )


class TestCustomBackend:
    def test_custom_backend_used(self):
        mock = _MockSandbox()
        tk = Toolkit([greet], sandbox=mock)
        result = tk.execute_sync('print("test")', validate=False)
        assert result.success
        assert result.output == "mock output"
        assert len(mock.calls) == 1
        assert mock.calls[0]["code"] == 'print("test")'

    def test_error_propagation(self):
        failing = _FailingSandbox()
        tk = Toolkit([greet], sandbox=failing)
        result = tk.execute_sync('print("test")', validate=False)
        assert not result.success
        assert result.error == "sandbox error"


# ── Protocol compliance tests ─────────────────────────────────────────


class TestProtocol:
    def test_local_sandbox_satisfies_protocol(self):
        assert isinstance(LocalSandbox(), SandboxBackend)

    def test_mock_satisfies_protocol(self):
        assert isinstance(_MockSandbox(), SandboxBackend)

    def test_missing_method_does_not_satisfy(self):
        class Incomplete:
            pass

        assert not isinstance(Incomplete(), SandboxBackend)
