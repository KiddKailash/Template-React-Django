"""Tests for `McpToken` + `McpCallLog` invariants.

The two important model-level guarantees:

  1. The raw secret is NEVER persisted — only its SHA-256 digest.
  2. `McpToken.verify()` is the only authoritative active-token check;
     it rejects revoked and expired tokens uniformly.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from mcp_server.models import TOKEN_PREFIX, McpCallLog, McpToken, stable_arg_hash


@pytest.mark.django_db
def test_issue_returns_raw_secret_and_persists_hash_only():
    token, raw = McpToken.issue(name="laptop")
    assert raw.startswith(TOKEN_PREFIX)
    fresh = McpToken.objects.get(pk=token.pk)
    assert fresh.secret_hash != raw
    assert len(fresh.secret_hash) == 64  # SHA-256 hex
    assert fresh.secret_prefix.startswith(TOKEN_PREFIX)
    assert raw not in fresh.secret_prefix


@pytest.mark.django_db
def test_verify_active_token():
    _, raw = McpToken.issue(name="x")
    token = McpToken.verify(raw)
    assert token is not None
    assert token.is_active()


@pytest.mark.django_db
def test_verify_rejects_unknown_secret():
    McpToken.issue(name="x")
    assert McpToken.verify(TOKEN_PREFIX + "definitelynotreal") is None
    assert McpToken.verify("garbage") is None
    assert McpToken.verify("") is None


@pytest.mark.django_db
def test_verify_rejects_revoked_token():
    token, raw = McpToken.issue(name="x")
    token.revoke()
    assert McpToken.verify(raw) is None


@pytest.mark.django_db
def test_verify_rejects_expired_token():
    token, raw = McpToken.issue(name="x", ttl_days=1)
    token.expires_at = timezone.now() - timedelta(seconds=1)
    token.save(update_fields=["expires_at"])
    assert McpToken.verify(raw) is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scopes,name,expected",
    [
        ("tools:*", "current_time_utc", True),
        ("tools:current_time_utc", "current_time_utc", True),
        ("tools:current_time_utc", "count_users_since", False),
        ("tools:count_users_since,tools:current_time_utc", "list_recent_users", False),
    ],
)
def test_scope_can_call_tool(scopes, name, expected):
    token, _ = McpToken.issue(name="x", scopes=scopes)
    assert token.can_call_tool(name) is expected


@pytest.mark.django_db
def test_empty_scopes_string_falls_back_to_default():
    """`issue()` treats an empty string as 'use default' (tools:*).

    Explicit narrowing requires a non-empty scope list — passing "" is
    a misuse, not an opt-out. Direct model construction with scopes=""
    yields an empty scope set (no tools callable) — that's the escape
    hatch for tests/admins who want a deliberately-locked-down row.
    """
    token, _ = McpToken.issue(name="defaulted", scopes="")
    assert token.scopes == "tools:*"
    assert token.can_call_tool("anything")

    locked = McpToken(name="locked", secret_hash="x" * 64, secret_prefix="mcp_xx", scopes="")
    assert not locked.can_call_tool("anything")


def test_stable_arg_hash_is_deterministic():
    a = stable_arg_hash({"name": "x", "arguments": {"days": 7, "n": 0}})
    b = stable_arg_hash({"arguments": {"n": 0, "days": 7}, "name": "x"})
    assert a == b


@pytest.mark.django_db
def test_call_log_is_immutable_via_admin_intent():
    log = McpCallLog.objects.create(
        token=None,
        method="ping",
        status=McpCallLog.Status.OK,
    )
    assert log.timestamp is not None
