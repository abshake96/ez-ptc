"""ez-ptc — Error handling and timeout example.

Demonstrates what happens when LLM-generated code fails: validation
errors, runtime exceptions, timeouts, and how to use ExecutionResult
fields for error recovery.

No API keys required.

Usage:
    uv run python examples/advanced/example_error_handling.py
"""

from ez_ptc import Toolkit, ez_tool


@ez_tool
def divide(a: float, b: float) -> float:
    """Divide a by b.

    Args:
        a: Numerator
        b: Denominator
    """
    return a / b


@ez_tool
def lookup(key: str) -> str:
    """Look up a value by key.

    Args:
        key: The key to look up
    """
    data = {"name": "Alice", "age": "30"}
    if key not in data:
        raise KeyError(f"Key '{key}' not found. Available: {list(data.keys())}")
    return data[key]


toolkit = Toolkit([divide, lookup], timeout=5.0)


def demo_runtime_error():
    """Show how runtime errors are captured in ExecutionResult."""
    print("=" * 60)
    print("1. Runtime Error — ZeroDivisionError")
    print("=" * 60)

    result = toolkit.execute_sync("print(divide(10, 0))")

    print(f"  success: {result.success}")
    print(f"  error: {result.error}")
    print(f"  error_output (first 3 lines):")
    for line in result.error_output.strip().split("\n")[:3]:
        print(f"    {line}")
    print()

    # to_string() returns the right thing for both success and failure
    print(f"  to_string(): {result.to_string()[:80]}...")
    print()


def demo_tool_exception():
    """Show how tool-raised exceptions propagate."""
    print("=" * 60)
    print("2. Tool Exception — KeyError from lookup()")
    print("=" * 60)

    result = toolkit.execute_sync('print(lookup("email"))')

    print(f"  success: {result.success}")
    print(f"  error: {result.error}")
    print()


def demo_validation_failure():
    """Show how validation errors block execution."""
    print("=" * 60)
    print("3. Validation Failure — code never runs")
    print("=" * 60)

    # This code tries to import a tool and access __globals__
    bad_code = """\
import divide
x = divide.__globals__
print(x)
"""
    result = toolkit.execute_sync(bad_code)

    print(f"  success: {result.success}")
    print(f"  error: {result.error}")
    print(f"  output: {result.output!r}  (empty — code never ran)")
    print(f"  tool_calls: {result.tool_calls}  (empty — code never ran)")
    print()


def demo_timeout():
    """Show how timeouts work at toolkit and per-call level."""
    print("=" * 60)
    print("4. Timeout — infinite loop stopped after 2s")
    print("=" * 60)

    # Toolkit default is 5s, but we override to 2s for this call
    result = toolkit.execute_sync(
        "x = 0\nwhile True:\n    x += 1",
        timeout=2.0,
        validate=False,  # skip validation warning about while True
    )

    print(f"  success: {result.success}")
    print(f"  error: {result.error}")
    print()


def demo_syntax_error():
    """Show how syntax errors are caught (by validation and by executor)."""
    print("=" * 60)
    print("5. Syntax Error — caught at validation stage")
    print("=" * 60)

    result = toolkit.execute_sync("def foo(:")

    print(f"  success: {result.success}")
    print(f"  error: {result.error}")
    print()


def demo_return_value():
    """Show how ExecutionResult.return_value captures the last expression."""
    print("=" * 60)
    print("6. Return Value — last expression captured like a REPL")
    print("=" * 60)

    result = toolkit.execute_sync("divide(100, 4)")

    print(f"  success: {result.success}")
    print(f"  output: {result.output!r}  (no print() call)")
    print(f"  return_value: {result.return_value}")
    print(f"  to_string(): {result.to_string()}")
    print()


def demo_error_recovery_pattern():
    """Show the pattern for feeding errors back to an LLM."""
    print("=" * 60)
    print("7. Error Recovery Pattern")
    print("=" * 60)

    # Simulate an LLM making a mistake, then self-correcting
    attempts = [
        # Attempt 1: LLM tries to import the tool
        'import divide\nprint(divide(10, 3))',
        # Attempt 2: LLM fixes the import issue but divides by zero
        'print(divide(10, 0))',
        # Attempt 3: LLM gets it right
        'result = divide(10, 3)\nprint(f"10 / 3 = {result:.2f}")',
    ]

    for i, code in enumerate(attempts, 1):
        result = toolkit.execute_sync(code)
        status = "OK" if result.success else "FAIL"
        print(f"  Attempt {i} [{status}]: {code.split(chr(10))[0][:50]}...")

        if result.success:
            print(f"    Output: {result.output.strip()}")
            break
        else:
            # In a real app, you'd feed this back to the LLM
            feedback = result.to_string()
            print(f"    Error feedback: {feedback[:80]}...")
    print()


if __name__ == "__main__":
    demo_runtime_error()
    demo_tool_exception()
    demo_validation_failure()
    demo_timeout()
    demo_syntax_error()
    demo_return_value()
    demo_error_recovery_pattern()
