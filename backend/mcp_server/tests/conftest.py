"""Fixtures shared across mcp_server tests.

Notable choices:

  - `mcp_client` builds raw POST requests against `/api/mcp/` with the
    bearer token. We don't use DRF's `APIClient` because the MCP
    endpoint is a plain Django view (csrf_exempt, bearer auth) — using
    a regular `Client` keeps the test surface honest about what an
    external client actually sends.

  - `issued_token` returns `(McpToken, raw_secret)` so tests can both
    inspect the row and authenticate as the holder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from django.test import Client


@pytest.fixture
def issued_token(db):
    """A fresh, active MCP token with `tools:*` scope and 60/min rate."""
    from mcp_server.models import McpToken

    token, raw = McpToken.issue(name="pytest", rate_limit_per_minute=60)
    return token, raw


@pytest.fixture
def restricted_scope_token(db):
    """An MCP token scoped to a single tool — used for scope-filter tests."""
    from mcp_server.models import McpToken

    token, raw = McpToken.issue(
        name="restricted",
        scopes="tools:current_time_utc",
        rate_limit_per_minute=60,
    )
    return token, raw


@dataclass
class McpResponse:
    status: int
    body: dict | list

    def result(self):
        assert isinstance(self.body, dict)
        return self.body.get("result")

    def error(self):
        assert isinstance(self.body, dict)
        return self.body.get("error")


@pytest.fixture
def mcp_client():
    """Returns a callable: `post(token_secret, payload) -> McpResponse`."""

    client = Client()

    def post(secret: str | None, payload: dict | list, *, ua: str = "pytest"):
        headers = {"HTTP_USER_AGENT": ua}
        if secret is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {secret}"
        resp = client.post(
            "/api/mcp/",
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )
        body = {} if resp.status_code == 202 else resp.json()
        return McpResponse(status=resp.status_code, body=body)

    return post


@pytest.fixture
def initialized(mcp_client, issued_token):
    """Performs the MCP initialize handshake; returns (post, raw_secret)."""
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
    assert resp.status == 200, resp.body
    return mcp_client, raw
