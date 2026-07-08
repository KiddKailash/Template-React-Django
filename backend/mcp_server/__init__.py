"""MCP server: expose the read-only tool registry over the Model Context Protocol.

Sits alongside `chat/` and `llm/` — same underlying tool registry, but
served over JSON-RPC 2.0 to external MCP clients (Claude Desktop,
scripts, future SDK consumers). Bearer-token authenticated; every call
writes an append-only audit row.
"""
