"""Toolkit class — groups tools and provides prompt/tool mode interfaces."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import queue
import re
import threading
from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, Literal

from .executor import ExecutionEvent, ExecutionResult, PendingToolCall, ToolCallRecord
from .sandbox import LocalSandbox, SandboxBackend
from .schema import format_return_schema
from .tool import Tool
from .validator import validate_code


def _validation_error_result(errors: list[str], **kwargs: Any) -> ExecutionResult:
    """Build an ExecutionResult for a validation failure."""
    return ExecutionResult(
        success=False,
        error="Validation failed: " + "; ".join(errors),
        error_output="Validation errors:\n" + "\n".join(f"- {e}" for e in errors),
        **kwargs,
    )


def _find_called_tool_names(code: str, tool_names: set[str]) -> set[str]:
    """AST-scan code to find which tool names are called.

    Handles both direct calls like ``tool(args)`` and calls via ``parallel()``.
    """
    import ast as _ast

    try:
        tree = _ast.parse(code)
    except SyntaxError:
        return set()

    called: set[str] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            # Direct call: tool_name(...)
            if isinstance(node.func, _ast.Name) and node.func.id in tool_names:
                called.add(node.func.id)
            # parallel((tool_name, arg1), ...) — tool refs as first element of tuples
            if isinstance(node.func, _ast.Name) and node.func.id == "parallel":
                for arg in node.args:
                    if isinstance(arg, _ast.Starred) and isinstance(arg.value, (_ast.ListComp, _ast.GeneratorExp)):
                        elt = arg.value.elt
                        if isinstance(elt, _ast.Tuple) and elt.elts:
                            first = elt.elts[0]
                            if isinstance(first, _ast.Name) and first.id in tool_names:
                                called.add(first.id)
                    elif isinstance(arg, _ast.Tuple) and arg.elts:
                        first = arg.elts[0]
                        if isinstance(first, _ast.Name) and first.id in tool_names:
                            called.add(first.id)
    return called


def _run_sync(coro: Awaitable[Any]) -> Any:
    """Run a coroutine synchronously, handling running event loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in async context — run in a new thread with its own loop
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _build_preamble(assist_tool_chaining: bool) -> str:
    """Build the default preamble based on configuration."""
    text = "You have access to the following tools via Python function calls. They are already available — do NOT import them."
    if assist_tool_chaining:
        text += (
            "\nEach tool's return type is documented with a # Returns: comment "
            "— use these keys when chaining results."
        )
    return text


def _build_postamble(assist_tool_chaining: bool) -> str:
    """Build the default postamble based on configuration."""
    lines = [
        "IMPORTANT: Combine ALL operations into a single code block.",
        "",
        "Write Python code in a ```python code block.",
        "",
    ]
    if assist_tool_chaining:
        lines.append(
            "Chain results: store tool outputs in variables, pass them to subsequent calls or conditions."
        )
    else:
        lines.append(
            "Tool return schemas are not documented — do NOT access, index, or filter return values.\n"
            "Only print() each raw result: print(tool_a(...)), print(tool_b(...))."
        )
    lines += [
        "For parallel execution, use the built-in parallel() helper:",
        "    a, b = parallel((tool1, arg1), (tool2, arg1, arg2))",
        "    results = parallel(*[(tool, id) for id in ids])  # batch pattern",
        "parallel() takes (callable, arg1, arg2, ...) tuples and runs them concurrently.",
        "Returns a list of results in the same order as the input tuples.",
        "Do NOT call the tools inside parallel() — pass the function and its arguments separately.",
        "",
        "Environment: json, math, re are pre-imported. You can also import other standard library modules (collections, datetime, itertools, etc.).",
        "Restrictions: No file I/O, networking, or shell access (os, subprocess, socket, etc. are blocked).",
        "",
        "ALWAYS print() the final result you want to return.",
    ]
    return "\n".join(lines)


class Toolkit:
    """Groups tools and provides two modes of LLM integration.

    Mode 1 — Prompt mode (framework-free):
        toolkit.prompt() → inject into system prompt → LLM writes code
        → toolkit.extract_code() → toolkit.execute() → results

    Mode 2 — Tool mode (native framework integration):
        toolkit.as_tool() → register with any framework
        → LLM calls meta-tool → ez-ptc executes → results
    """

    _DEFAULT_ERROR_HINT = "If execution returns an error, analyze the traceback, fix your code, and try again."

    def __init__(
        self,
        tools: list[Tool],
        preamble: str | None = None,
        postamble: str | None = None,
        assist_tool_chaining: bool = False,
        timeout: float = 30.0,
        sandbox: SandboxBackend | None = None,
        error_hint: str | None = None,
        on_tool_call: Callable[[ToolCallRecord], None] | None = None,
    ) -> None:
        for item in tools:
            if not isinstance(item, Tool):
                raise TypeError(
                    f"Expected Tool instance, got {type(item).__name__}. Did you forget @ez_tool?"
                )
        self.tools = tools
        self._tool_map: dict[str, Tool] = {}
        for t in tools:
            if t.name in self._tool_map:
                raise ValueError(
                    f"Duplicate tool name '{t.name}'. Each tool in a Toolkit must have a unique name."
                )
            self._tool_map[t.name] = t
        self._custom_preamble = preamble
        self._custom_postamble = postamble
        self._assist_tool_chaining = assist_tool_chaining
        self._timeout = timeout
        self._sandbox: SandboxBackend = sandbox or LocalSandbox()
        self._custom_error_hint = error_hint
        self._on_tool_call = on_tool_call
        self._tool_name_set = set(self._tool_map.keys())
        self._tools_needing_approval = frozenset(
            name for name, tool in self._tool_map.items() if tool.requires_approval
        )

    def get_tool(self, name: str) -> Tool:
        """Look up a tool by name. Raises KeyError if not found."""
        return self._tool_map[name]

    def __iter__(self):
        return iter(self.tools)

    def __len__(self) -> int:
        return len(self.tools)

    @property
    def _has_async_tools(self) -> bool:
        return any(t.is_async for t in self.tools)

    @property
    def _preamble(self) -> str:
        if self._custom_preamble is not None:
            return self._custom_preamble
        return _build_preamble(self._assist_tool_chaining)

    @property
    def _error_hint(self) -> str:
        if self._custom_error_hint is not None:
            return self._custom_error_hint
        return self._DEFAULT_ERROR_HINT

    @property
    def _postamble(self) -> str:
        base = self._custom_postamble if self._custom_postamble is not None else _build_postamble(self._assist_tool_chaining)
        if self._error_hint:
            base += "\n" + self._error_hint
        return base

    def _return_schema_text(self, tool: Tool) -> str | None:
        """Return formatted return schema string for a tool, or None."""
        if not self._assist_tool_chaining or tool.return_schema is None:
            return None
        return format_return_schema(tool.return_schema)

    def _tool_listing_lines(self) -> list[str]:
        """Build tool listing lines used by tool_prompt, as_tool, and tool_schema."""
        lines = []
        for tool in self.tools:
            desc = tool.description or "No description"
            ret_text = self._return_schema_text(tool)
            line = f"- {tool.signature}\n  {desc}"
            if ret_text:
                line += f"\n  # {ret_text}"
            lines.append(line)
        return lines

    # ── Mode 1: Prompt mode ──────────────────────────────────────────

    def prompt(self) -> str:
        """Generate the instruction block for LLM system prompts.

        Returns a string containing:
        - Preamble (intro text)
        - Tool signatures with docstrings
        - Postamble (instructions for the LLM)
        """
        if not self.tools:
            return "No tools are available."

        parts = [self._preamble, "", "Available tools:", ""]

        for tool in self.tools:
            # Build the function signature block
            sig = f"def {tool.signature}:"
            doc = inspect.getdoc(tool.fn)
            if doc:
                doc_lines = doc.strip().split("\n")
                indented = "\n".join(f"    {line}" for line in doc_lines)
                block = f'{sig}\n    """{indented.lstrip()}\n    """'
            else:
                block = sig
            ret_text = self._return_schema_text(tool)
            if ret_text:
                block += f"\n    # {ret_text}"
            parts.append(block)
            parts.append("")

        parts.append(self._postamble)
        return "\n".join(parts)

    def extract_code(self, llm_response: str) -> str | None:
        """Extract Python code block from markdown-formatted LLM response.

        Looks for ```python ... ``` fenced code blocks.
        Returns the first match, or None if no code block found.
        """
        # Match ```python ... ``` blocks
        pattern = r"```python\s*\n(.*?)```"
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Also try generic ``` ... ``` blocks
        pattern = r"```\s*\n(.*?)```"
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()

        return None

    # ── Mode 2: Tool mode ────────────────────────────────────────────

    def tool_prompt(self) -> str:
        """Generate a system prompt block for tool mode.

        This tells the LLM how to use the ``execute_tools`` meta-tool,
        listing all available functions, their signatures, and environment
        capabilities. Include this in your system prompt alongside the tool
        schema.
        """
        parts = [
            "You have access to a code execution tool called `execute_tools`. "
            "Pass Python code in its `code` argument.\n"
            "IMPORTANT: Always combine ALL operations into a SINGLE execute_tools call "
            "— do NOT make multiple separate calls. Write one code block that handles everything.\n"
            "Inside the code, the following functions are already available — do NOT import them:",
            "",
        ]

        for line in self._tool_listing_lines():
            parts.append(line)
        parts.append("")

        if self._assist_tool_chaining:
            parts.append(
                "Chain results: store outputs in variables, pass them to subsequent calls or conditions."
            )
            parts.append(
                "Each tool's return type is documented above — use these keys when accessing results."
            )
        else:
            parts.append(
                "Tool return schemas are not documented — do NOT access, index, or filter return values.\n"
                "Only print() each raw result: print(tool_a(...)), print(tool_b(...))."
            )
        parts.append(
            "For parallel execution, use the built-in parallel() helper: a, b = parallel((tool1, arg1), (tool2, arg1, arg2))\n"
            "Batch pattern: results = parallel(*[(tool, id) for id in ids])\n"
            "parallel() takes (callable, arg1, ...) tuples and runs them concurrently. Returns a list of results in order.\n"
            "Do NOT call the tools inside parallel() — pass the function and its arguments separately."
        )
        parts.append(
            "json, math, re are pre-imported. You can also import other safe stdlib modules "
            "(collections, datetime, itertools, etc.)."
        )
        parts.append(
            "No file I/O, networking, or shell access (os, subprocess, socket, etc. are blocked)."
        )
        if self._error_hint:
            parts.append(self._error_hint)
        parts.append("ALWAYS print() the final result you want to return.")
        return "\n".join(parts)

    def as_tool(self) -> Callable[[str], Awaitable[str]]:
        """Return an async callable function that any framework can register as a tool.

        The returned function:
        - Accepts `code: str` — Python code to execute
        - Returns `str` — stdout on success, stderr/error on failure
        - Has proper type hints, docstring, and __name__ for framework introspection
        """
        # Build docstring listing all sub-tools
        tool_docs = []
        for tool in self.tools:
            desc = tool.description or "No description"
            ret_text = self._return_schema_text(tool)
            line = f"    - {tool.signature}\n      {desc}"
            if ret_text:
                line += f" | {ret_text}"
            tool_docs.append(line)
        tools_listing = "\n\n".join(tool_docs)

        if self._assist_tool_chaining:
            usage_hint = "    Store results in variables to chain between function calls."
        else:
            usage_hint = (
                "    Tool return schemas are not documented — do NOT access, index, or filter return values.\n"
                "    Only print() each raw result: print(tool_a(...)), print(tool_b(...))."
            )

        parallel_hint = (
            "    For parallel execution: a, b = parallel((tool1, arg1), (tool2, arg1, arg2))\n"
            "    Batch pattern: results = parallel(*[(tool, id) for id in ids])\n"
            "    Do NOT call tools inside parallel() — pass the function and its arguments separately."
        )
        error_line = f"    {self._error_hint}\n" if self._error_hint else ""
        docstring = (
            f"Execute Python code by passing it in the `code` argument.\n"
            f"IMPORTANT: Combine ALL operations into a SINGLE code block — do NOT make separate calls.\n"
            f"Inside the code, the following functions are already available — do NOT import them:\n\n"
            f"{tools_listing}\n\n"
            f"{usage_hint}\n"
            f"{parallel_hint}\n"
            f"{error_line}"
            f"    ALWAYS print() the final result.\n\n"
            f"    Args:\n"
            f"        code: Python code to execute"
        )

        toolkit_ref = self

        async def execute_tools(code: str) -> str:
            result = await toolkit_ref.execute(code)
            if not result.success and toolkit_ref._error_hint:
                return f"ERROR: {toolkit_ref._error_hint}\n\n{result.to_string()}"
            if (
                not result.output
                and result.tool_calls
                and not toolkit_ref._assist_tool_chaining
                and "print(" not in code
            ):
                return (
                    "[No output captured. You called tool(s) but did not print() the results. "
                    "Rewrite the code to print() each result immediately: print(tool_name(...))]"
                )
            return result.to_string()

        execute_tools.__name__ = "execute_tools"
        execute_tools.__qualname__ = "execute_tools"
        execute_tools.__doc__ = docstring
        execute_tools.__annotations__ = {"code": str, "return": str}

        return execute_tools

    def as_tool_sync(self) -> Callable[[str], str]:
        """Return a sync callable function that any framework can register as a tool.

        The returned function:
        - Accepts `code: str` — Python code to execute
        - Returns `str` — stdout on success, stderr/error on failure
        - Has proper type hints, docstring, and __name__ for framework introspection
        """
        # Reuse as_tool() for docstring/metadata, then wrap sync
        async_fn = self.as_tool()
        toolkit_ref = self

        def execute_tools(code: str) -> str:
            result = toolkit_ref.execute_sync(code)
            if not result.success and toolkit_ref._error_hint:
                return f"ERROR: {toolkit_ref._error_hint}\n\n{result.to_string()}"
            if (
                not result.output
                and result.tool_calls
                and not toolkit_ref._assist_tool_chaining
                and "print(" not in code
            ):
                return (
                    "[No output captured. You called tool(s) but did not print() the results. "
                    "Rewrite the code to print() each result immediately: print(tool_name(...))]"
                )
            return result.to_string()

        execute_tools.__name__ = async_fn.__name__
        execute_tools.__qualname__ = async_fn.__qualname__
        execute_tools.__doc__ = async_fn.__doc__
        execute_tools.__annotations__ = async_fn.__annotations__

        return execute_tools

    def tool_schema(self, format: Literal["openai", "anthropic", "gemini", "raw", "mistral"] = "openai") -> dict[str, Any]:
        """Return a tool definition dict in the specified provider format.

        Args:
            format: Provider format. Supported values:
                - 'openai' (default) — ``{"type": "function", "function": {...}}``
                - 'anthropic' — ``{"name": ..., "input_schema": {...}}``
                - 'gemini' — ``{"name": ..., "description": ..., "parameters": {...}}``
                - 'raw' — same as gemini (bare JSON schema, no wrapper)
                - 'mistral' — same as openai (Mistral uses OpenAI-compatible format)
        """
        # Build description with sub-tool listing
        tool_lines = []
        for tool in self.tools:
            desc = tool.description or "No description"
            ret_text = self._return_schema_text(tool)
            line = f"- {tool.signature}: {desc}"
            if ret_text:
                line += f" | {ret_text}"
            tool_lines.append(line)
        tools_desc = "\n".join(tool_lines)

        if self._assist_tool_chaining:
            usage_hint = "Store results in variables to chain between function calls. print() the final result."
        else:
            usage_hint = (
                "Tool return schemas are not documented — do NOT access, index, or filter return values.\n"
                "Only print() each raw result: print(tool_a(...)), print(tool_b(...))."
            )

        description = (
            f"Execute Python code via the `code` argument. "
            f"Available functions inside the code (already available — do NOT import them):\n{tools_desc}\n\n"
            f"IMPORTANT: Combine ALL operations into a SINGLE code block — do NOT make multiple separate calls.\n"
            f"{usage_hint}\n"
            f"For parallel execution: a, b = parallel((tool1, arg1), (tool2, arg1, arg2)). "
            f"Batch pattern: results = parallel(*[(tool, id) for id in ids]). "
            f"Do NOT call tools inside parallel() — pass the function and its arguments separately."
        )
        if self._error_hint:
            description += "\n" + self._error_hint

        code_desc = "Python code to execute. The listed functions are available as globals."

        parameters_schema = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": code_desc,
                }
            },
            "required": ["code"],
        }

        if format == "anthropic":
            return {
                "name": "execute_tools",
                "description": description,
                "input_schema": parameters_schema,
            }

        if format in ("gemini", "raw"):
            return {
                "name": "execute_tools",
                "description": description,
                "parameters": parameters_schema,
            }

        # OpenAI / Mistral format (default)
        return {
            "type": "function",
            "function": {
                "name": "execute_tools",
                "description": description,
                "parameters": parameters_schema,
            },
        }

    # ── Filtering ─────────────────────────────────────────────────────

    def filter(
        self,
        names: list[str] | None = None,
        predicate: Callable[[Tool], bool] | None = None,
    ) -> Toolkit:
        """Return a new Toolkit containing only matching tools.

        Args:
            names: If provided, include only tools with these names.
            predicate: If provided, include only tools where predicate(tool) is True.

        At least one of names or predicate must be provided. If both, both
        conditions must match (AND logic). Raises ValueError if the result
        would be empty.
        """
        if names is None and predicate is None:
            raise ValueError("At least one of 'names' or 'predicate' must be provided.")

        name_set = set(names) if names is not None else None

        filtered: list[Tool] = []
        for tool in self.tools:
            if name_set is not None and tool.name not in name_set:
                continue
            if predicate is not None and not predicate(tool):
                continue
            filtered.append(tool)

        if not filtered:
            raise ValueError("Filter matched no tools — result would be empty.")

        return Toolkit(
            tools=filtered,
            preamble=self._custom_preamble,
            postamble=self._custom_postamble,
            assist_tool_chaining=self._assist_tool_chaining,
            timeout=self._timeout,
            sandbox=self._sandbox,
            error_hint=self._custom_error_hint,
            on_tool_call=self._on_tool_call,
        )

    # ── MCP bridge ────────────────────────────────────────────────────

    @classmethod
    async def from_mcp(
        cls,
        session: Any,
        *,
        tool_names: list[str] | None = None,
        include_resources: bool = True,
        extra_tools: list[Tool] | None = None,
        return_schemas: dict[str, dict] | None = None,
        descriptions: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Toolkit:
        """Create a Toolkit from an MCP server session.

        Discovers tools and resources from the MCP server and wraps them
        as ez-ptc Tool objects. Requires the ``mcp`` optional dependency.

        Args:
            session: An active MCP ClientSession.
            tool_names: Optional filter — only include tools whose names match.
            include_resources: Whether to wrap resources/templates as tools.
            extra_tools: Additional local Tool objects to include.
            return_schemas: Optional mapping of tool name → return schema dict.
                Overrides MCP ``outputSchema``. Enables ``assist_tool_chaining``
                for MCP tools that lack ``outputSchema``.
            descriptions: Optional mapping of tool name → description string.
                Overrides the MCP server's description for matching tools.
            **kwargs: Passed to Toolkit.__init__ (preamble, postamble, etc.).
        """
        from .mcp import tools_from_mcp  # lazy import

        mcp_tools = await tools_from_mcp(
            session,
            tool_names=tool_names,
            include_resources=include_resources,
            return_schemas=return_schemas,
            descriptions=descriptions,
        )
        all_tools = mcp_tools + (extra_tools or [])
        return cls(all_tools, **kwargs)

    @classmethod
    def from_mcp_sync(
        cls,
        session: Any,
        **kwargs: Any,
    ) -> Toolkit:
        """Create a Toolkit from an MCP server session (sync version).

        Convenience wrapper around ``from_mcp()`` for sync contexts.
        """
        return _run_sync(cls.from_mcp(session, **kwargs))

    # ── Shared ────────────────────────────────────────────────────────

    async def execute(
        self,
        code: str,
        timeout: float | None = None,
        validate: bool = True,
        approved_calls: list[str] | None = None,
        max_retries: int = 0,
        retry_handler: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> ExecutionResult:
        """Execute LLM-generated Python code with tools available.

        This is an async method. For sync usage, use ``execute_sync()``.

        Args:
            code: Python code string to execute
            timeout: Maximum execution time in seconds (None uses toolkit default)
            validate: Run AST validation before execution (default True)
            approved_calls: List of tool names approved for execution. Tools with
                ``requires_approval=True`` that are called in the code but not in
                this list will cause execution to pause and return a result with
                ``is_paused=True`` and ``pending_tool_calls``.
            max_retries: Maximum number of retry attempts (0 = no retry, default)
            retry_handler: Async callable that takes (failed_code, error_message)
                and returns new code to try. Required when max_retries > 0.

        Returns:
            ExecutionResult with output, tool calls, and error info.
            The ``attempts`` field indicates how many times execution was tried.

        Raises:
            ValueError: If max_retries > 0 but retry_handler is None.
        """
        if max_retries > 0 and retry_handler is None:
            raise ValueError("retry_handler is required when max_retries > 0")

        effective_timeout = timeout if timeout is not None else self._timeout

        # Check for tools that require approval (before any execution)
        if self._tools_needing_approval:
            called_tools = _find_called_tool_names(code, self._tool_name_set)
            approved = set(approved_calls) if approved_calls else set()
            unapproved = (called_tools & self._tools_needing_approval) - approved
            if unapproved:
                return ExecutionResult(
                    pending_tool_calls=[
                        PendingToolCall(tool_name=name) for name in sorted(unapproved)
                    ],
                )

        all_tool_calls: list[ToolCallRecord] = []
        attempt = 0
        current_code = code

        while True:
            attempt += 1

            if validate:
                vr = validate_code(
                    current_code, self._tool_name_set, allow_await=False
                )
                if not vr.is_safe:
                    result = _validation_error_result(
                        vr.errors, attempts=attempt, tool_calls=list(all_tool_calls),
                    )
                    if attempt <= max_retries and retry_handler is not None:
                        error_msg = result.error_output or result.error or "Unknown error"
                        current_code = await retry_handler(current_code, error_msg)
                        continue
                    return result
                warning_prefix = ""
                if vr.warnings:
                    warning_prefix = "Validation warnings:\n" + "\n".join(f"- {w}" for w in vr.warnings) + "\n"

            result = await self._sandbox.execute(current_code, self._tool_map, effective_timeout, self._on_tool_call)

            if validate and vr.warnings:
                result.error_output = warning_prefix + result.error_output

            all_tool_calls.extend(result.tool_calls)

            if result.success or attempt > max_retries:
                result.tool_calls = all_tool_calls
                result.attempts = attempt
                return result

            # Retry: call the handler to get new code
            error_msg = result.error_output or result.error or "Unknown error"
            current_code = await retry_handler(current_code, error_msg)

    def execute_sync(
        self,
        code: str,
        timeout: float | None = None,
        validate: bool = True,
        approved_calls: list[str] | None = None,
        max_retries: int = 0,
        retry_handler: Callable[[str, str], str] | None = None,
    ) -> ExecutionResult:
        """Execute LLM-generated Python code with tools available (sync version).

        Convenience wrapper around ``execute()`` for sync contexts.

        Args:
            code: Python code string to execute
            timeout: Maximum execution time in seconds (None uses toolkit default)
            validate: Run AST validation before execution (default True)
            approved_calls: List of tool names approved for execution (see ``execute()``).
            max_retries: Maximum number of retry attempts (0 = no retry, default)
            retry_handler: Sync callable that takes (failed_code, error_message)
                and returns new code to try. Required when max_retries > 0.

        Returns:
            ExecutionResult with output, tool calls, and error info.

        Raises:
            ValueError: If max_retries > 0 but retry_handler is None.
        """
        async_handler = None
        if retry_handler is not None:
            sync_handler = retry_handler

            async def async_handler(failed_code: str, error_message: str) -> str:
                return sync_handler(failed_code, error_message)

        return _run_sync(
            self.execute(
                code,
                timeout=timeout,
                validate=validate,
                approved_calls=approved_calls,
                max_retries=max_retries,
                retry_handler=async_handler,
            )
        )

    # ── Streaming execution ───────────────────────────────────────────

    _STREAMING_DONE = object()

    def _start_streaming_execution(
        self, code: str, loop: asyncio.AbstractEventLoop | None = None,
    ) -> tuple[threading.Thread, queue.Queue, list[ExecutionResult]]:
        """Shared setup for streaming: starts execution thread, returns (thread, queue, result_holder)."""
        from .executor import execute_code

        event_queue: queue.Queue = queue.Queue()
        result_holder: list[ExecutionResult] = []

        def _run() -> None:
            try:
                r = execute_code(
                    code, self._tool_map, self._timeout,
                    loop=loop, on_tool_call=self._on_tool_call,
                    event_queue=event_queue,
                )
                result_holder.append(r)
            except Exception as e:
                result_holder.append(ExecutionResult(
                    success=False, error=f"{type(e).__name__}: {e}", error_output=str(e),
                ))
            finally:
                event_queue.put(self._STREAMING_DONE)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread, event_queue, result_holder

    def _finalize_streaming_result(
        self, result_holder: list[ExecutionResult], vr: Any | None,
    ) -> ExecutionEvent:
        """Build the final 'done' event, attaching validation warnings if any."""
        final_result = result_holder[0] if result_holder else ExecutionResult(
            success=False, error="Execution did not produce a result"
        )
        if vr is not None and vr.warnings:
            warning_prefix = "Validation warnings:\n" + "\n".join(f"- {w}" for w in vr.warnings) + "\n"
            final_result.error_output = warning_prefix + final_result.error_output
        return ExecutionEvent(type="done", data=final_result)

    async def execute_streaming(
        self,
        code: str,
        validate: bool = True,
    ) -> AsyncIterator[ExecutionEvent]:
        """Execute code and yield events as they occur.

        Yields ExecutionEvent objects with types:
        - "output": print() output (data is str)
        - "tool_call": tool invocation (data is ToolCallRecord)
        - "error": stderr output during failure (data is str)
        - "done": final event (data is ExecutionResult)
        """
        vr = None
        if validate:
            vr = validate_code(code, self._tool_name_set, allow_await=False)
            if not vr.is_safe:
                error_result = _validation_error_result(vr.errors)
                yield ExecutionEvent(type="error", data=error_result.error_output)
                yield ExecutionEvent(type="done", data=error_result)
                return

        loop = asyncio.get_running_loop()
        thread, event_queue, result_holder = self._start_streaming_execution(code, loop=loop)

        while True:
            try:
                event = await loop.run_in_executor(
                    None, lambda: event_queue.get(timeout=0.01)
                )
            except queue.Empty:
                if not thread.is_alive() and event_queue.empty():
                    break
                continue
            if event is self._STREAMING_DONE:
                break
            yield event

        await loop.run_in_executor(None, thread.join)
        yield self._finalize_streaming_result(result_holder, vr)

    def execute_streaming_sync(
        self,
        code: str,
        validate: bool = True,
    ) -> Iterator[ExecutionEvent]:
        """Execute code and yield events as they occur (sync version).

        Yields ExecutionEvent objects with types:
        - "output": print() output (data is str)
        - "tool_call": tool invocation (data is ToolCallRecord)
        - "error": stderr output during failure (data is str)
        - "done": final event (data is ExecutionResult)
        """
        vr = None
        if validate:
            vr = validate_code(code, self._tool_name_set, allow_await=False)
            if not vr.is_safe:
                error_result = _validation_error_result(vr.errors)
                yield ExecutionEvent(type="error", data=error_result.error_output)
                yield ExecutionEvent(type="done", data=error_result)
                return

        thread, event_queue, result_holder = self._start_streaming_execution(code)

        while True:
            try:
                event = event_queue.get(timeout=0.05)
            except queue.Empty:
                if not thread.is_alive() and event_queue.empty():
                    break
                continue
            if event is self._STREAMING_DONE:
                break
            yield event

        thread.join()
        yield self._finalize_streaming_result(result_holder, vr)
