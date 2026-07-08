"""Boot-time tool-registry walk.

Runs from `llm.apps.LlmConfig.ready()`. Goals:

  1. Force-import the built-ins module so its `@read_only_tool` calls
     populate the REGISTRY before any LLM call can happen.
  2. Static-check every registered handler's source for obvious
     DB-write calls (`.save()`, `.delete()`, `.create(...)`,
     `.update(...)`, `.bulk_create(...)`, `.get_or_create(...)`).
     This is intentionally best-effort — a determined contributor can
     bypass it, but accidents fail boot loudly with file + line.

Boot-time enforcement is important because the LLM tool surface is a
privileged path: a write in a tool body would let the model mutate the
database. The AST check catches the obvious cases before deploy.
"""

from __future__ import annotations

import ast
import importlib
import inspect

from .decorator import REGISTRY, ToolSpec

WRITE_METHOD_NAMES = frozenset(
    {
        "save",
        "delete",
        "create",
        "update",
        "bulk_create",
        "bulk_update",
        "get_or_create",
        "update_or_create",
    }
)


class ToolValidationError(Exception):
    """Raised at boot when the tool registry contains an invalid tool."""


def _scan_writes(spec: ToolSpec) -> list[str]:
    """Return human-readable error strings for any DB-write call in `spec.handler`."""
    try:
        source = inspect.getsource(spec.handler)
    except (OSError, TypeError):
        return [f"tool {spec.name!r}: could not read source for static write-check"]
    try:
        tree = ast.parse(inspect.cleandoc(source))
    except SyntaxError as exc:
        return [f"tool {spec.name!r}: source unparseable: {exc}"]
    file = inspect.getsourcefile(spec.handler) or "<unknown>"
    base_line = spec.handler.__code__.co_firstlineno - 1
    errors: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in WRITE_METHOD_NAMES
        ):
            errors.append(
                f"tool {spec.name!r} ({file}:{base_line + node.lineno}) "
                f"calls .{node.func.attr}() — read-only tools may not write"
            )
    return errors


def validate_registry() -> None:
    """Force-load built-ins, then check every registered tool.

    Raises `ToolValidationError` listing every problem found — a single
    exception with a multi-line body so CI shows every issue in one
    log entry instead of one per boot attempt.
    """
    importlib.import_module("llm.utils.tools.builtin")

    errors: list[str] = []
    for spec in REGISTRY.values():
        if not spec.description:
            errors.append(f"tool {spec.name!r}: description is empty")
        errors.extend(_scan_writes(spec))

    if errors:
        raise ToolValidationError("tool registry validation failed:\n  - " + "\n  - ".join(errors))
