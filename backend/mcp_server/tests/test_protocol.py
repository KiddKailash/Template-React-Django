"""Tests for the MCP JSON-RPC protocol layer.

Coverage:
  - Auth rejection (missing/invalid/revoked)
  - Initialize handshake echoes a compatible protocol version
  - Ping liveness
  - tools/list filters by scope
  - tools/call dispatches and returns the MCP envelope
  - tools/call rejects unknown / out-of-scope tools with isError
  - Batch requests
  - Notifications return 202 with no body
  - Kill switch (MCP_ENABLED=False) returns 503
"""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_missing_auth_returns_401(mcp_client):
    resp = mcp_client(None, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status == 401


@pytest.mark.django_db
def test_invalid_token_returns_401(mcp_client):
    resp = mcp_client("mcp_definitelynotreal", {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status == 401


@pytest.mark.django_db
def test_revoked_token_returns_401(mcp_client, issued_token):
    token, raw = issued_token
    token.revoke()
    resp = mcp_client(raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status == 401


@pytest.mark.django_db
def test_initialize_handshake(mcp_client, issued_token):
    _, raw = issued_token
    resp = mcp_client(
        raw,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "clientInfo": {"name": "pytest"}},
        },
    )
    assert resp.status == 200
    result = resp.result()
    assert result["protocolVersion"] == "2025-03-26"
    assert result["serverInfo"]["name"] == "template-django-react-mcp"
    assert "tools" in result["capabilities"]


@pytest.mark.django_db
def test_initialize_negotiates_to_server_version_for_unknown_client(mcp_client, issued_token):
    _, raw = issued_token
    resp = mcp_client(
        raw,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "1999-01-01"},
        },
    )
    # We echo OUR preferred version; client decides whether to proceed.
    assert resp.result()["protocolVersion"] == "2025-03-26"


@pytest.mark.django_db
def test_ping(initialized):
    post, raw = initialized
    resp = post(raw, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert resp.status == 200
    assert resp.result() == {}


@pytest.mark.django_db
def test_notifications_initialized_returns_202(mcp_client, issued_token):
    _, raw = issued_token
    resp = mcp_client(raw, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    # No `id` → notification → 202 Accepted, no body
    assert resp.status == 202
    assert resp.body == {}


@pytest.mark.django_db
def test_method_not_found(initialized):
    post, raw = initialized
    resp = post(raw, {"jsonrpc": "2.0", "id": 3, "method": "no/such/method"})
    assert resp.status == 200  # JSON-RPC errors come back in the envelope
    assert resp.error()["code"] == -32601


@pytest.mark.django_db
def test_tools_list_includes_builtin_tools(initialized):
    """The three template built-in tools are unsourced and should be visible."""
    post, raw = initialized
    resp = post(raw, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    names = {t["name"] for t in resp.result()["tools"]}
    assert "current_time_utc" in names
    assert "count_users_since" in names
    assert "list_recent_users" in names


@pytest.mark.django_db
def test_tools_list_filters_by_scope(mcp_client, restricted_scope_token):
    _, raw = restricted_scope_token
    resp = mcp_client(raw, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp.result()["tools"]}
    # Token has only `tools:current_time_utc`.
    assert names == {"current_time_utc"}


@pytest.mark.django_db
def test_tools_call_unknown_returns_is_error(initialized):
    post, raw = initialized
    resp = post(
        raw,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}},
        },
    )
    result = resp.result()
    assert result["isError"] is True


@pytest.mark.django_db
def test_tools_call_out_of_scope_returns_is_error(mcp_client, restricted_scope_token):
    _, raw = restricted_scope_token
    resp = mcp_client(
        raw,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "count_users_since", "arguments": {"days": 7}},
        },
    )
    assert resp.result()["isError"] is True


@pytest.mark.django_db
def test_tools_call_dispatches_current_time(initialized):
    post, raw = initialized
    resp = post(
        raw,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "current_time_utc", "arguments": {}},
        },
    )
    result = resp.result()
    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"


@pytest.mark.django_db
def test_tools_call_bad_arguments_returns_is_error(initialized):
    post, raw = initialized
    resp = post(
        raw,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "count_users_since", "arguments": {"unknown_field": 1}},
        },
    )
    assert resp.result()["isError"] is True


@pytest.mark.django_db
def test_batch_request(initialized):
    post, raw = initialized
    resp = post(
        raw,
        [
            {"jsonrpc": "2.0", "id": "a", "method": "ping"},
            {"jsonrpc": "2.0", "id": "b", "method": "tools/list"},
        ],
    )
    assert resp.status == 200
    assert isinstance(resp.body, list)
    assert len(resp.body) == 2
    ids = {r["id"] for r in resp.body}
    assert ids == {"a", "b"}


@pytest.mark.django_db
def test_batch_drops_notifications(initialized):
    post, raw = initialized
    resp = post(
        raw,
        [
            {"jsonrpc": "2.0", "id": "a", "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ],
    )
    assert resp.status == 200
    assert isinstance(resp.body, list)
    assert len(resp.body) == 1
    assert resp.body[0]["id"] == "a"


@pytest.mark.django_db
def test_kill_switch_returns_503(mcp_client, issued_token, settings):
    settings.MCP_ENABLED = False
    _, raw = issued_token
    resp = mcp_client(raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status == 503


@pytest.mark.django_db
def test_parse_error_returns_400(mcp_client, issued_token):
    _, raw = issued_token
    from django.test import Client

    client = Client()
    resp = client.post(
        "/api/mcp/",
        data="{not valid json",
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_audit_log_written_for_each_call(initialized):
    from mcp_server.models import McpCallLog

    post, raw = initialized
    pre = McpCallLog.objects.count()
    post(raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    post(raw, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert McpCallLog.objects.count() == pre + 2


@pytest.mark.django_db
def test_failed_auth_writes_audit_row(mcp_client):
    from mcp_server.models import McpCallLog

    pre = McpCallLog.objects.filter(status=McpCallLog.Status.AUTH_FAILED).count()
    mcp_client("mcp_definitelynotreal", {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    post = McpCallLog.objects.filter(status=McpCallLog.Status.AUTH_FAILED).count()
    assert post == pre + 1
