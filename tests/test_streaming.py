"""Tests for streaming execution output."""

import pytest

from ez_ptc import ExecutionEvent, ExecutionResult, ToolCallRecord, Toolkit, ez_tool


@ez_tool
def get_weather(location: str) -> dict:
    """Get current weather for a location.

    Args:
        location: City name
    """
    return {"temp": 22, "condition": "sunny"}


@ez_tool
def search(query: str, limit: int = 5) -> list:
    """Search the database.

    Args:
        query: Search query string
        limit: Maximum number of results
    """
    return [{"id": i, "name": f"Result {i}"} for i in range(limit)]


def _make_toolkit(**kwargs):
    return Toolkit([get_weather, search], **kwargs)


# ── Async streaming tests ─────────────────────────────────────────────


class TestAsyncStreaming:
    @pytest.mark.asyncio
    async def test_streaming_output_events(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming('print("hello")\nprint("world")'):
            events.append(event)

        output_events = [e for e in events if e.type == "output"]
        done_events = [e for e in events if e.type == "done"]

        assert len(output_events) > 0
        assert len(done_events) == 1

        full_output = "".join(e.data for e in output_events)
        assert "hello" in full_output
        assert "world" in full_output

        final = done_events[0].data
        assert isinstance(final, ExecutionResult)
        assert final.success

    @pytest.mark.asyncio
    async def test_streaming_tool_call_events(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming('w = get_weather("NYC")\nprint(w["condition"])'):
            events.append(event)

        tool_events = [e for e in events if e.type == "tool_call"]
        assert len(tool_events) == 1
        assert isinstance(tool_events[0].data, ToolCallRecord)
        assert tool_events[0].data.name == "get_weather"
        assert tool_events[0].data.args == ("NYC",)
        assert tool_events[0].data.result == {"temp": 22, "condition": "sunny"}

    @pytest.mark.asyncio
    async def test_streaming_done_event_is_last(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming('print("hi")'):
            events.append(event)

        assert len(events) >= 1
        assert events[-1].type == "done"
        assert isinstance(events[-1].data, ExecutionResult)

    @pytest.mark.asyncio
    async def test_streaming_error_produces_error_event(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming("1/0"):
            events.append(event)

        error_events = [e for e in events if e.type == "error"]
        done_events = [e for e in events if e.type == "done"]

        assert len(error_events) > 0
        error_text = "".join(e.data for e in error_events)
        assert "ZeroDivisionError" in error_text

        assert len(done_events) == 1
        assert not done_events[0].data.success

    @pytest.mark.asyncio
    async def test_streaming_validation_error(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming("import get_weather"):
            events.append(event)

        error_events = [e for e in events if e.type == "error"]
        done_events = [e for e in events if e.type == "done"]

        assert len(error_events) > 0
        assert len(done_events) == 1
        assert not done_events[0].data.success
        assert "Validation" in done_events[0].data.error

    @pytest.mark.asyncio
    async def test_streaming_complete_result(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming(
            'w = get_weather("NYC")\ns = search("test", limit=2)\nprint(f"weather={w}, results={len(s)}")'
        ):
            events.append(event)

        done = [e for e in events if e.type == "done"][0]
        assert done.data.success
        assert len(done.data.tool_calls) == 2

    @pytest.mark.asyncio
    async def test_streaming_multiple_tool_calls(self):
        tk = _make_toolkit()
        events = []
        async for event in tk.execute_streaming(
            'get_weather("NYC")\nsearch("test")\nprint("done")'
        ):
            events.append(event)

        tool_events = [e for e in events if e.type == "tool_call"]
        assert len(tool_events) == 2


# ── Sync streaming tests ──────────────────────────────────────────────


class TestSyncStreaming:
    def test_streaming_output_events(self):
        tk = _make_toolkit()
        events = list(tk.execute_streaming_sync('print("hello")\nprint("world")'))

        output_events = [e for e in events if e.type == "output"]
        done_events = [e for e in events if e.type == "done"]

        assert len(output_events) > 0
        assert len(done_events) == 1

        full_output = "".join(e.data for e in output_events)
        assert "hello" in full_output
        assert "world" in full_output

        final = done_events[0].data
        assert isinstance(final, ExecutionResult)
        assert final.success

    def test_streaming_tool_call_events(self):
        tk = _make_toolkit()
        events = list(tk.execute_streaming_sync('w = get_weather("NYC")\nprint(w["condition"])'))

        tool_events = [e for e in events if e.type == "tool_call"]
        assert len(tool_events) == 1
        assert isinstance(tool_events[0].data, ToolCallRecord)
        assert tool_events[0].data.name == "get_weather"

    def test_streaming_done_event_is_last(self):
        tk = _make_toolkit()
        events = list(tk.execute_streaming_sync('print("hi")'))

        assert events[-1].type == "done"
        assert isinstance(events[-1].data, ExecutionResult)
        assert events[-1].data.success

    def test_streaming_error_produces_error_event(self):
        tk = _make_toolkit()
        events = list(tk.execute_streaming_sync("1/0"))

        error_events = [e for e in events if e.type == "error"]
        done_events = [e for e in events if e.type == "done"]

        assert len(error_events) > 0
        assert len(done_events) == 1
        assert not done_events[0].data.success

    def test_streaming_validation_error(self):
        tk = _make_toolkit()
        events = list(tk.execute_streaming_sync("import get_weather"))

        done_events = [e for e in events if e.type == "done"]
        assert len(done_events) == 1
        assert not done_events[0].data.success
        assert "Validation" in done_events[0].data.error


# ── ExecutionEvent type tests ─────────────────────────────────────────


class TestEventTypes:
    def test_execution_event_fields(self):
        event = ExecutionEvent(type="output", data="hello")
        assert event.type == "output"
        assert event.data == "hello"

    def test_execution_result_attempts_default(self):
        result = ExecutionResult()
        assert result.attempts == 1
