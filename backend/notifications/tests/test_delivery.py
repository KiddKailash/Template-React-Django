"""Tests for notifications.utils.delivery.

Coverage:
  choose_channel
    ├── device seen inside the window → push
    ├── device seen exactly at the window edge → push; just past it → email
    ├── no device / stale / never seen / inactive → email
    ├── push unconfigured → email even with a recent device
    ├── another user's recent device does not count
    └── no device and no address → None

  notify
    ├── preference off → None, no push row, no email
    ├── push delivered → "push", one row SENT, no email
    ├── pushes only the recent devices, not the stale ones
    ├── one of two recent devices delivers → still "push"
    ├── push reaches nobody → email, row FELL_BACK
    ├── fallback with no address → None
    ├── email path renders the template with frontend_url
    └── send_mail raises → None, never propagates
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.utils import timezone

from notifications.models import PushNotification, PushSubscription
from notifications.utils.delivery import Channel, Email, choose_channel, notify

TYPE = PushNotification.Type.GENERAL


@pytest.fixture(autouse=True)
def vapid_configured(settings):
    settings.WEB_PUSH_VAPID_PRIVATE_KEY = "test-private-key"
    settings.FRONTEND_URL = "https://app.example"


@pytest.fixture
def device():
    counter = iter(range(1000))

    def _make(user, *, seen: timedelta | None = timedelta(0), active=True):
        return PushSubscription.objects.create(
            user=user,
            endpoint=f"https://push.example/{next(counter)}",
            p256dh="k",
            auth="a",
            active=active,
            last_seen_at=None if seen is None else timezone.now() - seen,
        )

    return _make


@pytest.fixture
def webpush():
    response = MagicMock()
    response.status_code = 201
    with patch("pywebpush.webpush", return_value=response) as mock:
        yield mock


def _gone():
    from pywebpush import WebPushException

    resp = MagicMock()
    resp.status_code = 410
    return WebPushException("gone", response=resp)


def _email(**overrides):
    fields = {
        "subject": "Subject",
        "text": "Plain text",
        "template": "notifications/email/notification.html",
        "context": {"title": "Title", "body": "Body", "url": "/calendar"},
    }
    return Email(**{**fields, **overrides})


def _notify(user, **overrides):
    kwargs = {
        "user": user,
        "notification_type": TYPE,
        "title": "Title",
        "body": "Body",
        "url": "/calendar",
        "email": _email(),
    }
    return notify(**{**kwargs, **overrides})


# ---------------------------------------------------------------------------
# choose_channel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChooseChannel:
    def test_recent_device_means_push(self, user, device):
        device(user, seen=timedelta(days=13))
        assert choose_channel(user) == Channel.PUSH

    def test_window_edge(self, user, device):
        window = PushSubscription.ACTIVE_WINDOW
        device(user, seen=window - timedelta(minutes=1))
        assert choose_channel(user) == Channel.PUSH

        PushSubscription.objects.update(last_seen_at=timezone.now() - window - timedelta(minutes=1))
        assert choose_channel(user) == Channel.EMAIL

    @pytest.mark.parametrize(
        "kwargs",
        [
            None,
            {"seen": timedelta(days=15)},
            {"seen": None},
            {"seen": timedelta(0), "active": False},
        ],
        ids=["no-device", "stale", "never-seen", "inactive"],
    )
    def test_no_reachable_device_means_email(self, user, device, kwargs):
        if kwargs is not None:
            device(user, **kwargs)
        assert choose_channel(user) == Channel.EMAIL

    def test_push_unconfigured_means_email(self, user, device, settings):
        settings.WEB_PUSH_VAPID_PRIVATE_KEY = ""
        device(user)
        assert choose_channel(user) == Channel.EMAIL

    def test_another_users_device_does_not_count(self, user, other_user, device):
        device(other_user)
        assert choose_channel(user) == Channel.EMAIL

    def test_unreachable_by_both(self, user):
        user.email = ""
        user.save(update_fields=["email"])
        assert choose_channel(user) is None


# ---------------------------------------------------------------------------
# notify
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotify:
    def test_preference_off_sends_nothing(self, user, device, webpush, monkeypatch):
        monkeypatch.setattr("notifications.utils.dispatcher.allows", lambda *_: False)
        device(user)

        assert _notify(user) is None
        webpush.assert_not_called()
        assert not PushNotification.objects.exists()
        assert mail.outbox == []

    def test_push_delivered_means_no_email(self, user, device, webpush):
        device(user)

        assert _notify(user) == Channel.PUSH
        assert mail.outbox == []
        n = PushNotification.objects.get()
        assert n.status == PushNotification.Status.SENT
        assert (n.title, n.body, n.url) == ("Title", "Body", "/calendar")

    def test_only_recent_devices_are_pushed(self, user, device, webpush):
        recent = device(user)
        device(user, seen=timedelta(days=30))

        _notify(user)

        webpush.assert_called_once()
        sent_to = webpush.call_args.kwargs["subscription_info"]["endpoint"]
        assert sent_to == recent.endpoint

    def test_one_device_delivering_is_enough(self, user, device, webpush):
        device(user)
        device(user)
        ok = MagicMock(status_code=201)
        webpush.side_effect = [_gone(), ok]

        assert _notify(user) == Channel.PUSH
        assert mail.outbox == []

    def test_push_reaching_nobody_falls_back_to_email(self, user, device, webpush):
        device(user)
        webpush.side_effect = _gone()

        assert _notify(user) == Channel.EMAIL
        assert len(mail.outbox) == 1
        n = PushNotification.objects.get()
        assert n.status == PushNotification.Status.FELL_BACK
        assert n.attempt_count == 1

    def test_fallback_without_an_address_reaches_nobody(self, user, device, webpush):
        user.email = ""
        user.save(update_fields=["email"])
        device(user)
        webpush.side_effect = _gone()

        assert _notify(user) is None
        assert mail.outbox == []

    def test_email_renders_template_with_frontend_url(self, user, webpush):
        assert _notify(user, email=_email(subject="Hello")) == Channel.EMAIL

        webpush.assert_not_called()
        email = mail.outbox[0]
        assert email.subject == "Hello"
        assert email.body == "Plain text"
        assert email.to == [user.email]
        assert "https://app.example/calendar" in email.alternatives[0][0]

    def test_email_failure_is_swallowed(self, user):
        with patch("notifications.utils.delivery.send_mail", side_effect=RuntimeError("smtp")):
            assert _notify(user) is None
