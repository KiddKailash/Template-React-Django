"""Privacy filter sanity checks.

The template ships with the walkers disabled (`_DISALLOWED_KEYS` and
`_DISALLOWED_STRING_MARKERS` are empty). These tests exercise the
walker mechanics directly by monkeypatching those tuples so downstream
projects that enable invariants have a working scaffold to follow.
"""

from __future__ import annotations

import pytest

from mcp_server.utils import privacy


def test_enforce_is_noop_by_default():
    # Anything at all should pass — no invariants enabled.
    privacy.enforce("some_tool", {"anything": "goes", "including": ["nested", {"stuff": True}]})


def test_disallowed_key_raises(monkeypatch):
    monkeypatch.setattr(privacy, "_DISALLOWED_KEYS", frozenset({"secret"}))
    with pytest.raises(privacy.PrivacyViolation) as exc:
        privacy.enforce("t", {"a": {"b": [{"secret": "sh"}]}})
    assert "secret" in exc.value.reason
    assert exc.value.path.endswith(".secret")


def test_disallowed_marker_in_string_raises(monkeypatch):
    monkeypatch.setattr(privacy, "_DISALLOWED_STRING_MARKERS", ("__CANARY__",))
    with pytest.raises(privacy.PrivacyViolation):
        privacy.enforce("t", {"payload": "prefix __CANARY__ suffix"})


def test_walkers_traverse_lists(monkeypatch):
    monkeypatch.setattr(privacy, "_DISALLOWED_KEYS", frozenset({"leak"}))
    with pytest.raises(privacy.PrivacyViolation) as exc:
        privacy.enforce("t", [{"ok": 1}, {"ok": 2}, {"leak": 3}])
    assert "[2].leak" in exc.value.path
