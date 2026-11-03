"""End-to-end sign-in, refresh, sign-out and revocation, with real JWTs.

Ported from LLMStockAnalysis (push-notification cases dropped).

Coverage:
  sign in (POST /api/token/)
    ├── opens a DeviceSession with user agent, IP and expiry; sid in both tokens
    ├── each sign-in is its own session
    ├── bad credentials → 401, no session
    ├── sweeps the user's sessions that ended over RETENTION ago
    └── is rate limited per IP (the `auth` throttle)

  authenticated requests
    ├── a token of a live session works and touches last_seen_at (coalesced)
    ├── token without sid → 401
    ├── token of a revoked session → 401 immediately (access not yet expired)
    ├── token of an expired session → 401
    └── token whose sid belongs to another user → 401

  refresh (POST /api/token/refresh/)
    ├── live session → new pair, still bound to the same session, expiry extended
    ├── revoked session → 401
    ├── token without sid → 401
    └── garbage token → 401

  sign out (POST /api/auth/logout/)
    ├── ends the caller's session; its tokens stop working
    └── leaves the user's other sessions alone
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import DeviceSession

# Passwords of the ``user`` / ``other_user`` fixtures in conftest.py.
PASSWORDS = {"testuser": "testpass123", "otheruser": "otherpass123"}
UA_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


def sign_in(client: APIClient, user, password: str | None = None, **headers) -> dict:
    res = client.post(
        reverse("token_obtain_pair"),
        {"username": user.username, "password": password or PASSWORDS[user.username]},
        format="json",
        **headers,
    )
    assert res.status_code == 200, res.content
    return res.json()


def bearer(access: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def get_me(client):
    return client.get(reverse("me"))


@pytest.mark.django_db
class TestSignIn:
    def test_opens_a_session_bound_into_both_tokens(self, api_client, user):
        tokens = sign_in(
            api_client, user, HTTP_USER_AGENT=UA_IPHONE, HTTP_CF_CONNECTING_IP="203.0.113.7"
        )

        session = DeviceSession.objects.get(user=user)
        assert session.user_agent == UA_IPHONE
        assert session.ip_address == "203.0.113.7"
        assert session.is_live
        assert session.expires_at > timezone.now() + timedelta(days=13)
        assert RefreshToken(tokens["refresh"])["sid"] == str(session.pk)
        assert AccessToken(tokens["access"])["sid"] == str(session.pk)

    def test_each_sign_in_is_its_own_session(self, api_client, user):
        sign_in(api_client, user)
        sign_in(api_client, user)
        assert DeviceSession.objects.filter(user=user).count() == 2

    def test_bad_credentials(self, api_client, user):
        res = api_client.post(
            reverse("token_obtain_pair"),
            {"username": user.username, "password": "wrong"},
            format="json",
        )
        assert res.status_code == 401
        assert not DeviceSession.objects.exists()

    def test_sweeps_long_dead_sessions(self, api_client, user, other_user):
        long_ago = timezone.now() - DeviceSession.RETENTION - timedelta(days=1)
        ended = DeviceSession.start(user)
        DeviceSession.objects.filter(pk=ended.pk).update(revoked_at=long_ago)
        expired = DeviceSession.start(user)
        DeviceSession.objects.filter(pk=expired.pk).update(expires_at=long_ago)
        recently_ended = DeviceSession.start(user)
        DeviceSession.objects.filter(pk=recently_ended.pk).update(revoked_at=timezone.now())
        theirs = DeviceSession.start(other_user)
        DeviceSession.objects.filter(pk=theirs.pk).update(revoked_at=long_ago)

        sign_in(api_client, user)

        remaining = set(DeviceSession.objects.values_list("pk", flat=True))
        assert ended.pk not in remaining and expired.pk not in remaining
        assert recently_ended.pk in remaining
        assert theirs.pk in remaining  # only the signing-in user's rows

    def test_rate_limited_per_ip(self, api_client, user, monkeypatch):
        from accounts.throttling import AuthRateThrottle

        # DRF reads THROTTLE_RATES off the class; shrink the budget to 3.
        monkeypatch.setattr(
            AuthRateThrottle,
            "THROTTLE_RATES",
            {**AuthRateThrottle.THROTTLE_RATES, "auth": "3/hour"},
        )
        for _ in range(3):
            sign_in(api_client, user)
        res = api_client.post(
            reverse("token_obtain_pair"),
            {"username": user.username, "password": "testpass123"},
            format="json",
        )
        assert res.status_code == 429


@pytest.mark.django_db
class TestAuthenticatedRequests:
    def test_live_session_works_and_is_touched(self, api_client, user):
        tokens = sign_in(api_client, user)
        session = DeviceSession.objects.get(user=user)
        old = timezone.now() - DeviceSession.TOUCH_INTERVAL - timedelta(minutes=1)
        DeviceSession.objects.filter(pk=session.pk).update(last_seen_at=old)

        assert get_me(bearer(tokens["access"])).status_code == 200
        session.refresh_from_db()
        assert session.last_seen_at > old

    def test_touch_is_coalesced(self, api_client, user):
        tokens = sign_in(api_client, user)
        session = DeviceSession.objects.get(user=user)
        recent = timezone.now() - timedelta(minutes=1)
        DeviceSession.objects.filter(pk=session.pk).update(last_seen_at=recent)

        get_me(bearer(tokens["access"]))
        session.refresh_from_db()
        assert session.last_seen_at == recent

    def test_token_without_session_is_refused(self, user):
        legacy = RefreshToken.for_user(user).access_token
        assert get_me(bearer(str(legacy))).status_code == 401

    def test_revoked_session_is_refused_immediately(self, api_client, user):
        tokens = sign_in(api_client, user)
        client = bearer(tokens["access"])
        assert get_me(client).status_code == 200

        DeviceSession.objects.filter(user=user).revoke()

        assert get_me(client).status_code == 401

    def test_expired_session_is_refused(self, api_client, user):
        tokens = sign_in(api_client, user)
        DeviceSession.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert get_me(bearer(tokens["access"])).status_code == 401

    def test_sid_of_another_users_session_is_refused(self, user, other_user):
        theirs = DeviceSession.start(other_user)
        forged = RefreshToken.for_user(user)
        forged["sid"] = str(theirs.pk)
        assert get_me(bearer(str(forged.access_token))).status_code == 401


@pytest.mark.django_db
class TestRefresh:
    def _refresh(self, refresh: str):
        return APIClient().post(reverse("token_refresh"), {"refresh": refresh}, format="json")

    def test_live_session_refreshes_and_extends(self, api_client, user):
        tokens = sign_in(api_client, user)
        session = DeviceSession.objects.get(user=user)
        soon = timezone.now() + timedelta(days=1)
        DeviceSession.objects.filter(pk=session.pk).update(expires_at=soon)

        res = self._refresh(tokens["refresh"])

        assert res.status_code == 200
        body = res.json()
        assert AccessToken(body["access"])["sid"] == str(session.pk)
        assert RefreshToken(body["refresh"])["sid"] == str(session.pk)
        session.refresh_from_db()
        assert session.expires_at > soon + timedelta(days=12)
        assert get_me(bearer(body["access"])).status_code == 200

    def test_revoked_session_cannot_refresh(self, api_client, user):
        tokens = sign_in(api_client, user)
        DeviceSession.objects.filter(user=user).revoke()
        assert self._refresh(tokens["refresh"]).status_code == 401

    def test_token_without_session_cannot_refresh(self, user):
        assert self._refresh(str(RefreshToken.for_user(user))).status_code == 401

    def test_garbage_token(self):
        assert self._refresh("not-a-token").status_code == 401


@pytest.mark.django_db
class TestLogout:
    def test_ends_the_callers_session_only(self, api_client, user):
        here = sign_in(api_client, user)
        there = sign_in(api_client, user)
        client = bearer(here["access"])

        assert client.post(reverse("logout")).status_code == 204

        assert get_me(client).status_code == 401
        assert get_me(bearer(there["access"])).status_code == 200
        assert DeviceSession.objects.live().filter(user=user).count() == 1
