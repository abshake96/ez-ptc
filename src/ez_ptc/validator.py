"""AST-based pre-flight validation for LLM-generated code."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of static code validation.

    Attributes:
        warnings: Non-blocking issues (code still executes).
        errors: Blocking issues (code will NOT execute).
    """

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        """True when there are no blocking errors."""
        return len(self.errors) == 0


# Dunders that allow sandbox escape — always blocked.
_DANGEROUS_ATTRS = frozenset(
    {
        "__import__",
        "__builtins__",
        "__globals__",
        "__code__",
        "__subclasses__",
        "__bases__",
        "__mro__",
    }
)

# Dunders that are suspicious but not outright dangerous — warn only.
_SUSPICIOUS_ATTRS = frozenset({"__class__", "__dict__"})

# Builtins available in the sandbox (mirrors executor._SAFE_BUILTINS keys).
_SAFE_BUILTIN_NAMES = frozenset(
    {
        "print",
        "str",
        "int",
        "float",
        "bool",
        "dict",
        "list",
        "tuple",
        "set",
        "frozenset",
        "bytes",
        "bytearray",
        "complex",
        "object",
        "slice",
        "memoryview",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "next",
        "iter",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "pow",
        "divmod",
        "any",
        "all",
        "len",
        "callable",
        "repr",
        "chr",
        "ord",
        "hex",
        "bin",
        "oct",
        "format",
        "ascii",
        "isinstance",
        "issubclass",
        "type",
        "hasattr",
        "getattr",
        "setattr",
        "delattr",
        "dir",
        "id",
        "hash",
        "super",
        "property",
        "staticmethod",
        "classmethod",
        # Exceptions
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "StopIteration",
        "ImportError",
        "ZeroDivisionError",
        "NotImplementedError",
        "OverflowError",
        "AssertionError",
        "OSError",
        "StopAsyncIteration",
        "Exception",
    }
)

# Modules pre-injected into the sandbox namespace (available without import).
_PRE_INJECTED_MODULES = frozenset({"json", "asyncio", "math", "re"})


def validate_code(code: str, tool_names: set[str]) -> ValidationResult:
    """Validate LLM-generated code before execution.

    Runs lightweight AST checks to catch common LLM mistakes.
    This is defense-in-depth, not a security boundary.

    Args:
        code: Python source code to validate.
        tool_names: Names of tools available in the sandbox.

    Returns:
        ValidationResult with any warnings and errors found.
    """
    result = ValidationResult()

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result.errors.append(f"SyntaxError: {e}")
        return result

    _check_tool_imports(tree, tool_names, result)
    _check_dangerous_attrs(tree, result)
    _check_unknown_calls(tree, tool_names, result)
    _check_infinite_loops(tree, result)
    _check_excessive_resources(tree, result)

    return result


# ── Individual checks ─────────────────────────────────────────────────


def _check_tool_imports(
    tree: ast.Module, tool_names: set[str], result: ValidationResult
) -> None:
    """Detect ``import tool_name`` or ``from tool_name import ...``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in tool_names:
                    result.errors.append(
                        f"Do not import '{alias.name}' — it is already available as a global function."
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module in tool_names:
                result.errors.append(
                    f"Do not import from '{node.module}' — it is already available as a global function."
                )


def _check_dangerous_attrs(tree: ast.Module, result: ValidationResult) -> None:
    """Detect access to dangerous or suspicious dunder attributes."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in _DANGEROUS_ATTRS:
                result.errors.append(
                    f"Access to '{node.attr}' is not allowed."
                )
            elif node.attr in _SUSPICIOUS_ATTRS:
                result.warnings.append(
                    f"Access to '{node.attr}' is suspicious and may not work in the sandbox."
                )


def _check_unknown_calls(
    tree: ast.Module, tool_names: set[str], result: ValidationResult
) -> None:
    """Warn about calls to functions not in tools, builtins, or locally defined names."""
    locally_defined = _collect_locally_defined(tree)
    known = tool_names | _SAFE_BUILTIN_NAMES | _PRE_INJECTED_MODULES | locally_defined

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in known:
                result.warnings.append(
                    f"Unknown function '{node.func.id}' — not a tool, builtin, or locally defined name."
                )


def _collect_locally_defined(tree: ast.Module) -> set[str]:
    """Collect all names defined locally in the code."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_extract_names(target))
        elif isinstance(node, ast.For):
            names.update(_extract_names(node.target))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _extract_names(node: ast.AST) -> set[str]:
    """Extract variable names from an assignment target or for-target."""
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            names.update(_extract_names(elt))
    return names


def _check_infinite_loops(tree: ast.Module, result: ValidationResult) -> None:
    """Warn about ``while True`` loops without ``break`` or ``return``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                if not _body_has_exit(node.body):
                    result.warnings.append(
                        "Possible infinite loop: 'while True' without break or return."
                    )


def _body_has_exit(body: list[ast.stmt]) -> bool:
    """Check if a list of statements contains a break or return.

    Skips nested function/class definitions — a ``return`` inside a nested
    function does not exit the enclosing loop.
    """
    for stmt in body:
        if isinstance(stmt, (ast.Break, ast.Return)):
            return True
        # Skip nested functions/classes — return/break inside them doesn't exit our loop
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # Recurse into compound statement bodies (If, For, While, Try, With, etc.)
        if hasattr(stmt, "body") and _body_has_exit(stmt.body):
            return True
        if hasattr(stmt, "orelse") and _body_has_exit(stmt.orelse):
            return True
        if hasattr(stmt, "handlers"):  # try/except
            for handler in stmt.handlers:
                if _body_has_exit(handler.body):
                    return True
        if hasattr(stmt, "finalbody") and _body_has_exit(stmt.finalbody):
            return True
    return False


def _check_excessive_resources(tree: ast.Module, result: ValidationResult) -> None:
    """Warn about expressions that may allocate excessive memory."""
    _LARGE_THRESHOLD = 10**7

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                # x ** large_number
                if isinstance(node.right, ast.Constant) and isinstance(
                    node.right.value, (int, float)
                ):
                    if node.right.value > _LARGE_THRESHOLD:
                        result.warnings.append(
                            f"Potential excessive resource usage: exponent of {node.right.value}."
                        )
            elif isinstance(node.op, ast.Mult):
                # [0] * large_number or large_number * [0]
                left_val = _get_constant_value(node.left)
                right_val = _get_constant_value(node.right)
                if left_val is not None and left_val > _LARGE_THRESHOLD:
                    result.warnings.append(
                        f"Potential excessive resource usage: multiplication by {left_val}."
                    )
                elif right_val is not None and right_val > _LARGE_THRESHOLD:
                    result.warnings.append(
                        f"Potential excessive resource usage: multiplication by {right_val}."
                    )


def _get_constant_value(node: ast.AST) -> int | float | None:
    """Extract a numeric constant value from an AST node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    # Handle 10**9 style expressions
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        base = _get_constant_value(node.left)
        exp = _get_constant_value(node.right)
        if base is not None and exp is not None:
            try:
                val = base**exp
                return val if isinstance(val, (int, float)) else None
            except (OverflowError, ValueError):
                return float("inf")
    return None
