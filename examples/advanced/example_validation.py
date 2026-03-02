"""ez-ptc — Pre-flight code validation example.

Demonstrates the AST-based validation that catches common LLM mistakes
before code is executed: tool imports, dangerous attribute access,
unknown function calls, infinite loops, and excessive resource allocation.

No API keys required.

Usage:
    uv run python examples/advanced/example_validation.py
"""

from ez_ptc import Toolkit, ValidationResult, ez_tool, validate_code


@ez_tool
def search_cars(make: str, year: int = 2024) -> dict:
    """Search for cars by make and year.

    Args:
        make: Car manufacturer
        year: Model year
    """
    return {"make": make, "year": year, "results": 5}


@ez_tool
def get_price(car_id: int) -> dict:
    """Get the price of a car.

    Args:
        car_id: Car ID from search results
    """
    return {"car_id": car_id, "price": 25000}


tool_names = {"search_cars", "get_price"}


def demo_tool_import_detection():
    """LLMs often try to import tools that are already available as globals."""
    print("=" * 60)
    print("1. Tool Import Detection")
    print("=" * 60)

    bad_code = """\
import search_cars
results = search_cars("Toyota")
print(results)
"""
    vr = validate_code(bad_code, tool_names)
    print(f"  Code: import search_cars; ...")
    print(f"  is_safe: {vr.is_safe}")
    print(f"  Errors: {vr.errors}")
    print()

    # from-style import also caught
    vr2 = validate_code("from get_price import something", tool_names)
    print(f"  Code: from get_price import something")
    print(f"  is_safe: {vr2.is_safe}")
    print(f"  Errors: {vr2.errors}")
    print()


def demo_dangerous_attrs():
    """Detect sandbox-escape attempts via dunder attributes."""
    print("=" * 60)
    print("2. Dangerous Attribute Detection")
    print("=" * 60)

    # Blocked (error)
    dangerous_code = "obj.__globals__['os'].system('rm -rf /')"
    vr = validate_code(dangerous_code, tool_names)
    print(f"  Code: obj.__globals__[...]")
    print(f"  is_safe: {vr.is_safe}")
    print(f"  Errors: {vr.errors}")
    print()

    # Suspicious (warning only)
    suspicious_code = "print(x.__class__)"
    vr2 = validate_code(suspicious_code, tool_names)
    print(f"  Code: x.__class__")
    print(f"  is_safe: {vr2.is_safe}  (warnings don't block execution)")
    print(f"  Warnings: {vr2.warnings}")
    print()


def demo_unknown_calls():
    """Warn about functions not in tools, builtins, or local scope."""
    print("=" * 60)
    print("3. Unknown Function Call Detection")
    print("=" * 60)

    code_with_unknown = """\
result = search_cars("Honda")
formatted = format_output(result)
print(formatted)
"""
    vr = validate_code(code_with_unknown, tool_names)
    print(f"  Code: search_cars() + format_output()")
    print(f"  is_safe: {vr.is_safe}  (warnings only)")
    print(f"  Warnings: {vr.warnings}")
    print()

    # Locally defined functions are recognized
    code_with_local = """\
def format_output(data):
    return str(data)
result = search_cars("Honda")
formatted = format_output(result)
print(formatted)
"""
    vr2 = validate_code(code_with_local, tool_names)
    print(f"  Code: defines format_output() locally + search_cars()")
    print(f"  Warnings: {vr2.warnings}  (none — local def recognized)")
    print()


def demo_infinite_loops():
    """Detect while True without break/return."""
    print("=" * 60)
    print("4. Infinite Loop Detection")
    print("=" * 60)

    bad_loop = """\
while True:
    x = search_cars("Toyota")
"""
    vr = validate_code(bad_loop, tool_names)
    print(f"  Code: while True: ... (no break)")
    print(f"  Warnings: {vr.warnings}")
    print()

    ok_loop = """\
while True:
    x = search_cars("Toyota")
    if x["results"] > 0:
        break
"""
    vr2 = validate_code(ok_loop, tool_names)
    print(f"  Code: while True: ... break (has exit)")
    print(f"  Warnings: {vr2.warnings}  (none)")
    print()


def demo_excessive_resources():
    """Detect code that would allocate excessive memory."""
    print("=" * 60)
    print("5. Excessive Resource Detection")
    print("=" * 60)

    bad_alloc = "data = [0] * 10**9"
    vr = validate_code(bad_alloc, tool_names)
    print(f"  Code: [0] * 10**9")
    print(f"  Warnings: {vr.warnings}")
    print()


def demo_toolkit_integration():
    """Validation integrated with Toolkit.execute()."""
    print("=" * 60)
    print("6. Toolkit Integration")
    print("=" * 60)

    toolkit = Toolkit([search_cars, get_price])

    # Errors block execution entirely
    result = toolkit.execute_sync("import search_cars\nsearch_cars('BMW')")
    print(f"  Bad code (import tool):")
    print(f"    success: {result.success}")
    print(f"    error: {result.error}")
    print()

    # Warnings are passed through but code still runs
    result2 = toolkit.execute_sync("x = ''.__class__\nprint('still runs')")
    print(f"  Suspicious code (__class__ access):")
    print(f"    success: {result2.success}")
    print(f"    output: {result2.output.strip()}")
    print(f"    error_output starts with: {result2.error_output[:50]}...")
    print()

    # Skip validation when you know code is safe
    result3 = toolkit.execute_sync(
        'print(search_cars("Tesla"))',
        validate=False,
    )
    print(f"  validate=False (skip checks):")
    print(f"    success: {result3.success}")
    print(f"    output: {result3.output.strip()}")


if __name__ == "__main__":
    demo_tool_import_detection()
    demo_dangerous_attrs()
    demo_unknown_calls()
    demo_infinite_loops()
    demo_excessive_resources()
    demo_toolkit_integration()
