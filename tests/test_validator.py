"""Tests for validator.py — AST-based pre-flight validation."""

from ez_ptc.validator import ValidationResult, validate_code


# ── ValidationResult tests ────────────────────────────────────────────


class TestValidationResult:
    def test_empty_is_safe(self):
        vr = ValidationResult()
        assert vr.is_safe

    def test_warnings_only_is_safe(self):
        vr = ValidationResult(warnings=["something odd"])
        assert vr.is_safe

    def test_errors_is_not_safe(self):
        vr = ValidationResult(errors=["bad thing"])
        assert not vr.is_safe

    def test_both_warnings_and_errors(self):
        vr = ValidationResult(warnings=["odd"], errors=["bad"])
        assert not vr.is_safe


# ── Tool import checks ────────────────────────────────────────────────


class TestToolImports:
    def test_import_tool_is_error(self):
        vr = validate_code("import search_cars", {"search_cars"})
        assert not vr.is_safe
        assert any("search_cars" in e for e in vr.errors)

    def test_from_tool_import_is_error(self):
        vr = validate_code("from search_cars import something", {"search_cars"})
        assert not vr.is_safe
        assert any("search_cars" in e for e in vr.errors)

    def test_stdlib_import_is_ok(self):
        vr = validate_code("import json", {"search_cars"})
        assert vr.is_safe

    def test_helpful_error_message(self):
        vr = validate_code("import search_cars", {"search_cars"})
        assert any("already available" in e for e in vr.errors)


# ── Dangerous attribute checks ────────────────────────────────────────


class TestDangerousAttrs:
    def test_globals_blocked(self):
        vr = validate_code("x.__globals__", set())
        assert not vr.is_safe
        assert any("__globals__" in e for e in vr.errors)

    def test_subclasses_blocked(self):
        vr = validate_code("x.__subclasses__()", set())
        assert not vr.is_safe
        assert any("__subclasses__" in e for e in vr.errors)

    def test_builtins_blocked(self):
        vr = validate_code("x.__builtins__", set())
        assert not vr.is_safe

    def test_code_blocked(self):
        vr = validate_code("f.__code__", set())
        assert not vr.is_safe

    def test_bases_blocked(self):
        vr = validate_code("cls.__bases__", set())
        assert not vr.is_safe

    def test_mro_blocked(self):
        vr = validate_code("cls.__mro__", set())
        assert not vr.is_safe

    def test_import_attr_blocked(self):
        vr = validate_code("x.__import__('os')", set())
        assert not vr.is_safe

    def test_class_is_warning(self):
        vr = validate_code("x.__class__", set())
        assert vr.is_safe
        assert len(vr.warnings) >= 1
        assert any("__class__" in w for w in vr.warnings)

    def test_dict_is_warning(self):
        vr = validate_code("x.__dict__", set())
        assert vr.is_safe
        assert any("__dict__" in w for w in vr.warnings)

    def test_name_is_ok(self):
        """__name__ is not in either blocklist."""
        vr = validate_code("x.__name__", set())
        assert vr.is_safe
        assert len(vr.warnings) == 0

    def test_normal_attr_is_ok(self):
        vr = validate_code("x.some_method()", set())
        assert vr.is_safe
        assert len(vr.errors) == 0


# ── Unknown call checks ──────────────────────────────────────────────


class TestUnknownCalls:
    def test_tool_call_ok(self):
        vr = validate_code("search_cars('toyota')", {"search_cars"})
        assert len(vr.warnings) == 0

    def test_builtin_call_ok(self):
        vr = validate_code("print(len([1, 2, 3]))", set())
        assert len(vr.warnings) == 0

    def test_user_defined_function_ok(self):
        code = "def helper(): pass\nhelper()"
        vr = validate_code(code, set())
        assert len(vr.warnings) == 0

    def test_method_call_ok(self):
        """Method calls (x.method()) should not trigger warnings."""
        vr = validate_code("results.append(1)", set())
        assert len(vr.warnings) == 0

    def test_class_call_ok(self):
        code = "class Foo: pass\nFoo()"
        vr = validate_code(code, set())
        assert len(vr.warnings) == 0

    def test_loop_var_ok(self):
        code = "for item in items:\n    item()"
        vr = validate_code(code, set())
        # 'item' is locally defined via for-loop, 'items' is unknown but not a call
        assert not any("item" == w.split("'")[1] for w in vr.warnings if "'" in w)

    def test_unknown_function_warns(self):
        vr = validate_code("mystery_function()", set())
        assert any("mystery_function" in w for w in vr.warnings)

    def test_imported_name_ok(self):
        code = "import datetime\ndatetime()"
        vr = validate_code(code, set())
        assert not any("datetime" in w for w in vr.warnings)

    def test_assigned_name_ok(self):
        code = "callback = get_callback()\ncallback()"
        vr = validate_code(code, set())
        assert not any("'callback'" in w for w in vr.warnings)


# ── Infinite loop checks ─────────────────────────────────────────────


class TestInfiniteLoops:
    def test_while_true_no_break_warns(self):
        code = "while True:\n    x = 1"
        vr = validate_code(code, set())
        assert any("infinite loop" in w.lower() for w in vr.warnings)

    def test_while_true_with_break_ok(self):
        code = "while True:\n    if done:\n        break"
        vr = validate_code(code, set())
        assert not any("infinite loop" in w.lower() for w in vr.warnings)

    def test_while_true_with_return_ok(self):
        code = "def f():\n    while True:\n        return 1"
        vr = validate_code(code, set())
        assert not any("infinite loop" in w.lower() for w in vr.warnings)

    def test_normal_while_ok(self):
        code = "while x < 10:\n    x += 1"
        vr = validate_code(code, set())
        assert not any("infinite loop" in w.lower() for w in vr.warnings)


# ── Excessive resource checks ────────────────────────────────────────


class TestExcessiveResources:
    def test_large_exponent_warns(self):
        code = "x = 2 ** 100000000"
        vr = validate_code(code, set())
        assert any("excessive" in w.lower() for w in vr.warnings)

    def test_large_multiplication_warns(self):
        code = "x = [0] * 10**9"
        vr = validate_code(code, set())
        assert any("excessive" in w.lower() for w in vr.warnings)

    def test_normal_operations_ok(self):
        code = "x = [0] * 100\ny = 2 ** 10"
        vr = validate_code(code, set())
        assert not any("excessive" in w.lower() for w in vr.warnings)


# ── Integration tests ─────────────────────────────────────────────────


class TestIntegration:
    def test_valid_code(self):
        code = """
weather = get_weather("NYC")
products = search("umbrellas", limit=3)
print(f"Weather: {weather}, Products: {products}")
"""
        vr = validate_code(code, {"get_weather", "search"})
        assert vr.is_safe
        assert len(vr.warnings) == 0

    def test_syntax_error(self):
        vr = validate_code("def foo(:", set())
        assert not vr.is_safe
        assert any("SyntaxError" in e for e in vr.errors)

    def test_multiple_issues(self):
        code = """
import search_cars
x.__globals__
mystery()
while True:
    pass
"""
        vr = validate_code(code, {"search_cars"})
        assert not vr.is_safe
        # Should have at least: import error + __globals__ error
        assert len(vr.errors) >= 2
        # Should have at least: unknown call warning + infinite loop warning
        assert len(vr.warnings) >= 2
