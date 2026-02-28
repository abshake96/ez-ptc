"""Toolkit class — groups tools and provides prompt/tool mode interfaces."""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Literal

from .executor import ExecutionResult, execute_code
from .schema import format_return_schema
from .tool import Tool


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
            "Call all the tools you need and print() all results in a single code block.\n"
        )
        lines.append(
            "CAUTION: Do NOT assume the structure or key names of tool return values — print() raw results directly instead of accessing specific keys."
        )
    lines += [
        "For parallel execution, use asyncio:",
        "    async def main():",
        "        a, b = await asyncio.gather(asyncio.to_thread(tool1, ...), asyncio.to_thread(tool2, ...))",
        "        print(a, b)",
        "    asyncio.run(main())",
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

    def __init__(
        self,
        tools: list[Tool],
        preamble: str | None = None,
        postamble: str | None = None,
        assist_tool_chaining: bool = False,
    ) -> None:
        for item in tools:
            if not isinstance(item, Tool):
                raise TypeError(
                    f"Expected Tool instance, got {type(item).__name__}. Did you forget @ez_tool?"
                )
        self.tools = tools
        self._tool_map = {t.name: t for t in tools}
        self._custom_preamble = preamble
        self._custom_postamble = postamble
        self._assist_tool_chaining = assist_tool_chaining

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
    def _postamble(self) -> str:
        if self._custom_postamble is not None:
            return self._custom_postamble
        return _build_postamble(self._assist_tool_chaining)

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
                "Call all the tools you need and print() all results in a single code block.\n"
            )
            parts.append(
                "CAUTION: Do NOT assume the structure or key names of tool return values — print() raw results directly instead of accessing specific keys."
            )
        parts.append("For parallel execution, use asyncio.gather with asyncio.to_thread.")
        parts.append(
            "json, math, re, asyncio are pre-imported. You can also import other safe stdlib modules "
            "(collections, datetime, itertools, etc.)."
        )
        parts.append(
            "No file I/O, networking, or shell access (os, subprocess, socket, etc. are blocked)."
        )
        parts.append("ALWAYS print() the final result you want to return.")
        return "\n".join(parts)

    def as_tool(self) -> Callable[[str], str]:
        """Return a callable function that any framework can register as a tool.

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
                "    Call all the tools you need and print() all results in a single code block.\n"
                "    CAUTION: Do NOT assume the structure or key names of tool return values — print() raw results directly."
            )

        docstring = (
            f"Execute Python code by passing it in the `code` argument.\n"
            f"IMPORTANT: Combine ALL operations into a SINGLE code block — do NOT make separate calls.\n"
            f"Inside the code, the following functions are already available — do NOT import them:\n\n"
            f"{tools_listing}\n\n"
            f"{usage_hint}\n"
            f"    ALWAYS print() the final result.\n\n"
            f"    Args:\n"
            f"        code: Python code to execute"
        )

        toolkit_ref = self

        def execute_tools(code: str) -> str:
            result = toolkit_ref.execute(code)
            return result.to_string()

        execute_tools.__name__ = "execute_tools"
        execute_tools.__qualname__ = "execute_tools"
        execute_tools.__doc__ = docstring
        execute_tools.__annotations__ = {"code": str, "return": str}

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
                "Call all the tools you need and print() all results in a single code block.\n"
                "CAUTION: Do NOT assume the structure or key names of tool return values — print() raw results directly."
            )

        description = (
            f"Execute Python code via the `code` argument. "
            f"Available functions inside the code (already available — do NOT import them):\n{tools_desc}\n\n"
            f"IMPORTANT: Combine ALL operations into a SINGLE code block — do NOT make multiple separate calls.\n"
            f"{usage_hint}"
        )

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

    # ── Shared ────────────────────────────────────────────────────────

    def execute(self, code: str, timeout: float = 30.0) -> ExecutionResult:
        """Execute LLM-generated Python code with tools available.

        Args:
            code: Python code string to execute
            timeout: Maximum execution time in seconds

        Returns:
            ExecutionResult with output, tool calls, and error info
        """
        return execute_code(code, self._tool_map, timeout=timeout)
