"""Device sessions ↔ push subscriptions (ported from LLMStockAnalysis).

Coverage:
  GET /api/sessions/
    ├── per-session notification state: receiving / idle / off
    ├── notifications.channel push → devices lists the receiving sessions
    ├── notifications.channel email when push is idle, with the address
    └── reachable device with no session counted as unlinked

  ending a session stops that device's pushes
    ├── DELETE /api/sessions/<id>/
    ├── POST /api/auth/logout/
    └── POST /api/auth/password/ (signs the others out)

  push subscription ↔ session link
    ├── subscribe links the caller's session
    └── seen re-links a device that signed in again
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from accounts.tests.test_auth_flow import UA_IPHONE, bearer, sign_in
from notifications.models import PushSubscription

UA_MAC_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


@pytest.fixture(autouse=True)
def vapid_configured(settings):
    settings.WEB_PUSH_VAPID_PRIVATE_KEY = "test-private-key"


def _sid(tokens) -> str:
    return AccessToken(tokens["access"])["sid"]


def _subscribe(session_id, user, *, n=0, seen=timedelta(0), active=True):
    return PushSubscription.objects.create(
        user=user,
        endpoint=f"https://push.example/{n}",
        p256dh="k",
        auth="a",
        active=active,
        session_id=session_id,
        last_seen_at=timezone.now() - seen,
    )


@pytest.mark.django_db
class TestOverview:
    def test_notification_state_per_session(self, api_client, user):
        phone = sign_in(api_client, user, HTTP_USER_AGENT=UA_IPHONE)
        laptop = sign_in(api_client, user, HTTP_USER_AGENT=UA_MAC_CHROME)
        tablet = sign_in(api_client, user)
        _subscribe(_sid(phone), user, n=1)
        _subscribe(_sid(laptop), user, n=2, seen=timedelta(days=20))

        body = bearer(phone["access"]).get(reverse("session_list")).json()

        state = {s["id"]: s["notifications"] for s in body["sessions"]}
        assert state == {_sid(phone): "receiving", _sid(laptop): "idle", _sid(tablet): "off"}
        assert body["notifications"] == {
            "channel": "push",
            "email": user.email,
            "devices": [_sid(phone)],
            "unlinked_devices": 0,
        }

    def test_email_when_push_is_idle(self, api_client, user):
        laptop = sign_in(api_client, user)
        _subscribe(_sid(laptop), user, seen=timedelta(days=20))

        notifications = (
            bearer(laptop["access"]).get(reverse("session_list")).json()["notifications"]
        )
        assert notifications["channel"] == "email"
        assert notifications["email"] == user.email
        assert notifications["devices"] == []

    def test_no_channel_without_push_or_email(self, api_client, user):
        user.email = ""
        user.save(update_fields=["email"])
        tokens = sign_in(api_client, user)
        notifications = (
            bearer(tokens["access"]).get(reverse("session_list")).json()["notifications"]
        )
        assert notifications["channel"] is None

    def test_unlinked_reachable_device_is_counted(self, api_client, user):
        tokens = sign_in(api_client, user)
        _subscribe(None, user)

        notifications = (
            bearer(tokens["access"]).get(reverse("session_list")).json()["notifications"]
        )
        assert notifications["channel"] == "push"
        assert notifications["unlinked_devices"] == 1


@pytest.mark.django_db
class TestEndingASessionStopsPushes:
    def test_revoke_one(self, api_client, user):
        here = sign_in(api_client, user)
        there = sign_in(api_client, user)
        sub = _subscribe(_sid(there), user)

        bearer(here["access"]).delete(reverse("session_detail", args=[_sid(there)]))

        sub.refresh_from_db()
        assert sub.active is False

    def test_logout(self, api_client, user):
        tokens = sign_in(api_client, user)
        client = bearer(tokens["access"])
        client.post(
            reverse("subscribe"),
            {"endpoint": "https://push.example/phone", "keys": {"p256dh": "p", "auth": "a"}},
            format="json",
        )
        sub = PushSubscription.objects.get()
        assert str(sub.session_id) == _sid(tokens)
        assert sub.active

        client.post(reverse("logout"))

        sub.refresh_from_db()
        assert sub.active is False

    def test_password_change_stops_the_other_devices(self, api_client, user):
        here = sign_in(api_client, user)
        there = sign_in(api_client, user)
        mine = _subscribe(_sid(here), user, n=1)
        theirs = _subscribe(_sid(there), user, n=2)

        bearer(here["access"]).post(
            reverse("change_password"),
            {"current_password": "testpass123", "new_password": "a-much-longer-passphrase-42"},
            format="json",
        )

        mine.refresh_from_db()
        theirs.refresh_from_db()
        assert mine.active is True
        assert theirs.active is False


@pytest.mark.django_db
class TestPushSessionLink:
    def test_seen_relinks_a_device_that_signed_in_again(self, api_client, user):
        first = sign_in(api_client, user)
        sub = _subscribe(_sid(first), user)
        second = sign_in(api_client, user)

        res = bearer(second["access"]).post(
            reverse("seen"), {"endpoint": sub.endpoint}, format="json"
        )

        assert res.json() == {"active": True}
        sub.refresh_from_db()
        assert str(sub.session_id) == _sid(second)
