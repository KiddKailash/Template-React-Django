"""Sliding-window rate limit verification.

We don't sleep one minute in the test — instead we configure a very
small per-minute cap (3) and fire that many requests in a tight loop;
the next request must be rejected with HTTP 429.

The rate-limit window is computed from `McpCallLog`, which is the
shared source of truth across workers — so the test exercises the
real production path.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from mcp_server.models import McpCallLog, McpToken


@pytest.mark.django_db
def test_rate_limit_blocks_after_quota(mcp_client):
    _, raw = McpToken.issue(name="lim", rate_limit_per_minute=3)

    def ping():
        return mcp_client(raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"})

    for _ in range(3):
        assert ping().status == 200
    assert ping().status == 429


@pytest.mark.django_db
def test_rate_limit_zero_means_unlimited(mcp_client):
    _, raw = McpToken.issue(name="unl", rate_limit_per_minute=0)
    for _ in range(20):
        assert mcp_client(raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status == 200


@pytest.mark.django_db
def test_rate_limit_window_is_one_minute(mcp_client):
    """Old calls (> 60s ago) don't count toward the window."""
    token, raw = McpToken.issue(name="win", rate_limit_per_minute=2)

    old = timezone.now() - timedelta(minutes=2)
    for _ in range(2):
        log = McpCallLog.objects.create(token=token, method="ping", status=McpCallLog.Status.OK)
        McpCallLog.objects.filter(pk=log.pk).update(timestamp=old)

    assert mcp_client(raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status == 200
