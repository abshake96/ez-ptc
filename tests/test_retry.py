"""Tests for auto-retry with error feedback."""

import pytest

from ez_ptc import ExecutionResult, Toolkit, ez_tool


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


# ── Async retry tests ─────────────────────────────────────────────────


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        tk = _make_toolkit()
        call_count = 0

        async def handler(failed_code: str, error_msg: str) -> str:
            nonlocal call_count
            call_count += 1
            return 'print("fixed")'

        result = await tk.execute(
            "x = undefined_var",
            max_retries=1,
            retry_handler=handler,
        )
        assert result.success
        assert "fixed" in result.output
        assert result.attempts == 2
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_exhausts_max_retries(self):
        tk = _make_toolkit()
        call_count = 0

        async def handler(failed_code: str, error_msg: str) -> str:
            nonlocal call_count
            call_count += 1
            return "x = still_broken"

        result = await tk.execute(
            "x = undefined_var",
            max_retries=2,
            retry_handler=handler,
        )
        assert not result.success
        assert result.attempts == 3  # 1 initial + 2 retries
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_handler_raises_value_error(self):
        tk = _make_toolkit()
        with pytest.raises(ValueError, match="retry_handler is required"):
            await tk.execute("print('hi')", max_retries=1, retry_handler=None)

    @pytest.mark.asyncio
    async def test_attempts_field_correct_on_first_try(self):
        tk = _make_toolkit()
        result = await tk.execute('print("ok")')
        assert result.attempts == 1
        assert result.success

    @pytest.mark.asyncio
    async def test_tool_calls_accumulate_across_retries(self):
        tk = _make_toolkit()

        async def handler(failed_code: str, error_msg: str) -> str:
            return 'w = get_weather("LA")\nprint(w["condition"])'

        result = await tk.execute(
            'w = get_weather("NYC")\nprint(w["nonexistent"])',
            max_retries=1,
            retry_handler=handler,
        )
        assert result.success
        assert result.attempts == 2
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].args == ("NYC",)
        assert result.tool_calls[1].args == ("LA",)

    @pytest.mark.asyncio
    async def test_retry_handler_receives_error_message(self):
        tk = _make_toolkit()
        received_errors = []

        async def handler(failed_code: str, error_msg: str) -> str:
            received_errors.append(error_msg)
            return 'print("fixed")'

        await tk.execute(
            "1/0",
            max_retries=1,
            retry_handler=handler,
        )
        assert len(received_errors) == 1
        assert "ZeroDivisionError" in received_errors[0]

    @pytest.mark.asyncio
    async def test_retry_handler_receives_failed_code(self):
        tk = _make_toolkit()
        received_codes = []

        async def handler(failed_code: str, error_msg: str) -> str:
            received_codes.append(failed_code)
            return 'print("fixed")'

        await tk.execute(
            "bad_code_here",
            max_retries=1,
            retry_handler=handler,
        )
        assert received_codes[0] == "bad_code_here"

    @pytest.mark.asyncio
    async def test_zero_retries_no_retry(self):
        tk = _make_toolkit()
        result = await tk.execute("x = undefined_var", max_retries=0)
        assert not result.success
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_validation_failure_is_retryable(self):
        tk = _make_toolkit()

        async def handler(failed_code: str, error_msg: str) -> str:
            return 'print("fixed")'

        result = await tk.execute(
            "import get_weather",  # validation error
            max_retries=1,
            retry_handler=handler,
        )
        assert result.success
        assert result.attempts == 2


# ── Sync retry tests ──────────────────────────────────────────────────


class TestSyncRetry:
    def test_retry_succeeds_on_second_attempt(self):
        tk = _make_toolkit()
        call_count = 0

        def handler(failed_code: str, error_msg: str) -> str:
            nonlocal call_count
            call_count += 1
            return 'print("fixed")'

        result = tk.execute_sync(
            "x = undefined_var",
            max_retries=1,
            retry_handler=handler,
        )
        assert result.success
        assert "fixed" in result.output
        assert result.attempts == 2
        assert call_count == 1

    def test_retry_exhausts_max_retries(self):
        tk = _make_toolkit()

        def handler(failed_code: str, error_msg: str) -> str:
            return "x = still_broken"

        result = tk.execute_sync(
            "x = undefined_var",
            max_retries=2,
            retry_handler=handler,
        )
        assert not result.success
        assert result.attempts == 3

    def test_no_retry_handler_raises_value_error(self):
        tk = _make_toolkit()
        with pytest.raises(ValueError, match="retry_handler is required"):
            tk.execute_sync("print('hi')", max_retries=1, retry_handler=None)

    def test_attempts_field_correct_on_first_try(self):
        tk = _make_toolkit()
        result = tk.execute_sync('print("ok")')
        assert result.attempts == 1
        assert result.success

    def test_tool_calls_accumulate_across_retries(self):
        tk = _make_toolkit()

        def handler(failed_code: str, error_msg: str) -> str:
            return 'w = get_weather("LA")\nprint(w["condition"])'

        result = tk.execute_sync(
            'w = get_weather("NYC")\nprint(w["nonexistent"])',
            max_retries=1,
            retry_handler=handler,
        )
        assert result.success
        assert result.attempts == 2
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].args == ("NYC",)
        assert result.tool_calls[1].args == ("LA",)

    def test_error_enrichment_passed_to_handler(self):
        """Error enrichment (e.g., key hints) should be in the error message."""
        tk = _make_toolkit()
        received_errors = []

        def handler(failed_code: str, error_msg: str) -> str:
            received_errors.append(error_msg)
            return 'print("fixed")'

        tk.execute_sync(
            'r = get_weather("NYC")\nprint(r["mileage"])',
            max_retries=1,
            retry_handler=handler,
        )
        assert len(received_errors) == 1
        assert "Hint" in received_errors[0] or "temp" in received_errors[0]
