"""App config for the MCP server surface.

Exposes the read-only tool registry (`llm.utils.tools`) over the Model
Context Protocol. All served tools go through the same audited paths
the in-process chat/agent loops use:

  - Handlers pulled from `llm.utils.tools.decorator.REGISTRY`, which the
    boot-time AST validator has already proven read-only.
  - Tool visibility filtered by `available_tools()` — source-gated
    tools disappear when the underlying adapter is disconnected.
  - Every tool result is walked one more time by `mcp_server.utils.privacy`
    before it leaves the process. The template ships a no-op walker;
    add your own invariants if you have data that must never leave a
    tool response (secrets, PII, restricted rows, etc.).
"""

from __future__ import annotations

from django.apps import AppConfig


class McpServerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mcp_server"
    verbose_name = "MCP Server"
