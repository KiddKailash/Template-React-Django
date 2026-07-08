"""Privacy guards re-applied at the MCP boundary.

The read-only tool registry should be the primary place privacy
invariants live — a tool that must never emit a secret should strip
the secret before returning. These guards are belt-and-suspenders:
every tool result handed to an MCP client is walked one more time, and
any byte that matches a disallowed pattern aborts the call.

Why a second layer? The MCP surface is the only path where third-party
code sees the raw tool result without the in-app chat/agent
post-processing. A regression in a single tool that started leaking
sensitive fields would otherwise only surface in a later audit. With
this layer, the leak becomes a JSON-RPC error — visible to ops, denied
to the client.

Template default
================

The template ships an empty invariant set — `enforce()` is a no-op.
Add your own walkers here as you introduce sensitive fields. Example
scaffolds below (commented out) show the two common shapes:

  * disallowed keys anywhere in the result tree
  * disallowed substrings inside string values

Violations raise `PrivacyViolation`. The view catches it and returns a
generic JSON-RPC error to the client; the operator-facing log includes
the offending tool + key path.
"""

from __future__ import annotations

from typing import Any


class PrivacyViolation(Exception):  # noqa: N818 — name matches concept, not Python's "Error" convention
    """Raised when a tool result fails a privacy invariant.

    Carries the tool name and a path expression locating the offending
    field so the operator log can pinpoint the regression.
    """

    def __init__(self, tool: str, reason: str, path: str = "$") -> None:
        super().__init__(f"{tool} → {reason} at {path}")
        self.tool = tool
        self.reason = reason
        self.path = path


# ---------------------------------------------------------------------
# Configure your invariants here
# ---------------------------------------------------------------------

# Keys that must never appear anywhere in a tool result. Matches by
# exact key name, recursively through dicts and lists. Empty by default.
_DISALLOWED_KEYS: frozenset[str] = frozenset()

# Substrings that must never appear inside any string value. Empty by
# default. Useful for markers you deliberately embed in raw text stores
# that should never reach a tool response (e.g. `<raw_ocr>`).
_DISALLOWED_STRING_MARKERS: tuple[str, ...] = ()


def enforce(tool_name: str, result: Any) -> None:
    """Walk `result` and raise PrivacyViolation on any leak.

    Pure validator — does not modify the result. Callers should treat a
    raised exception as a fatal error for the call (return a JSON-RPC
    error, never the partial result).
    """
    if _DISALLOWED_KEYS:
        _walk_no_disallowed_keys(tool_name, result, "$")
    if _DISALLOWED_STRING_MARKERS:
        _walk_no_disallowed_markers(tool_name, result, "$")


def _walk_no_disallowed_keys(tool: str, node: Any, path: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _DISALLOWED_KEYS:
                raise PrivacyViolation(
                    tool,
                    reason=f"disallowed key {key!r}",
                    path=f"{path}.{key}",
                )
            _walk_no_disallowed_keys(tool, value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_no_disallowed_keys(tool, item, f"{path}[{i}]")


def _walk_no_disallowed_markers(tool: str, node: Any, path: str) -> None:
    if isinstance(node, str):
        for marker in _DISALLOWED_STRING_MARKERS:
            if marker in node:
                raise PrivacyViolation(
                    tool,
                    reason=f"disallowed marker {marker!r} in string value",
                    path=path,
                )
    elif isinstance(node, dict):
        for key, value in node.items():
            _walk_no_disallowed_markers(tool, value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_no_disallowed_markers(tool, item, f"{path}[{i}]")
