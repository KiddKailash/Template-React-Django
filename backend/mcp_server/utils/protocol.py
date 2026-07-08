"""MCP JSON-RPC 2.0 method handlers.

Implements the subset of the Model Context Protocol needed to expose
the read-only tool registry over Streamable HTTP. Each handler is a
pure function `(token, params) -> result`; the view layer is
responsible for transport, auth, audit logging, and rate limiting.

Methods implemented:

  * `initialize` — capability handshake. Returns server info and
    declares `tools.listChanged=false` (we don't push change
    notifications; clients refresh on reconnect).
  * `notifications/initialized` — client → server signal that the
    handshake is complete. No-op for us, but accepted so spec-
    compliant clients don't see an error.
  * `ping` — liveness check.
  * `tools/list` — enumerates the read-only tool surface visible to
    this token (source-gated, scope-filtered, MCP-excluded).
  * `tools/call` — dispatch a single tool. Privacy-validated. May
    return `isError=true` with a structured error message; only
    catastrophic failures bubble out as JSON-RPC errors.

Unknown methods raise `JsonRpcMethodNotFound`; bad parameters raise
`JsonRpcInvalidParams`. The view converts these to JSON-RPC envelope
errors with the canonical numeric codes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from llm.utils.tools.decorator import ToolSpec

from ..models import McpToken
from .privacy import PrivacyViolation, enforce
from .tool_bridge import (
    coerce_arguments,
    find_callable_tool,
    list_visible_tools,
    to_mcp_tool_schema,
)

logger = logging.getLogger(__name__)

# MCP protocol versions we accept. Clients advertise their version in
# the initialize handshake; we echo back the one we'd like to speak.
# 2025-03-26 is the Streamable HTTP version of the spec.
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-03-26", "2024-11-05")
SERVER_PROTOCOL_VERSION = "2025-03-26"

SERVER_INFO = {
    "name": "template-django-react-mcp",
    "version": "1.0.0",
}

# JSON-RPC 2.0 error codes (see https://www.jsonrpc.org/specification#error_object).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# Implementation-defined server error range: -32000 to -32099.
TOOL_DENIED_CODE = -32001
RATE_LIMITED_CODE = -32002
PRIVACY_VIOLATION_CODE = -32003
SERVICE_DISABLED_CODE = -32004


class JsonRpcError(Exception):
    """Base class for protocol-level errors that carry a JSON-RPC code."""

    code: int = INTERNAL_ERROR

    def __init__(self, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.data = data


# JSON-RPC's canonical names (MethodNotFound, InvalidParams) don't carry the
# "Error" suffix Ruff's N818 prefers; we keep the spec-canonical names so the
# class identifies its protocol meaning at a glance.
class JsonRpcMethodNotFound(JsonRpcError):  # noqa: N818
    code = METHOD_NOT_FOUND


class JsonRpcInvalidParams(JsonRpcError):  # noqa: N818
    code = INVALID_PARAMS


class JsonRpcServiceDisabled(JsonRpcError):  # noqa: N818
    code = SERVICE_DISABLED_CODE


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------


@dataclass
class DispatchOutcome:
    result: Any
    tool_name: str = ""  # only set for tools/call
    privacy_violation: PrivacyViolation | None = None


def dispatch(method: str, params: Any, token: McpToken) -> DispatchOutcome:
    """Route a JSON-RPC method to its handler.

    Returns a `DispatchOutcome` with the JSON-serialisable result. May
    raise `JsonRpcError` subclasses for protocol-level problems; the
    view turns those into JSON-RPC error responses.
    """
    if not getattr(settings, "MCP_ENABLED", True):
        raise JsonRpcServiceDisabled("MCP service is disabled on this instance.")

    if method == "initialize":
        return DispatchOutcome(result=_handle_initialize(params))

    if method == "notifications/initialized":
        return DispatchOutcome(result={})

    if method == "ping":
        return DispatchOutcome(result={})

    if method == "tools/list":
        return DispatchOutcome(result=_handle_tools_list(token, params))

    if method == "tools/call":
        return _handle_tools_call(token, params)

    raise JsonRpcMethodNotFound(f"method not found: {method!r}")


# ---------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------


def _handle_initialize(params: Any) -> dict[str, Any]:
    """Respond to the client's capability handshake.

    Per the MCP spec, we MUST echo back a `protocolVersion` we're
    willing to speak. If the client's version isn't in our supported
    list, we still return our preferred version and let the client
    decide whether to proceed — this matches the reference SDK.
    """
    if not isinstance(params, dict):
        params = {}
    client_version = params.get("protocolVersion")
    server_version = (
        client_version if client_version in SUPPORTED_PROTOCOL_VERSIONS else SERVER_PROTOCOL_VERSION
    )
    return {
        "protocolVersion": server_version,
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "serverInfo": SERVER_INFO,
        "instructions": (
            "Read-only access to the server's tool registry. All tools "
            "are AST-validated at boot to forbid database writes; every "
            "call is audited."
        ),
    }


def _handle_tools_list(token: McpToken, params: Any) -> dict[str, Any]:
    """Enumerate tools visible to this token. No pagination — the tool
    surface is small enough that everything fits in one response.
    """
    specs = list_visible_tools(token)
    return {
        "tools": [to_mcp_tool_schema(spec) for spec in specs],
    }


def _handle_tools_call(token: McpToken, params: Any) -> DispatchOutcome:
    """Dispatch a single tool call.

    Returns the MCP `CallToolResult` envelope:
      `{ content: [{type: "text", text: "<json>"}], isError: false }`

    Tool-level errors (bad arguments, source disconnected mid-call,
    privacy violation) are returned with `isError=true` so the client
    can show them to the user without aborting the session. JSON-RPC
    protocol-level errors (unknown method, missing params) still bubble
    out via raise.
    """
    if not isinstance(params, dict):
        raise JsonRpcInvalidParams("tools/call requires an object params field")
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise JsonRpcInvalidParams("tools/call requires a string `name` field")
    raw_arguments = params.get("arguments") or {}

    spec: ToolSpec | None = find_callable_tool(token, name)
    if spec is None:
        return _tool_error_outcome(
            tool_name=name,
            message=(
                f"tool {name!r} is not available — it may be unknown, "
                "out of scope for this token, or its data source is "
                "currently disconnected."
            ),
        )

    try:
        kwargs = coerce_arguments(spec, raw_arguments)
    except ValueError as exc:
        return _tool_error_outcome(tool_name=name, message=str(exc))

    try:
        result = spec.handler(**kwargs)
    except Exception as exc:  # noqa: BLE001 — fence handler errors
        logger.exception("mcp.tool_handler_failed", extra={"tool": name})
        return _tool_error_outcome(
            tool_name=name,
            message=f"tool handler raised: {type(exc).__name__}",
        )

    # Privacy gate — belt-and-suspenders. See utils/privacy.py.
    try:
        enforce(name, result)
    except PrivacyViolation as exc:
        logger.error(
            "mcp.privacy_violation",
            extra={"tool": name, "reason": exc.reason, "path": exc.path},
        )
        return DispatchOutcome(
            result=_call_envelope(
                text=json.dumps(
                    {
                        "error": "privacy_violation",
                        "message": "tool result rejected by server-side privacy filter",
                    }
                ),
                is_error=True,
            ),
            tool_name=name,
            privacy_violation=exc,
        )

    return DispatchOutcome(
        result=_call_envelope(text=json.dumps(result, default=str), is_error=False),
        tool_name=name,
    )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _tool_error_outcome(*, tool_name: str, message: str) -> DispatchOutcome:
    return DispatchOutcome(
        result=_call_envelope(
            text=json.dumps({"error": "tool_unavailable_or_invalid", "message": message}),
            is_error=True,
        ),
        tool_name=tool_name,
    )


def _call_envelope(*, text: str, is_error: bool) -> dict[str, Any]:
    """MCP `CallToolResult` envelope.

    The tool result is serialised as a single text-content block. We
    use JSON so the client can re-parse a structured response; a future
    enhancement could emit MCP `embeddedResource` for richer media, but
    text-with-JSON is universally understood.
    """
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
