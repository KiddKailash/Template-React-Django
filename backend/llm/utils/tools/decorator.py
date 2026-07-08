"""`@read_only_tool` decorator and the global REGISTRY.

The decorator inspects the function's signature + annotations and
builds a JSON-schema fragment matching OpenRouter's tool-use contract.
Supported parameter types: `int`, `float`, `str`, `bool`,
`list[<primitive>]`. Default values become non-required parameters.

`requires_source` is an optional gate: when set, the tool is hidden
from the LLM unless the named source is currently connected. The
mapping from source name → connected? is provided by the caller via
`available_tools(connected_sources=...)`. This lets tools that depend
on external integrations (Stripe, Slack, Google Drive) drop out of the
tool list when the integration isn't wired up, instead of surfacing
runtime errors mid-loop.
"""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Union, get_args, get_origin, get_type_hints


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any]
    required: list[str] = field(default_factory=list)
    requires_source: str | None = None

    def openrouter_payload(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                    "additionalProperties": False,
                },
            },
        }


REGISTRY: dict[str, ToolSpec] = {}


_PY_TO_JSON = {
    int: {"type": "integer"},
    float: {"type": "number"},
    str: {"type": "string"},
    bool: {"type": "boolean"},
}


def _strip_optional(annotation: Any) -> Any:
    """For `X | None` / `Optional[X]`, return X. Tool args must be concrete."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _annotation_to_schema(annotation: Any, name: str, fn_name: str) -> dict[str, Any]:
    annotation = _strip_optional(annotation)
    if annotation in _PY_TO_JSON:
        return dict(_PY_TO_JSON[annotation])
    origin = get_origin(annotation)
    if origin is list:
        (inner,) = get_args(annotation) or (str,)
        inner = _strip_optional(inner)
        if inner not in _PY_TO_JSON:
            raise TypeError(
                f"tool {fn_name!r} param {name!r}: list item type {inner!r} not supported"
            )
        return {"type": "array", "items": dict(_PY_TO_JSON[inner])}
    raise TypeError(f"tool {fn_name!r} param {name!r}: annotation {annotation!r} not supported")


def read_only_tool(
    *, name: str, description: str, requires_source: str | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a read-only LLM tool."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not description.strip():
            raise ValueError(f"tool {name!r}: description is required")
        sig = inspect.signature(fn)
        try:
            hints = get_type_hints(fn)
        except NameError as exc:
            raise TypeError(f"tool {name!r}: unresolved annotation ({exc})") from exc
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                raise TypeError(f"tool {name!r}: *args/**kwargs not allowed")
            if param_name not in hints:
                raise TypeError(f"tool {name!r}: param {param_name!r} must be annotated")
            properties[param_name] = _annotation_to_schema(hints[param_name], param_name, name)
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        if name in REGISTRY:
            raise ValueError(f"tool {name!r} already registered")
        REGISTRY[name] = ToolSpec(
            name=name,
            description=description.strip(),
            handler=fn,
            parameters=properties,
            required=required,
            requires_source=requires_source,
        )
        return fn

    return deco


def available_tools(connected_sources: Iterable[str] | None = None) -> list[ToolSpec]:
    """Tool specs filtered by connected sources.

    Tools with `requires_source=<name>` are dropped from the result when
    `<name>` is not in `connected_sources`. Tools with no
    `requires_source` are always included.

    If `connected_sources` is None, no source-gating is applied — every
    registered tool is returned. Projects that use `requires_source`
    should pass their own connected-source set (e.g. read from the DB).
    """
    connected = set(connected_sources) if connected_sources is not None else None
    return [
        spec
        for spec in REGISTRY.values()
        if spec.requires_source is None or connected is None or spec.requires_source in connected
    ]
