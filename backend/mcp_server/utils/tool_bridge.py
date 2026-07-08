"""Bridge `llm.utils.tools.REGISTRY` → MCP tool schema + dispatch.

The MCP `tools/list` response and `tools/call` dispatcher both delegate
here. The single source of truth for what's read-only and safe to
expose is `llm.utils.tools.decorator.REGISTRY`, populated at import time
by the `@read_only_tool` decorator and validated at boot by the AST
walker (`llm.utils.tools.validator`).

Additional filtering layered on top:

  * `EXCLUDED_TOOLS` — tools that exist in the registry for in-process
    use but make no sense to a third-party MCP client. Empty by
    default; add sentinel/control-flow tools here (e.g. `remain_silent`
    in projects that use it).

  * Source-gated tools — `requires_source="..."` tools disappear when
    the underlying adapter isn't listed in the `connected_sources`
    iterable. In the template this is always empty; wire it up to your
    project's data-source registry once you have one.

  * Per-token scopes — if the holder's scope set doesn't include
    `tools:*` or `tools:<name>`, the tool is hidden.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from llm.utils.tools.decorator import REGISTRY, ToolSpec, available_tools

from ..models import McpToken

# Tools that exist in the registry but should never be exposed over MCP.
# Add here if you introduce control-flow sentinels (e.g. `remain_silent`).
EXCLUDED_TOOLS: frozenset[str] = frozenset()


def connected_sources() -> Iterable[str]:
    """Names of data sources that are currently connected.

    The template does not ship a data-source registry — override this
    function (or replace the call sites) once you have one. Returning
    an empty iterable means `requires_source=...` tools are always
    hidden; return `None` to disable source-gating entirely.
    """
    return ()


def list_visible_tools(token: McpToken) -> list[ToolSpec]:
    """Specs the given token may invoke right now.

    Combines:
      - `available_tools()` (source-gated, registry-membership)
      - token scope
      - the MCP exclusion list
    """
    return [
        spec
        for spec in available_tools(connected_sources=connected_sources())
        if spec.name not in EXCLUDED_TOOLS and token.can_call_tool(spec.name)
    ]


def find_callable_tool(token: McpToken, name: str) -> ToolSpec | None:
    """Return the spec for `name` iff the token may call it right now.

    Returns None for:
      - unknown tools
      - tools on the exclusion list
      - tools whose `requires_source` adapter isn't connected
      - tools not in the token's scope
    """
    if name in EXCLUDED_TOOLS:
        return None
    if name not in REGISTRY:
        return None
    if not token.can_call_tool(name):
        return None
    spec = REGISTRY[name]
    if spec.requires_source is not None:
        if spec.requires_source not in set(connected_sources()):
            return None
    return spec


def to_mcp_tool_schema(spec: ToolSpec) -> dict[str, Any]:
    """Serialise a `ToolSpec` into the MCP `tools/list` schema.

    MCP's `Tool` shape is `{name, description, inputSchema}` where
    `inputSchema` is a JSON Schema. Our `ToolSpec.parameters` is
    already JSON-Schema-shaped; we wrap it in the standard envelope.
    """
    return {
        "name": spec.name,
        "description": spec.description,
        "inputSchema": {
            "type": "object",
            "properties": spec.parameters,
            "required": spec.required,
            "additionalProperties": False,
        },
    }


def coerce_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Best-effort coerce MCP arguments to the handler's parameter types.

    JSON-RPC clients often send numbers as floats even when the schema
    says `integer`; some send `null` for unset parameters. The handler
    contract is "all parameters are provided", so we fill defaults for
    missing optional fields and coerce primitive types where lossless.

    Errors are raised as `ValueError` — the caller turns them into a
    JSON-RPC `invalid_params` response (-32602).
    """
    out: dict[str, Any] = {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")

    for param_name, schema in spec.parameters.items():
        if param_name in arguments:
            value = arguments[param_name]
        elif param_name in spec.required:
            raise ValueError(f"missing required parameter {param_name!r}")
        else:
            value = _default_for_schema(schema)
        out[param_name] = _coerce(value, schema, param_name)

    extras = set(arguments.keys()) - set(spec.parameters.keys())
    if extras:
        raise ValueError(f"unexpected parameter(s): {sorted(extras)}")
    return out


def _default_for_schema(schema: dict[str, Any]) -> Any:
    t = schema.get("type")
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "string":
        return ""
    if t == "boolean":
        return False
    if t == "array":
        return []
    return None


def _coerce(value: Any, schema: dict[str, Any], name: str) -> Any:
    t = schema.get("type")
    if value is None:
        return _default_for_schema(schema)
    if t == "integer":
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"parameter {name!r}: expected integer, got {value!r}") from exc
    if t == "number":
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"parameter {name!r}: expected number, got {value!r}") from exc
    if t == "string":
        if not isinstance(value, str):
            raise ValueError(f"parameter {name!r}: expected string, got {type(value).__name__}")
        return value
    if t == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"parameter {name!r}: expected boolean")
        return value
    if t == "array":
        if not isinstance(value, list):
            raise ValueError(f"parameter {name!r}: expected array")
        return value
    return value
