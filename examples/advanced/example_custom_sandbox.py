"""ez-ptc — Custom sandbox backend example.

Demonstrates the pluggable SandboxBackend protocol: how to implement
your own execution backend (logging, Docker, E2B, Modal, etc.)
while keeping the zero-dep LocalSandbox as the default.

No API keys required.

Usage:
    uv run python examples/advanced/example_custom_sandbox.py
"""

import time

from ez_ptc import ExecutionResult, LocalSandbox, SandboxBackend, Toolkit, ez_tool


@ez_tool
def add(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number
        b: Second number
    """
    return a + b


@ez_tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers.

    Args:
        a: First number
        b: Second number
    """
    return a * b


# ── Example 1: LoggingSandbox ────────────────────────────────────────


class LoggingSandbox:
    """A sandbox that logs every execution and delegates to LocalSandbox.

    Useful for debugging, auditing, or monitoring in production.
    """

    def __init__(self):
        self._inner = LocalSandbox()
        self.log: list[dict] = []

    async def execute(self, code, tools, timeout):
        start = time.monotonic()
        result = await self._inner.execute(code, tools, timeout)
        elapsed = time.monotonic() - start

        entry = {
            "code": code.strip(),
            "success": result.success,
            "elapsed_ms": round(elapsed * 1000, 1),
            "tool_calls": [tc["name"] for tc in result.tool_calls],
        }
        self.log.append(entry)
        return result


def demo_logging_sandbox():
    print("=" * 60)
    print("1. LoggingSandbox — audits every execution")
    print("=" * 60)

    sandbox = LoggingSandbox()
    toolkit = Toolkit([add, multiply], sandbox=sandbox)

    # Run a few executions
    toolkit.execute_sync("print(add(2, 3))")
    toolkit.execute_sync("print(multiply(4, 5))")
    toolkit.execute_sync("print(add(multiply(2, 3), 4))")

    print("\n  Execution log:")
    for i, entry in enumerate(sandbox.log, 1):
        print(f"    [{i}] success={entry['success']}, "
              f"elapsed={entry['elapsed_ms']}ms, "
              f"tools={entry['tool_calls']}")
        print(f"        code: {entry['code'][:60]}")
    print()


# ── Example 2: DryRunSandbox ─────────────────────────────────────────


class DryRunSandbox:
    """A sandbox that never executes code — just returns a placeholder.

    Useful for testing prompt generation and tool schema without
    actually running anything.
    """

    def __init__(self):
        self.last_code = None

    async def execute(self, code, tools, timeout):
        self.last_code = code
        return ExecutionResult(
            success=True,
            output=f"[DRY RUN] Would execute {len(code)} chars with {len(tools)} tools (timeout={timeout}s)",
        )


def demo_dry_run_sandbox():
    print("=" * 60)
    print("2. DryRunSandbox — never executes, just records")
    print("=" * 60)

    sandbox = DryRunSandbox()
    toolkit = Toolkit([add, multiply], sandbox=sandbox, timeout=10.0)

    result = toolkit.execute_sync("print(add(1, 2))", validate=False)
    print(f"  Output: {result.output}")
    print(f"  Last code received: {sandbox.last_code!r}")
    print()


# ── Example 3: Protocol compliance ───────────────────────────────────


def demo_protocol_check():
    print("=" * 60)
    print("3. Protocol Compliance Check")
    print("=" * 60)

    # Any class with async execute(code, tools, timeout) -> ExecutionResult works
    print(f"  LocalSandbox satisfies SandboxBackend: {isinstance(LocalSandbox(), SandboxBackend)}")
    print(f"  LoggingSandbox satisfies SandboxBackend: {isinstance(LoggingSandbox(), SandboxBackend)}")
    print(f"  DryRunSandbox satisfies SandboxBackend: {isinstance(DryRunSandbox(), SandboxBackend)}")

    class Incomplete:
        pass

    print(f"  Incomplete class satisfies SandboxBackend: {isinstance(Incomplete(), SandboxBackend)}")
    print()


# ── Example 4: Default behavior ──────────────────────────────────────


def demo_default_sandbox():
    print("=" * 60)
    print("4. Default Behavior — LocalSandbox")
    print("=" * 60)

    # When you don't pass sandbox=, Toolkit uses LocalSandbox automatically
    toolkit = Toolkit([add, multiply])
    print(f"  Sandbox type: {type(toolkit._sandbox).__name__}")

    result = toolkit.execute_sync("print(add(10, 20))")
    print(f"  Result: {result.output.strip()}")
    print()


if __name__ == "__main__":
    demo_logging_sandbox()
    demo_dry_run_sandbox()
    demo_protocol_check()
    demo_default_sandbox()
