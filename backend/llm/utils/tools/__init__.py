"""LLM-callable tool registry.

Tools are **read-only** data accessors the LLM may call mid-turn to
fetch specific slices of context on demand. Each tool is registered via
`@read_only_tool`, which:

  - Records the tool in `REGISTRY` under a stable name.
  - Derives a JSON schema from the Python signature + annotations.
  - Bundles a description (LLM-facing) and handler (server-side).

The registry is walked at boot by `llm.apps.LlmConfig.ready()` via
`validate_registry()`, which:

  - Force-imports the built-in tools module so decorators run.
  - Asserts every tool has a non-empty description.
  - Asserts the handler body contains no obvious DB-write calls
    (`.save` / `.delete` / `.create` / `.update` — best-effort AST check).

Tool execution happens in `llm.utils.tool_loop.chat_with_tools` when
the model emits a tool call; the dispatcher reads the JSON args, calls
`REGISTRY[name].handler(**args)`, and returns the result as a tool
message. The turn count is capped at `LLM_MAX_TOOL_TURNS`.
"""

from __future__ import annotations

from .decorator import REGISTRY, ToolSpec, available_tools, read_only_tool
from .validator import ToolValidationError, validate_registry

__all__ = [
    "REGISTRY",
    "ToolSpec",
    "ToolValidationError",
    "available_tools",
    "read_only_tool",
    "validate_registry",
]
