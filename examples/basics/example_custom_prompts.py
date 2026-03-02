"""ez-ptc — Custom preamble and postamble example.

Demonstrates how to override the default system prompt text that
gets injected before and after the tool listings. Useful for
domain-specific instructions, different languages, or custom formats.

No API keys required.

Usage:
    uv run python examples/basics/example_custom_prompts.py
"""

from ez_ptc import Toolkit, ez_tool


@ez_tool
def calculate(expression: str) -> float:
    """Evaluate a math expression safely.

    Args:
        expression: Math expression like "2 + 3 * 4"
    """
    import ast
    return float(eval(compile(ast.parse(expression, mode="eval"), "<expr>", "eval")))


@ez_tool
def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between units.

    Args:
        value: Numeric value to convert
        from_unit: Source unit (e.g. "km", "miles", "kg", "lbs")
        to_unit: Target unit
    """
    conversions = {
        ("km", "miles"): 0.621371,
        ("miles", "km"): 1.60934,
        ("kg", "lbs"): 2.20462,
        ("lbs", "kg"): 0.453592,
        ("celsius", "fahrenheit"): lambda v: v * 9/5 + 32,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5/9,
    }
    key = (from_unit.lower(), to_unit.lower())
    factor = conversions.get(key)
    if factor is None:
        raise ValueError(f"Unknown conversion: {from_unit} -> {to_unit}")
    return factor(value) if callable(factor) else value * factor


tools = [calculate, convert_units]


def demo_default_prompt():
    """Show the default prompt (no customization)."""
    print("=" * 60)
    print("1. Default Prompt")
    print("=" * 60)

    toolkit = Toolkit(tools)
    print(toolkit.prompt())
    print()


def demo_custom_preamble():
    """Override the preamble with domain-specific instructions."""
    print("=" * 60)
    print("2. Custom Preamble")
    print("=" * 60)

    toolkit = Toolkit(
        tools,
        preamble=(
            "You are a science tutor. Use the tools below to help students "
            "with calculations and unit conversions. Show your work step by step. "
            "The tools are pre-loaded — do NOT import them."
        ),
    )
    prompt = toolkit.prompt()
    # Show just the preamble
    lines = prompt.split("\n")
    print(f"  Preamble: {lines[0]}")
    print()


def demo_custom_postamble():
    """Override the postamble with specific output format requirements."""
    print("=" * 60)
    print("3. Custom Postamble")
    print("=" * 60)

    toolkit = Toolkit(
        tools,
        postamble=(
            "Write Python code in a ```python block.\n"
            "IMPORTANT: Always show intermediate steps as comments.\n"
            "Format the final answer as: ANSWER: <value> <unit>\n"
            "Always print() the final answer."
        ),
    )
    prompt = toolkit.prompt()
    # Show just the postamble (everything after the last tool definition)
    in_postamble = False
    for line in prompt.split("\n"):
        if in_postamble:
            print(f"  {line}")
        if line.startswith("Write Python"):
            in_postamble = True
            print(f"  {line}")
    print()


def demo_both_custom():
    """Override both preamble and postamble."""
    print("=" * 60)
    print("4. Both Custom — Domain-specific Prompt")
    print("=" * 60)

    toolkit = Toolkit(
        tools,
        preamble="You are a physics calculator. Use these tools (pre-loaded, do NOT import):",
        postamble=(
            "Respond with Python code in a ```python block.\n"
            "Always include units in your output.\n"
            "Use print() for the final answer."
        ),
    )
    print(toolkit.prompt())
    print()


def demo_execution_with_custom():
    """Custom prompts don't affect execution — just prompt generation."""
    print("=" * 60)
    print("5. Execution (custom prompts don't affect execution)")
    print("=" * 60)

    toolkit = Toolkit(
        tools,
        preamble="Custom intro",
        postamble="Custom outro",
    )

    # Execution works the same regardless of prompt customization
    result = toolkit.execute_sync("""
distance_km = 42.195  # marathon distance
distance_miles = convert_units(distance_km, "km", "miles")
print(f"Marathon: {distance_km} km = {distance_miles:.2f} miles")
""")
    print(f"  Output: {result.output.strip()}")
    print(f"  Success: {result.success}")
    print()


if __name__ == "__main__":
    demo_default_prompt()
    demo_custom_preamble()
    demo_custom_postamble()
    demo_both_custom()
    demo_execution_with_custom()
