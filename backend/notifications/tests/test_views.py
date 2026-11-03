"""Tests for notifications.views (DRF endpoints).

Coverage:
  vapid_public_key
    ├── returns configured key
    ├── returns "" when unconfigured
    └── requires authentication

  subscribe
    ├── creates row on first call
    ├── upserts on re-registration (same endpoint, same user)
    ├── rebinds ownership when a different user re-registers same endpoint
    ├── stamps last_seen_at (subscribing is the device in use)
    ├── rejects missing keys
    ├── rejects invalid endpoint
    └── requires authentication

  seen
    ├── stamps last_seen_at on the caller's live subscription → active
    ├── coalesced: a second report inside SEEN_RESOLUTION does not rewrite
    ├── refreshes once older than SEEN_RESOLUTION
    ├── active=false for unknown / another user's / inactive endpoint
    ├── 400 when endpoint missing
    └── requires authentication

  unsubscribe
    ├── deactivates row for the caller
    ├── does NOT touch another user's subscription with the same endpoint
    ├── 400 when endpoint missing
    └── requires authentication

  test_push (works in production; throttled per user)
    ├── pushes once to the caller's reachable devices → 200 with the count
    ├── reaches no device → 502, row FELL_BACK
    ├── VAPID unset → 503, nothing written
    ├── another user's devices are never sent to
    └── requires authentication
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from notifications.models import PushNotification, PushSubscription

# ---------------------------------------------------------------------------
# vapid_public_key
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVapidPublicKey:
    def test_returns_configured_key(self, authenticated_client, settings):
        settings.WEB_PUSH_VAPID_PUBLIC_KEY = "abc123"
        res = authenticated_client.get(reverse("vapid_public_key"))
        assert res.status_code == status.HTTP_200_OK
        assert res.json() == {"public_key": "abc123"}

    def test_returns_empty_when_unconfigured(self, authenticated_client, settings):
        settings.WEB_PUSH_VAPID_PUBLIC_KEY = ""
        res = authenticated_client.get(reverse("vapid_public_key"))
        assert res.status_code == status.HTTP_200_OK
        assert res.json() == {"public_key": ""}

    def test_requires_auth(self, api_client):
        res = api_client.get(reverse("vapid_public_key"))
        assert res.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------


def _sub_payload(endpoint="https://push.example/abc"):
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "pkey", "auth": "akey"},
    }


@pytest.mark.django_db
class TestSubscribe:
    url = reverse("subscribe")

    def test_creates_row(self, authenticated_client, user):
        res = authenticated_client.post(self.url, _sub_payload(), format="json")
        assert res.status_code == status.HTTP_201_CREATED
        assert res.json()["created"] is True
        sub = PushSubscription.objects.get(endpoint="https://push.example/abc")
        assert sub.user_id == user.id
        assert sub.active is True
        assert sub.p256dh == "pkey"
        assert sub.auth == "akey"
        assert sub.last_seen_at is not None
        assert timezone.now() - sub.last_seen_at < timedelta(minutes=1)

    def test_upsert_same_user_refreshes_keys(self, authenticated_client, user):
        PushSubscription.objects.create(
            user=user,
            endpoint="https://push.example/abc",
            p256dh="old",
            auth="old-a",
        )
        payload = _sub_payload()
        payload["keys"] = {"p256dh": "new", "auth": "new-a"}
        res = authenticated_client.post(self.url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        assert res.json()["created"] is False

        sub = PushSubscription.objects.get(endpoint="https://push.example/abc")
        assert sub.p256dh == "new"
        assert sub.auth == "new-a"
        assert sub.user_id == user.id
        assert PushSubscription.objects.count() == 1

    def test_rebinds_when_other_user_reregisters_same_endpoint(
        self, authenticated_client, user, other_user
    ):
        # Previous user's device now signed in as `user`. The browser hands us
        # the same endpoint — we rebind rather than orphan a stale row.
        PushSubscription.objects.create(
            user=other_user,
            endpoint="https://push.example/abc",
            p256dh="old",
            auth="old-a",
        )
        res = authenticated_client.post(self.url, _sub_payload(), format="json")
        assert res.status_code == status.HTTP_201_CREATED
        sub = PushSubscription.objects.get(endpoint="https://push.example/abc")
        assert sub.user_id == user.id
        assert PushSubscription.objects.count() == 1

    def test_rejects_missing_keys(self, authenticated_client):
        res = authenticated_client.post(
            self.url,
            {"endpoint": "https://push.example/x", "keys": {"p256dh": "k"}},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_invalid_endpoint(self, authenticated_client):
        res = authenticated_client.post(
            self.url, {"endpoint": "not-a-url", "keys": {}}, format="json"
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_auth(self, api_client):
        res = api_client.post(self.url, _sub_payload(), format="json")
        assert res.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


@pytest.mark.django_db
class TestSeen:
    url = reverse("seen")

    def _sub(self, user, *, last_seen_at=None, active=True, endpoint="https://push.example/seen"):
        return PushSubscription.objects.create(
            user=user,
            endpoint=endpoint,
            p256dh="k",
            auth="a",
            active=active,
            last_seen_at=last_seen_at,
        )

    def test_stamps_last_seen_and_reports_active(self, authenticated_client, user):
        sub = self._sub(user)
        res = authenticated_client.post(self.url, {"endpoint": sub.endpoint}, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res.json() == {"active": True}
        sub.refresh_from_db()
        assert timezone.now() - sub.last_seen_at < timedelta(minutes=1)
        assert PushSubscription.objects.reachable(user).get() == sub

    def test_coalesced_inside_resolution(self, authenticated_client, user):
        earlier = timezone.now() - timedelta(minutes=10)
        sub = self._sub(user, last_seen_at=earlier)
        authenticated_client.post(self.url, {"endpoint": sub.endpoint}, format="json")
        sub.refresh_from_db()
        assert sub.last_seen_at == earlier

    def test_refreshes_once_older_than_resolution(self, authenticated_client, user):
        old = timezone.now() - PushSubscription.SEEN_RESOLUTION - timedelta(minutes=1)
        sub = self._sub(user, last_seen_at=old)
        authenticated_client.post(self.url, {"endpoint": sub.endpoint}, format="json")
        sub.refresh_from_db()
        assert sub.last_seen_at > old

    def test_unknown_endpoint_is_inactive(self, authenticated_client):
        res = authenticated_client.post(
            self.url, {"endpoint": "https://push.example/nope"}, format="json"
        )
        assert res.json() == {"active": False}

    def test_other_users_subscription_is_inactive_and_untouched(
        self, authenticated_client, other_user
    ):
        sub = self._sub(other_user)
        res = authenticated_client.post(self.url, {"endpoint": sub.endpoint}, format="json")
        assert res.json() == {"active": False}
        sub.refresh_from_db()
        assert sub.last_seen_at is None

    def test_inactive_subscription_is_inactive_and_untouched(self, authenticated_client, user):
        sub = self._sub(user, active=False)
        res = authenticated_client.post(self.url, {"endpoint": sub.endpoint}, format="json")
        assert res.json() == {"active": False}
        sub.refresh_from_db()
        assert sub.last_seen_at is None

    def test_400_when_endpoint_missing(self, authenticated_client):
        res = authenticated_client.post(self.url, {}, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_auth(self, api_client):
        res = api_client.post(self.url, {"endpoint": "https://push.example/x"}, format="json")
        assert res.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


@pytest.mark.django_db
class TestUnsubscribe:
    url = reverse("unsubscribe")

    def test_deactivates_caller_subscription(self, authenticated_client, user):
        sub = PushSubscription.objects.create(
            user=user,
            endpoint="https://push.example/abc",
            p256dh="k",
            auth="a",
        )
        res = authenticated_client.post(self.url, {"endpoint": sub.endpoint}, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res.json() == {"unsubscribed": 1}
        sub.refresh_from_db()
        assert sub.active is False

    def test_scoped_to_caller_only(self, authenticated_client, user, other_user):
        other_sub = PushSubscription.objects.create(
            user=other_user,
            endpoint="https://push.example/foreign",
            p256dh="k",
            auth="a",
        )
        res = authenticated_client.post(self.url, {"endpoint": other_sub.endpoint}, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res.json() == {"unsubscribed": 0}
        other_sub.refresh_from_db()
        assert other_sub.active is True

    def test_400_when_endpoint_missing(self, authenticated_client):
        res = authenticated_client.post(self.url, {}, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_auth(self, api_client):
        res = api_client.post(self.url, {"endpoint": "https://push.example/x"}, format="json")
        assert res.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# test_push
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTestPushEndpoint:
    url = reverse("test_push")

    @pytest.fixture(autouse=True)
    def vapid(self, settings):
        settings.WEB_PUSH_VAPID_PRIVATE_KEY = "test-private-key"

    def _sub(self, user, n=0):
        return PushSubscription.objects.create(
            user=user,
            endpoint=f"https://push.example/t{n}",
            p256dh="k",
            auth="a",
            last_seen_at=timezone.now(),
        )

    def test_pushes_to_own_devices(self, authenticated_client, user, other_user):
        self._sub(user, 1)
        self._sub(other_user, 2)
        with patch("pywebpush.webpush") as webpush:
            webpush.return_value.status_code = 201
            res = authenticated_client.post(self.url, {}, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["delivered"] == 1
        assert webpush.call_count == 1
        sent_to = webpush.call_args.kwargs["subscription_info"]["endpoint"]
        assert sent_to == "https://push.example/t1"
        n = PushNotification.objects.get()
        assert n.notification_type == PushNotification.Type.TEST
        assert n.status == PushNotification.Status.SENT

    def test_no_device_is_502(self, authenticated_client, user):
        res = authenticated_client.post(self.url, {}, format="json")
        assert res.status_code == status.HTTP_502_BAD_GATEWAY
        assert PushNotification.objects.get().status == PushNotification.Status.FELL_BACK

    def test_unconfigured_is_503(self, authenticated_client, settings):
        settings.WEB_PUSH_VAPID_PRIVATE_KEY = ""
        res = authenticated_client.post(self.url, {}, format="json")
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert not PushNotification.objects.exists()

    def test_requires_auth(self, api_client):
        res = api_client.post(self.url, {}, format="json")
        assert res.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
