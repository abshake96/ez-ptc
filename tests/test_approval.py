"""Tests for human-in-the-loop tool approval."""

import pytest

from ez_ptc import ExecutionResult, PendingToolCall, Tool, Toolkit, ez_tool


# ── Test fixtures ─────────────────────────────────────────────────────


@ez_tool
def safe_tool(x: str) -> str:
    """A safe tool that doesn't need approval.

    Args:
        x: Input string
    """
    return f"safe:{x}"


@ez_tool(requires_approval=True)
def dangerous_tool(x: str) -> str:
    """A dangerous tool that needs approval.

    Args:
        x: Input string
    """
    return f"dangerous:{x}"


@ez_tool(requires_approval=True)
def another_dangerous_tool(y: int) -> str:
    """Another dangerous tool.

    Args:
        y: Input number
    """
    return f"another:{y}"


# ── Tool-level flag tests ────────────────────────────────────────────


class TestToolRequiresApproval:
    def test_default_is_false(self):
        assert safe_tool.requires_approval is False

    def test_decorator_sets_flag(self):
        assert dangerous_tool.requires_approval is True

    def test_direct_construction(self):
        tool = Tool(
            name="my_tool",
            description="A tool",
            parameters={"type": "object", "properties": {}},
            fn=lambda: None,
            signature="my_tool()",
            requires_approval=True,
        )
        assert tool.requires_approval is True

    def test_direct_construction_default(self):
        tool = Tool(
            name="my_tool",
            description="A tool",
            parameters={"type": "object", "properties": {}},
            fn=lambda: None,
            signature="my_tool()",
        )
        assert tool.requires_approval is False


# ── Execution approval tests ─────────────────────────────────────────


class TestExecutionApproval:
    def test_no_approval_needed_executes_normally(self):
        tk = Toolkit([safe_tool])
        result = tk.execute_sync('print(safe_tool("hello"))')
        assert result.success
        assert result.is_paused is False
        assert result.pending_tool_calls == []
        assert "safe:hello" in result.output

    def test_approval_needed_pauses_execution(self):
        tk = Toolkit([dangerous_tool])
        result = tk.execute_sync('print(dangerous_tool("delete everything"))')
        assert result.is_paused is True
        assert len(result.pending_tool_calls) == 1
        assert result.pending_tool_calls[0].tool_name == "dangerous_tool"
        assert result.output == ""
        assert result.tool_calls == []

    def test_approved_calls_allows_execution(self):
        tk = Toolkit([dangerous_tool])
        result = tk.execute_sync(
            'print(dangerous_tool("ok"))',
            approved_calls=["dangerous_tool"],
        )
        assert result.is_paused is False
        assert result.pending_tool_calls == []
        assert result.success
        assert "dangerous:ok" in result.output

    def test_mix_safe_and_dangerous_pauses(self):
        tk = Toolkit([safe_tool, dangerous_tool])
        code = """
a = safe_tool("hi")
b = dangerous_tool("bye")
print(a, b)
"""
        result = tk.execute_sync(code)
        assert result.is_paused is True
        assert len(result.pending_tool_calls) == 1
        assert result.pending_tool_calls[0].tool_name == "dangerous_tool"

    def test_mix_safe_and_dangerous_approved(self):
        tk = Toolkit([safe_tool, dangerous_tool])
        code = """
a = safe_tool("hi")
b = dangerous_tool("bye")
print(a, b)
"""
        result = tk.execute_sync(code, approved_calls=["dangerous_tool"])
        assert result.is_paused is False
        assert result.success
        assert "safe:hi" in result.output
        assert "dangerous:bye" in result.output

    def test_multiple_dangerous_tools_all_pending(self):
        tk = Toolkit([dangerous_tool, another_dangerous_tool])
        code = """
a = dangerous_tool("x")
b = another_dangerous_tool(42)
print(a, b)
"""
        result = tk.execute_sync(code)
        assert result.is_paused is True
        pending_names = {p.tool_name for p in result.pending_tool_calls}
        assert pending_names == {"dangerous_tool", "another_dangerous_tool"}

    def test_partial_approval(self):
        tk = Toolkit([dangerous_tool, another_dangerous_tool])
        code = """
a = dangerous_tool("x")
b = another_dangerous_tool(42)
print(a, b)
"""
        result = tk.execute_sync(code, approved_calls=["dangerous_tool"])
        assert result.is_paused is True
        pending_names = {p.tool_name for p in result.pending_tool_calls}
        assert pending_names == {"another_dangerous_tool"}

    def test_full_approval_of_multiple(self):
        tk = Toolkit([dangerous_tool, another_dangerous_tool])
        code = """
a = dangerous_tool("x")
b = another_dangerous_tool(42)
print(a, b)
"""
        result = tk.execute_sync(
            code,
            approved_calls=["dangerous_tool", "another_dangerous_tool"],
        )
        assert result.is_paused is False
        assert result.success
        assert "dangerous:x" in result.output
        assert "another:42" in result.output

    def test_approved_calls_for_safe_tool_is_noop(self):
        tk = Toolkit([safe_tool])
        result = tk.execute_sync(
            'print(safe_tool("test"))',
            approved_calls=["safe_tool"],
        )
        assert result.is_paused is False
        assert result.success
        assert "safe:test" in result.output

    def test_code_not_calling_dangerous_tool_executes(self):
        tk = Toolkit([safe_tool, dangerous_tool])
        result = tk.execute_sync('print(safe_tool("only safe"))')
        assert result.is_paused is False
        assert result.success
        assert "safe:only safe" in result.output

    def test_is_paused_flag_false_on_normal_execution(self):
        tk = Toolkit([safe_tool])
        result = tk.execute_sync('print("hi")')
        assert result.is_paused is False

    def test_is_paused_flag_false_on_error(self):
        tk = Toolkit([safe_tool])
        result = tk.execute_sync("1/0")
        assert result.is_paused is False
        assert result.success is False

    def test_pending_tool_calls_empty_by_default(self):
        result = ExecutionResult()
        assert result.pending_tool_calls == []
        assert result.is_paused is False


# ── Async execution tests ────────────────────────────────────────────


class TestAsyncApproval:
    async def test_async_approval_pauses(self):
        tk = Toolkit([dangerous_tool])
        result = await tk.execute('print(dangerous_tool("test"))')
        assert result.is_paused is True
        assert len(result.pending_tool_calls) == 1
        assert result.pending_tool_calls[0].tool_name == "dangerous_tool"

    async def test_async_approval_allows(self):
        tk = Toolkit([dangerous_tool])
        result = await tk.execute(
            'print(dangerous_tool("test"))',
            approved_calls=["dangerous_tool"],
        )
        assert result.is_paused is False
        assert result.success
        assert "dangerous:test" in result.output


# ── parallel() detection tests ────────────────────────────────────────


class TestParallelApproval:
    def test_detects_tool_in_parallel_tuples(self):
        tk = Toolkit([safe_tool, dangerous_tool])
        code = 'a, b = parallel((safe_tool, "x"), (dangerous_tool, "y"))'
        result = tk.execute_sync(code)
        assert result.is_paused is True
        assert result.pending_tool_calls[0].tool_name == "dangerous_tool"

    def test_detects_tool_in_parallel_batch(self):
        tk = Toolkit([dangerous_tool])
        code = 'results = parallel(*[(dangerous_tool, x) for x in ["a", "b"]])'
        result = tk.execute_sync(code)
        assert result.is_paused is True
        assert result.pending_tool_calls[0].tool_name == "dangerous_tool"

    def test_parallel_with_approval_executes(self):
        tk = Toolkit([safe_tool, dangerous_tool])
        code = """
a, b = parallel((safe_tool, "x"), (dangerous_tool, "y"))
print(a, b)
"""
        result = tk.execute_sync(code, approved_calls=["dangerous_tool"])
        assert result.is_paused is False
        assert result.success


# ── PendingToolCall dataclass tests ───────────────────────────────────


class TestPendingToolCall:
    def test_creation(self):
        ptc = PendingToolCall(tool_name="delete_file")
        assert ptc.tool_name == "delete_file"

    def test_import_from_package(self):
        from ez_ptc import PendingToolCall as PTC
        assert PTC is PendingToolCall
