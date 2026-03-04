"""Safe code execution engine for LLM-generated Python."""

from __future__ import annotations

import ast
import asyncio
import builtins
import inspect
import io
import json
import signal
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .tool import Tool


@dataclass
class ExecutionResult:
    """Result of executing LLM-generated code.

    Attributes:
        output: Captured stdout (print output)
        error_output: Captured stderr — critical for LLM to self-correct
        return_value: Last expression value if available
        tool_calls: Log of which tools were called with what args
        success: Whether execution completed without error
        error: Exception message if execution failed
    """

    output: str = ""
    error_output: str = ""
    return_value: Any = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: str | None = None

    def to_string(self) -> str:
        """Return a string optimized for token efficiency.

        On success: returns stdout, or repr(return_value) if stdout is empty.
        On failure: returns stderr/traceback only.
        """
        if self.success:
            if self.output:
                return self.output
            if self.return_value is not None:
                return repr(self.return_value)
            return ""
        return self.error_output or (self.error or "Unknown error")


class _TimeoutError(Exception):
    """Raised when code execution exceeds the timeout."""


def _make_tool_wrapper(
    tool: Tool,
    call_log: list[dict[str, Any]],
    loop: asyncio.AbstractEventLoop | None = None,
) -> Callable[..., Any]:
    """Create a wrapper around a tool function that logs calls."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_record: dict[str, Any] = {
            "name": tool.name,
            "args": args,
            "kwargs": kwargs,
        }

        result = tool.fn(*args, **kwargs)

        # Handle async tools
        if inspect.isawaitable(result):
            if loop is not None and loop.is_running():
                # Efficient path: dispatch to the main event loop
                future = asyncio.run_coroutine_threadsafe(result, loop)
                result = future.result()
            else:
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    current_loop = None

                if current_loop and current_loop.is_running():
                    # We're already in an async context — run in a new thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(asyncio.run, result).result()
                else:
                    result = asyncio.run(result)

        call_record["result"] = result
        call_log.append(call_record)
        return result

    wrapper.__name__ = tool.name
    wrapper.__doc__ = tool.description
    return wrapper


def _make_async_tool_wrapper(
    tool: Tool,
    call_log: list[dict[str, Any]],
) -> Callable[..., Any]:
    """Create an async wrapper around an async tool function that logs calls."""

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_record: dict[str, Any] = {
            "name": tool.name,
            "args": args,
            "kwargs": kwargs,
        }

        result = tool.fn(*args, **kwargs)

        if inspect.isawaitable(result):
            result = await result

        call_record["result"] = result
        call_log.append(call_record)
        return result

    wrapper.__name__ = tool.name
    wrapper.__doc__ = tool.description
    return wrapper


def _make_parallel_helper() -> Callable[..., list[Any]]:
    """Create a parallel() helper that runs (callable, *args) tuples concurrently."""
    import concurrent.futures

    def parallel(*specs: Any) -> list[Any]:
        """Run multiple tool calls in parallel.

        Each argument must be a tuple of (callable, arg1, arg2, ...).
        Returns a list of results in the same order as the input tuples.
        """
        if not specs:
            return []

        for i, spec in enumerate(specs):
            if not isinstance(spec, tuple):
                if callable(spec):
                    raise TypeError(
                        f"Argument {i} is a callable, not a tuple. "
                        f"Did you call the function instead of passing it? "
                        f"Use: parallel((tool, arg), ...) not parallel(tool(arg), ...)"
                    )
                raise TypeError(
                    f"Argument {i} must be a (callable, arg1, ...) tuple, got {type(spec).__name__}"
                )
            if len(spec) == 0 or not callable(spec[0]):
                raise TypeError(
                    f"Argument {i}: first element of each tuple must be a callable"
                )

        with concurrent.futures.ThreadPoolExecutor() as pool:
            futures = []
            for spec in specs:
                fn, *args = spec
                futures.append(pool.submit(fn, *args))
            return [f.result() for f in futures]

    return parallel


def _enrich_error(e: Exception, stderr_capture: io.StringIO) -> None:
    """Append available keys/attributes to error output for LLM self-correction."""
    tb = e.__traceback__
    if tb is None:
        return

    # Walk to innermost frame
    while tb.tb_next is not None:
        tb = tb.tb_next

    frame = tb.tb_frame
    # Only enrich errors from LLM code, not from tool internals
    if frame.f_code.co_filename not in ("<string>", "<llm_code>"):
        return

    if isinstance(e, KeyError) and e.args:
        missing_key = e.args[0]
        hints = []
        for var_name, var_val in frame.f_locals.items():
            if var_name.startswith("_"):
                continue
            if isinstance(var_val, dict) and missing_key not in var_val:
                keys = list(var_val.keys())[:20]
                hints.append(f"  {var_name}: {keys}")
            if len(hints) >= 3:
                break
        if hints:
            stderr_capture.write(
                f"\nHint — available keys in scope:\n" + "\n".join(hints) + "\n"
            )

    elif isinstance(e, AttributeError):
        hints = []
        for var_name, var_val in frame.f_locals.items():
            if var_name.startswith("_"):
                continue
            if isinstance(var_val, dict):
                keys = list(var_val.keys())[:20]
                hints.append(
                    f"  {var_name} is a dict — use ['{keys[0]}'] syntax. Keys: {keys}"
                    if keys
                    else f"  {var_name} is an empty dict"
                )
            if len(hints) >= 3:
                break
        if hints:
            stderr_capture.write(
                f"\nHint — variable is a dict, use ['key'] syntax:\n"
                + "\n".join(hints)
                + "\n"
            )


# Safe builtins that LLM-generated code can use
_SAFE_BUILTINS = {
    # Output
    "print": print,
    # Data types & constructors
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "bytes": bytes,
    "bytearray": bytearray,
    "complex": complex,
    "object": object,
    "slice": slice,
    "memoryview": memoryview,
    # Iteration & sequences
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "next": next,
    "iter": iter,
    # Math & aggregation
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "pow": pow,
    "divmod": divmod,
    # Logic & length
    "any": any,
    "all": all,
    "len": len,
    "callable": callable,
    # Data conversion
    "repr": repr,
    "chr": chr,
    "ord": ord,
    "hex": hex,
    "bin": bin,
    "oct": oct,
    "format": format,
    "ascii": ascii,
    # Type checking & introspection
    "isinstance": isinstance,
    "issubclass": issubclass,
    "type": type,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "delattr": delattr,
    "dir": dir,
    "id": id,
    "hash": hash,
    "super": super,
    "property": property,
    "staticmethod": staticmethod,
    "classmethod": classmethod,
    # Class construction
    "__build_class__": __build_class__,
    "__name__": "__main__",
    # Constants
    "True": True,
    "False": False,
    "None": None,
    # Exceptions
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "ImportError": ImportError,
    "ZeroDivisionError": ZeroDivisionError,
    "NotImplementedError": NotImplementedError,
    "OverflowError": OverflowError,
    "AssertionError": AssertionError,
    "OSError": OSError,
    "StopAsyncIteration": StopAsyncIteration,
    "Exception": Exception,
}

# Curated set of safe stdlib modules — no filesystem, networking, shell, or deserialization
_SAFE_MODULES = {
    "asyncio", "json", "math", "re", "datetime", "time", "calendar",
    "collections", "itertools", "functools", "operator", "bisect", "heapq",
    "typing", "types", "dataclasses", "enum", "abc",
    "string", "textwrap", "pprint", "copy",
    "random", "statistics", "decimal", "fractions",
    "base64", "hashlib", "uuid",
    "urllib.parse", "concurrent.futures",
}

# Parent packages of allowed submodules (e.g. "urllib" for "urllib.parse")
_SAFE_PARENT_PACKAGES = {mod.split(".")[0] for mod in _SAFE_MODULES if "." in mod}


def _safe_import(
    name: str,
    globals: dict | None = None,
    locals: dict | None = None,
    fromlist: tuple = (),
    level: int = 0,
) -> Any:
    """Restricted __import__ that only allows safe stdlib modules."""
    if level != 0:
        raise ImportError("Relative imports are not allowed")

    # Check if the module or a dotted submodule is in the allowlist
    if name in _SAFE_MODULES:
        return builtins.__import__(name, globals, locals, fromlist, level)

    # Allow parent packages of allowed submodules, but only when fromlist
    # resolves to an allowed full module path (e.g. "urllib" + fromlist=("parse",)
    # is OK because "urllib.parse" is in _SAFE_MODULES, but fromlist=("request",)
    # is blocked because "urllib.request" is not).
    if name in _SAFE_PARENT_PACKAGES:
        if fromlist:
            for item in fromlist:
                full = f"{name}.{item}"
                if full not in _SAFE_MODULES:
                    raise ImportError(
                        f"Import of '{full}' is not allowed. "
                        f"Only these submodules of '{name}' are allowed: "
                        + ", ".join(m for m in sorted(_SAFE_MODULES) if m.startswith(name + "."))
                    )
        return builtins.__import__(name, globals, locals, fromlist, level)

    available = sorted(_SAFE_MODULES)
    raise ImportError(
        f"Import of '{name}' is not allowed. "
        f"Available modules: {', '.join(available)}"
    )


def execute_code(
    code: str,
    tools: dict[str, Tool],
    timeout: float = 30.0,
    loop: asyncio.AbstractEventLoop | None = None,
    has_async_tools: bool = False,
) -> ExecutionResult:
    """Execute LLM-generated Python code with tools injected as globals.

    Args:
        code: Python code string to execute
        tools: Dict mapping tool names to Tool objects
        timeout: Maximum execution time in seconds
        loop: Optional event loop for efficient async tool dispatch
        has_async_tools: Deprecated — ignored. Kept for backward compatibility.

    Returns:
        ExecutionResult with captured output, tool calls, and error info
    """
    call_log: list[dict[str, Any]] = []
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    # Build restricted namespace
    namespace: dict[str, Any] = {}
    builtins_dict = dict(_SAFE_BUILTINS)
    builtins_dict["__import__"] = _safe_import
    namespace["__builtins__"] = builtins_dict

    # Pre-inject commonly needed modules (available without import)
    import math as _math
    import re as _re

    namespace["json"] = json
    namespace["asyncio"] = asyncio
    namespace["math"] = _math
    namespace["re"] = _re

    # Add tool wrappers — always sync; _make_tool_wrapper handles async tools
    # transparently via run_coroutine_threadsafe.
    for name, tool in tools.items():
        namespace[name] = _make_tool_wrapper(tool, call_log, loop=loop)

    # Inject parallel() helper for concurrent tool calls
    namespace["parallel"] = _make_parallel_helper()

    result = ExecutionResult()

    # Split code into body + last expression so we can capture its value
    # (like a Python REPL / Jupyter cell).
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result.success = False
        result.error = f"SyntaxError: {e}"
        result.error_output = f"SyntaxError: {e}"
        return result

    last_expr_code = None
    body_code = code  # default: run everything with exec

    if tree.body and isinstance(tree.body[-1], ast.Expr):
        # Last statement is a bare expression — compile it separately
        # so we can capture its value with eval().
        last_node = tree.body.pop()
        if tree.body:
            body_code = ast.unparse(tree)  # remaining statements
        else:
            body_code = None
        last_expr_code = ast.unparse(ast.Expression(body=last_node.value))

    def _run() -> None:
        nonlocal result
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                if body_code:
                    exec(body_code, namespace)
                if last_expr_code:
                    val = eval(last_expr_code, namespace)
                    result.return_value = val
        except _TimeoutError:
            result.success = False
            result.error = f"Execution timed out after {timeout} seconds"
        except Exception as e:
            result.success = False
            result.error = f"{type(e).__name__}: {e}"
            # Capture traceback to stderr for LLM self-correction
            tb = traceback.format_exc()
            stderr_capture.write(tb)
            _enrich_error(e, stderr_capture)

    # Detect if there's already a running event loop (e.g., inside an async framework
    # like Pydantic AI). If so, we must use thread-based execution so LLM code that
    # calls asyncio.run() gets a clean thread with no existing loop.
    def _has_running_loop() -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    # Use signal-based timeout on Unix when safe, threading otherwise
    _use_signal = (
        hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
        and not _has_running_loop()
    )

    if _use_signal:
        original_handler = signal.getsignal(signal.SIGALRM)

        def _timeout_handler(signum: int, frame: Any) -> None:
            raise _TimeoutError(f"Execution timed out after {timeout} seconds")

        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            import math as _math_
            signal.alarm(max(1, _math_.ceil(timeout)))
            _run()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, original_handler)
    else:
        # Fallback: run in a thread with a timeout.
        # Note: if the thread times out, the daemon thread continues running in the
        # background until the process exits. Python threads cannot be forcibly killed.
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            result.success = False
            result.error = f"Execution timed out after {timeout} seconds"

    result.output = stdout_capture.getvalue()
    result.error_output = stderr_capture.getvalue()
    result.tool_calls = call_log

    return result
