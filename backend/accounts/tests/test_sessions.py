"""Tests for the device-session list, revocation and password change.

Ported from LLMStockAnalysis (push-notification cases dropped); password change
is new here.

Coverage:
  GET /api/sessions/
    ├── lists live sessions only, current first, flagged current
    ├── device described from the user agent
    ├── never lists another user's sessions
    └── requires authentication

  DELETE /api/sessions/<id>/
    ├── ends that session (its tokens stop working)
    ├── 404 for another user's session, and it stays live
    └── 404 for an already-ended session

  POST /api/sessions/revoke-others/
    ├── ends every session but the caller's; returns the count
    └── without a current session (force_authenticate) ends them all

  POST /api/auth/password/
    ├── wrong current password → 400, nothing changes
    ├── weak new password → 400 (Django's validators)
    └── success: new password works, this device stays, the others are signed out
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import DeviceSession
from accounts.tests.test_auth_flow import UA_IPHONE, bearer, get_me, sign_in

UA_MAC_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def _sid(tokens) -> str:
    return AccessToken(tokens["access"])["sid"]


@pytest.mark.django_db
class TestSessionList:
    def test_lists_live_sessions_current_first(self, api_client, user, other_user):
        phone = sign_in(api_client, user, HTTP_USER_AGENT=UA_IPHONE)
        laptop = sign_in(api_client, user, HTTP_USER_AGENT=UA_MAC_CHROME)
        ended = sign_in(api_client, user)
        DeviceSession.objects.filter(pk=_sid(ended)).revoke()
        sign_in(api_client, other_user)

        res = bearer(phone["access"]).get(reverse("session_list"))

        assert res.status_code == 200
        sessions = res.json()["sessions"]
        assert [s["id"] for s in sessions] == [_sid(phone), _sid(laptop)]
        assert [s["current"] for s in sessions] == [True, False]
        assert sessions[0]["device"] == {
            "browser": "Safari",
            "os": "iPhone",
            "kind": "mobile",
            "label": "Safari on iPhone",
        }
        assert sessions[1]["device"]["label"] == "Chrome on macOS"

    def test_requires_auth(self, api_client):
        assert api_client.get(reverse("session_list")).status_code == 401


@pytest.mark.django_db
class TestRevokeOne:
    def test_signs_that_device_out(self, api_client, user):
        here = sign_in(api_client, user)
        there = sign_in(api_client, user)

        res = bearer(here["access"]).delete(reverse("session_detail", args=[_sid(there)]))

        assert res.status_code == 204
        assert get_me(bearer(there["access"])).status_code == 401
        assert get_me(bearer(here["access"])).status_code == 200

    def test_another_users_session_is_404_and_untouched(self, api_client, user, other_user):
        mine = sign_in(api_client, user)
        theirs = sign_in(api_client, other_user)

        res = bearer(mine["access"]).delete(reverse("session_detail", args=[_sid(theirs)]))

        assert res.status_code == 404
        assert get_me(bearer(theirs["access"])).status_code == 200

    def test_already_ended_is_404(self, api_client, user):
        here = sign_in(api_client, user)
        there = sign_in(api_client, user)
        DeviceSession.objects.filter(pk=_sid(there)).revoke()

        res = bearer(here["access"]).delete(reverse("session_detail", args=[_sid(there)]))
        assert res.status_code == 404


@pytest.mark.django_db
class TestRevokeOthers:
    def test_ends_all_but_the_callers(self, api_client, user, other_user):
        here = sign_in(api_client, user)
        others = [sign_in(api_client, user) for _ in range(3)]
        theirs = sign_in(api_client, other_user)

        res = bearer(here["access"]).post(reverse("session_revoke_others"))

        assert res.json() == {"revoked": 3}
        assert get_me(bearer(here["access"])).status_code == 200
        for tokens in others:
            assert get_me(bearer(tokens["access"])).status_code == 401
        assert get_me(bearer(theirs["access"])).status_code == 200

    def test_without_a_current_session_ends_them_all(self, api_client, user):
        sign_in(APIClient(), user)
        sign_in(APIClient(), user)
        api_client.force_authenticate(user=user)

        res = api_client.post(reverse("session_revoke_others"))

        assert res.json() == {"revoked": 2}
        assert not DeviceSession.objects.live().exists()


NEW_PASSWORD = "a-much-longer-passphrase-42"


@pytest.mark.django_db
class TestChangePassword:
    def _change(self, client, current, new):
        return client.post(
            reverse("change_password"),
            {"current_password": current, "new_password": new},
            format="json",
        )

    def test_wrong_current_password(self, api_client, user):
        tokens = sign_in(api_client, user)

        res = self._change(bearer(tokens["access"]), "nope", NEW_PASSWORD)

        assert res.status_code == 400
        assert "current_password" in res.json()
        user.refresh_from_db()
        assert user.check_password("testpass123")

    def test_weak_new_password(self, api_client, user):
        tokens = sign_in(api_client, user)

        res = self._change(bearer(tokens["access"]), "testpass123", "12345678")

        assert res.status_code == 400
        assert "new_password" in res.json()

    def test_success_keeps_this_device_and_signs_out_the_others(self, api_client, user):
        here = sign_in(api_client, user)
        there = sign_in(api_client, user)

        res = self._change(bearer(here["access"]), "testpass123", NEW_PASSWORD)

        assert res.status_code == 200
        assert res.json()["signed_out"] == 1
        assert get_me(bearer(here["access"])).status_code == 200
        assert get_me(bearer(there["access"])).status_code == 401
        sign_in(APIClient(), user, password=NEW_PASSWORD)
