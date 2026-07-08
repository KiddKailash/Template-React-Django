"""Project-wide pytest fixtures.

Lives at the backend root so every test module — under core/tests/ or
anywhere else — automatically sees these fixtures without explicit import.

Add app-specific fixtures under `core/tests/conftest.py` (or per-app).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Environment hardening — opt-in fixture for tests that explicitly want a
# scrubbed environment. NOT autouse: a global scrub regresses any existing
# test that implicitly depended on a developer's local env vars.
# ---------------------------------------------------------------------------


@pytest.fixture
def scrub_external_env(monkeypatch):
    """Clear API keys for this test. Use when testing missing-credential paths."""
    for key in (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "CHROMA_TENANT",
        "CHROMA_DATABASE",
        "CHROMA_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Users + auth
# ---------------------------------------------------------------------------


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="test@example.com",
    )


@pytest.fixture
def other_user(db) -> User:
    """A second user for cross-user isolation tests."""
    return User.objects.create_user(
        username="otheruser",
        password="otherpass123",
        email="other@example.com",
    )


@pytest.fixture
def admin_user(db) -> User:
    return User.objects.create_superuser(
        username="admin",
        password="adminpass123",
        email="admin@example.com",
    )


@pytest.fixture
def api_client() -> APIClient:
    """Unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user) -> APIClient:
    """APIClient authenticated as `user` via force_authenticate (skips JWT)."""
    api_client.force_authenticate(user=user)
    return api_client


# ---------------------------------------------------------------------------
# Time travel — for tests that depend on now()
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_now(monkeypatch):
    """Pin django.utils.timezone.now() to a deterministic value.

    Returns the pinned datetime so tests can compute offsets:
        frozen_now + timedelta(days=1)
    """
    fixed = timezone.now().replace(microsecond=0)
    monkeypatch.setattr("django.utils.timezone.now", lambda: fixed)
    return fixed
