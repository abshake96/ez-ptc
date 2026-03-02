"""Toolkit class — groups tools and provides prompt/tool mode interfaces."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import re
from typing import Any, Awaitable, Callable, Literal

from .executor import ExecutionResult
from .sandbox import LocalSandbox, SandboxBackend
from .schema import format_return_schema
from .tool import Tool
from .validator import validate_code


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
        "For parallel execution, use asyncio (tools are sync — use asyncio.to_thread):",
        "    async def main():",
        "        a, b = await asyncio.gather(asyncio.to_thread(tool1, ...), asyncio.to_thread(tool2, ...))",
        "        print(a, b)",
        "    asyncio.run(main())",
        "To group multiple tool calls per task, use a regular (not async) wrapper:",
        "    def process(x):",
        "        return tool1(x), tool2(x)",
        "    async def main():",
        "        results = await asyncio.gather(*[asyncio.to_thread(process, x) for x in items])",
        "        print(results)",
        "    asyncio.run(main())",
        "WARNING: Do NOT pass async functions to asyncio.to_thread — it only works with sync functions.",
        "",
        "Environment: json, math, re, asyncio are pre-imported. You can also import other standard library modules (collections, datetime, itertools, etc.).",
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

    def __iter__(self):
        return iter(self.tools)

    def __len__(self) -> int:
        return len(self.tools)

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
            "For parallel execution, use asyncio.gather with asyncio.to_thread (tools are sync functions).\n"
            "To group multiple calls, use a regular def wrapper (not async): def process(x): return tool1(x), tool2(x)\n"
            "Do NOT pass async functions to asyncio.to_thread — it only works with sync functions."
        )
        parts.append(
            "json, math, re, asyncio are pre-imported. You can also import other safe stdlib modules "
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

        error_line = f"    {self._error_hint}\n" if self._error_hint else ""
        docstring = (
            f"Execute Python code by passing it in the `code` argument.\n"
            f"IMPORTANT: Combine ALL operations into a SINGLE code block — do NOT make separate calls.\n"
            f"Inside the code, the following functions are already available — do NOT import them:\n\n"
            f"{tools_listing}\n\n"
            f"{usage_hint}\n"
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

    def tool_schema(self, format: Literal["openai", "anthropic"] = "openai") -> dict[str, Any]:
        """Return a tool definition dict in the specified provider format.

        Args:
            format: 'openai' (default, most universal) or 'anthropic'
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
            f"{usage_hint}"
        )
        if self._error_hint:
            description += "\n" + self._error_hint

        code_desc = "Python code to execute. The listed functions are available as globals."

        if format == "anthropic":
            return {
                "name": "execute_tools",
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": code_desc,
                        }
                    },
                    "required": ["code"],
                },
            }

        # OpenAI format (default)
        return {
            "type": "function",
            "function": {
                "name": "execute_tools",
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": code_desc,
                        }
                    },
                    "required": ["code"],
                },
            },
        }

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
            **kwargs: Passed to Toolkit.__init__ (preamble, postamble, etc.).
        """
        from .mcp import tools_from_mcp  # lazy import

        mcp_tools = await tools_from_mcp(
            session,
            tool_names=tool_names,
            include_resources=include_resources,
            return_schemas=return_schemas,
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
    ) -> ExecutionResult:
        """Execute LLM-generated Python code with tools available.

        This is an async method. For sync usage, use ``execute_sync()``.

        Args:
            code: Python code string to execute
            timeout: Maximum execution time in seconds (None uses toolkit default)
            validate: Run AST validation before execution (default True)

        Returns:
            ExecutionResult with output, tool calls, and error info
        """
        effective_timeout = timeout if timeout is not None else self._timeout

        if validate:
            vr = validate_code(code, set(self._tool_map.keys()))
            if not vr.is_safe:
                return ExecutionResult(
                    success=False,
                    error="Validation failed: " + "; ".join(vr.errors),
                    error_output="Validation errors:\n" + "\n".join(f"- {e}" for e in vr.errors),
                )
            warning_prefix = ""
            if vr.warnings:
                warning_prefix = "Validation warnings:\n" + "\n".join(f"- {w}" for w in vr.warnings) + "\n"

        result = await self._sandbox.execute(code, self._tool_map, effective_timeout)

        if validate and vr.warnings:
            result.error_output = warning_prefix + result.error_output

        return result

    def execute_sync(
        self,
        code: str,
        timeout: float | None = None,
        validate: bool = True,
    ) -> ExecutionResult:
        """Execute LLM-generated Python code with tools available (sync version).

        Convenience wrapper around ``execute()`` for sync contexts.

        Args:
            code: Python code string to execute
            timeout: Maximum execution time in seconds (None uses toolkit default)
            validate: Run AST validation before execution (default True)

        Returns:
            ExecutionResult with output, tool calls, and error info
        """
        return _run_sync(self.execute(code, timeout, validate))
