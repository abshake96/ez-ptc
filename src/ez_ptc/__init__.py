"""ez-ptc: Easy Programmatic Tool Calling.

A lightweight, framework-agnostic library for programmatic tool calling with any LLM.
"""

from importlib.metadata import version as _version

from .executor import ExecutionResult
from .sandbox import LocalSandbox, SandboxBackend
from .schema import function_to_schema
from .tool import Tool, ez_tool
from .toolkit import Toolkit
from .validator import ValidationResult, validate_code

__version__ = _version("ez-ptc")

__all__ = [
    "__version__",
    "ez_tool",
    "Tool",
    "Toolkit",
    "ExecutionResult",
    "function_to_schema",
    "ValidationResult",
    "validate_code",
    "SandboxBackend",
    "LocalSandbox",
]
