"""Tests for notifications.utils.dispatcher.

Coverage:
  flush_due_retries
    ├── drains due retries
    ├── throttled to one pass per RETRY_FLUSH_INTERVAL_SEC per process
    └── never raises

  queue_push
    ├── flushes due retries before queueing
    ├── preference-gated → returns None, no row written
    ├── unknown notification_type → allowed
    ├── writes row + triggers deliver()
    └── deliver failure does not raise to caller

  deliver
    ├── no VAPID key configured → row moved to FAILED, scheduled for retry
    ├── successful pywebpush → notification SENT, dispatch DELIVERED
    ├── pywebpush 410 → subscription deactivated, dispatch GONE
    ├── pywebpush 500 → dispatch ERROR, notification FAILED
    ├── non-WebPushException → dispatch TIMEOUT, notification FAILED
    ├── no active subscriptions → notification FAILED with descriptive error
    └── mix of active/inactive subs — only actives dispatched

  push_now  (single-shot push used by notify(); never retried)
    ├── delivered to a reachable device → SENT, attempt_count 1
    ├── no reachable device → FELL_BACK "no active subscriptions"
    ├── stale device is not sent to
    ├── VAPID unset → FELL_BACK without sending
    ├── unexpected exception → FELL_BACK, never raises
    └── FELL_BACK rows are never picked up by dispatch_pending

  dispatch_pending
    ├── picks up PENDING rows
    ├── picks up FAILED rows past next_attempt_at
    ├── ignores FAILED rows before next_attempt_at
    ├── ignores SENT rows
    └── ignores DEAD_LETTER rows
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from notifications.models import (
    NotificationDispatch,
    PushNotification,
    PushSubscription,
)
from notifications.utils import dispatcher as dispatcher_module
from notifications.utils.dispatcher import (
    deliver,
    dispatch_pending,
    flush_due_retries,
    push_now,
    queue_push,
)


@pytest.fixture(autouse=True)
def _reset_retry_flush_throttle():
    """Make the queue_push() retry flush deterministic regardless of test order.

    The throttle is module-level process state, so without this a test that
    happens to run after another would silently skip the flush.
    """
    dispatcher_module._last_retry_flush = 0.0
    yield
    dispatcher_module._last_retry_flush = 0.0


@pytest.fixture
def vapid_configured(settings):
    settings.WEB_PUSH_VAPID_PRIVATE_KEY = "test-private-key"
    settings.WEB_PUSH_VAPID_PUBLIC_KEY = "test-public-key"
    settings.WEB_PUSH_VAPID_SUBJECT = "mailto:test@example.com"


@pytest.fixture
def sub(user):
    return PushSubscription.objects.create(
        user=user,
        endpoint="https://push.example/1",
        p256dh="pkey",
        auth="akey",
    )


def _fake_webpush_response(status_code=201):
    r = MagicMock()
    r.status_code = status_code
    return r


def _webpush_exception(status_code):
    """Build a pywebpush.WebPushException with a response carrying `status_code`."""
    from pywebpush import WebPushException

    resp = MagicMock()
    resp.status_code = status_code
    exc = WebPushException("boom", response=resp)
    return exc


# ---------------------------------------------------------------------------
# queue_push
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestQueuePush:
    def test_returns_none_when_preference_disabled(self, user, monkeypatch):
        monkeypatch.setattr("notifications.utils.dispatcher.allows", lambda *_: False)
        result = queue_push(
            user=user,
            notification_type=PushNotification.Type.GENERAL,
            title="t",
            body="b",
        )
        assert result is None
        assert not PushNotification.objects.exists()

    def test_unknown_type_is_allowed(self, user, vapid_configured):
        with patch("notifications.utils.dispatcher._send_one_web_push") as send:
            send.return_value = MagicMock(outcome=NotificationDispatch.Outcome.DELIVERED)
            result = queue_push(
                user=user,
                notification_type="something_unmapped",
                title="t",
                body="b",
            )
        assert result is not None
        assert PushNotification.objects.count() == 1

    def test_writes_row_and_invokes_deliver(self, user, vapid_configured, sub):
        with patch("notifications.utils.dispatcher._send_one_web_push") as send:
            send.return_value = NotificationDispatch(
                notification=None,
                subscription=sub,
                outcome=NotificationDispatch.Outcome.DELIVERED,
            )
            result = queue_push(
                user=user,
                notification_type=PushNotification.Type.GENERAL,
                title="t",
                body="b",
                url="/watchlist",
            )
        assert result is not None
        assert result.url == "/watchlist"
        send.assert_called_once()

    def test_deliver_exception_does_not_raise(self, user, vapid_configured, sub):
        # Callers (email-sending management commands) must never see push
        # errors — email is the authoritative channel.
        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=RuntimeError("boom"),
        ):
            result = queue_push(
                user=user,
                notification_type=PushNotification.Type.GENERAL,
                title="t",
                body="b",
            )
        assert result is not None  # row was written before deliver blew up

    def test_title_body_url_truncation(self, user, vapid_configured):
        with patch("notifications.utils.dispatcher.deliver"):
            n = queue_push(
                user=user,
                notification_type=PushNotification.Type.GENERAL,
                title="x" * 500,
                body="b",
                url="/" + ("y" * 600),
            )
        assert len(n.title) == 128
        assert len(n.url) == 512


# ---------------------------------------------------------------------------
# deliver
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeliver:
    def _pending(self, user):
        return PushNotification.objects.create(
            user=user,
            notification_type=PushNotification.Type.GENERAL,
            title="t",
            body="b",
        )

    def test_missing_vapid_schedules_retry(self, user, settings):
        settings.WEB_PUSH_VAPID_PRIVATE_KEY = ""
        n = self._pending(user)
        deliver(n)
        n.refresh_from_db()
        assert n.status == PushNotification.Status.FAILED
        assert n.last_error == "VAPID keys not configured"
        assert n.attempt_count == 1

    def test_success_marks_sent_and_records_dispatch(self, user, vapid_configured, sub):
        n = self._pending(user)
        with patch("pywebpush.webpush", return_value=_fake_webpush_response(201)) as web:
            deliver(n)
        n.refresh_from_db()
        sub.refresh_from_db()
        assert n.status == PushNotification.Status.SENT
        assert n.sent_at is not None
        assert n.dispatches.count() == 1
        assert n.dispatches.first().outcome == NotificationDispatch.Outcome.DELIVERED
        assert sub.last_success_at is not None
        web.assert_called_once()

    def test_410_deactivates_subscription(self, user, vapid_configured, sub):
        n = self._pending(user)
        with patch("pywebpush.webpush", side_effect=_webpush_exception(410)):
            deliver(n)
        n.refresh_from_db()
        sub.refresh_from_db()
        assert sub.active is False
        assert n.dispatches.first().outcome == NotificationDispatch.Outcome.GONE
        assert n.status == PushNotification.Status.FAILED

    def test_404_deactivates_subscription(self, user, vapid_configured, sub):
        n = self._pending(user)
        with patch("pywebpush.webpush", side_effect=_webpush_exception(404)):
            deliver(n)
        sub.refresh_from_db()
        assert sub.active is False

    def test_500_error_records_error_outcome(self, user, vapid_configured, sub):
        n = self._pending(user)
        with patch("pywebpush.webpush", side_effect=_webpush_exception(500)):
            deliver(n)
        sub.refresh_from_db()
        assert sub.active is True  # NOT deactivated on non-410/404
        n.refresh_from_db()
        assert n.status == PushNotification.Status.FAILED
        assert n.dispatches.first().outcome == NotificationDispatch.Outcome.ERROR

    def test_generic_exception_treated_as_timeout(self, user, vapid_configured, sub):
        n = self._pending(user)
        with patch("pywebpush.webpush", side_effect=TimeoutError("slow")):
            deliver(n)
        n.refresh_from_db()
        assert n.status == PushNotification.Status.FAILED
        assert n.dispatches.first().outcome == NotificationDispatch.Outcome.TIMEOUT

    def test_no_active_subscriptions_records_descriptive_error(self, user, vapid_configured):
        n = self._pending(user)
        deliver(n)
        n.refresh_from_db()
        assert n.status == PushNotification.Status.FAILED
        assert n.last_error == "no active subscriptions"
        assert n.dispatches.count() == 0

    def test_inactive_subscriptions_are_skipped(self, user, vapid_configured):
        PushSubscription.objects.create(
            user=user,
            endpoint="https://push.example/dead",
            p256dh="k",
            auth="a",
            active=False,
        )
        active = PushSubscription.objects.create(
            user=user,
            endpoint="https://push.example/alive",
            p256dh="k",
            auth="a",
            active=True,
        )
        n = self._pending(user)
        with patch("pywebpush.webpush", return_value=_fake_webpush_response(201)):
            deliver(n)
        n.refresh_from_db()
        assert n.dispatches.count() == 1
        assert n.dispatches.first().subscription_id == active.id


# ---------------------------------------------------------------------------
# dispatch_pending
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDispatchPending:
    def _mk(self, user, status, next_attempt_at=None):
        return PushNotification.objects.create(
            user=user,
            notification_type=PushNotification.Type.GENERAL,
            title="t",
            body="b",
            status=status,
            next_attempt_at=next_attempt_at,
        )

    def test_picks_up_pending(self, user, vapid_configured):
        self._mk(user, PushNotification.Status.PENDING)
        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=lambda n: n,
        ) as d:
            dispatch_pending()
        assert d.called

    def test_picks_up_failed_past_next_attempt(self, user, vapid_configured):
        self._mk(
            user,
            PushNotification.Status.FAILED,
            next_attempt_at=timezone.now() - timedelta(minutes=1),
        )
        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=lambda n: n,
        ) as d:
            dispatch_pending()
        assert d.call_count == 1

    def test_ignores_failed_before_next_attempt(self, user, vapid_configured):
        self._mk(
            user,
            PushNotification.Status.FAILED,
            next_attempt_at=timezone.now() + timedelta(minutes=10),
        )
        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=lambda n: n,
        ) as d:
            dispatch_pending()
        assert d.call_count == 0

    def test_ignores_sent(self, user, vapid_configured):
        self._mk(user, PushNotification.Status.SENT)
        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=lambda n: n,
        ) as d:
            dispatch_pending()
        assert d.call_count == 0

    def test_ignores_dead_letter(self, user, vapid_configured):
        self._mk(user, PushNotification.Status.DEAD_LETTER)
        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=lambda n: n,
        ) as d:
            dispatch_pending()
        assert d.call_count == 0

    def test_returns_counts(self, user, vapid_configured):
        self._mk(user, PushNotification.Status.PENDING)
        self._mk(user, PushNotification.Status.PENDING)

        def fake_deliver(n):
            n.status = PushNotification.Status.SENT
            n.save(update_fields=["status"])
            return n

        with patch(
            "notifications.utils.dispatcher.deliver",
            side_effect=fake_deliver,
        ):
            result = dispatch_pending()
        assert result == {"sent": 2, "failed": 0}


# ---------------------------------------------------------------------------
# flush_due_retries — the replacement for the `*/5` dispatch_pending_pushes cron
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFlushDueRetries:
    def _failed_and_due(self, user):
        return PushNotification.objects.create(
            user=user,
            notification_type=PushNotification.Type.GENERAL,
            title="t",
            body="b",
            status=PushNotification.Status.FAILED,
            attempt_count=1,
            next_attempt_at=timezone.now() - timedelta(minutes=1),
        )

    def test_drains_a_due_retry(self, user, vapid_configured):
        self._failed_and_due(user)

        def fake_deliver(n):
            n.status = PushNotification.Status.SENT
            n.save(update_fields=["status"])
            return n

        with patch("notifications.utils.dispatcher.deliver", side_effect=fake_deliver) as d:
            flush_due_retries()
        assert d.call_count == 1

    def test_throttled_to_one_pass_per_interval(self, user, vapid_configured):
        """A sender looping over users must not re-scan the retry table per call."""
        self._failed_and_due(user)
        with patch(
            "notifications.utils.dispatcher.dispatch_pending",
            return_value={"sent": 0, "failed": 0},
        ) as dp:
            flush_due_retries()
            flush_due_retries()
            flush_due_retries()
        assert dp.call_count == 1

    def test_never_raises(self, user, vapid_configured):
        with patch(
            "notifications.utils.dispatcher.dispatch_pending",
            side_effect=RuntimeError("db down"),
        ):
            flush_due_retries()  # must not raise

    def test_queue_push_flushes_first(self, user, vapid_configured, sub):
        """The backlog is drained by the notification flow, not by a timer."""
        with patch("notifications.utils.dispatcher.flush_due_retries") as flush:
            with patch("notifications.utils.dispatcher.deliver", side_effect=lambda n: n):
                queue_push(
                    user=user,
                    notification_type=PushNotification.Type.GENERAL,
                    title="t",
                    body="b",
                )
        flush.assert_called_once_with()


# ---------------------------------------------------------------------------
# push_now
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPushNow:
    def _push(self, user):
        return push_now(
            user=user,
            notification_type=PushNotification.Type.GENERAL,
            title="t",
            body="b",
            url="/calendar",
        )

    def _seen(self, sub, ago=timedelta(0)):
        sub.last_seen_at = timezone.now() - ago
        sub.save(update_fields=["last_seen_at"])
        return sub

    def test_delivered_to_reachable_device(self, user, vapid_configured, sub):
        self._seen(sub)
        with patch("pywebpush.webpush", return_value=_fake_webpush_response()):
            n = self._push(user)
        assert n.status == PushNotification.Status.SENT
        assert n.attempt_count == 1
        assert n.sent_at is not None
        assert n.dispatches.get().outcome == NotificationDispatch.Outcome.DELIVERED

    def test_no_reachable_device_falls_back(self, user, vapid_configured):
        n = self._push(user)
        assert n.status == PushNotification.Status.FELL_BACK
        assert n.last_error == "no active subscriptions"
        assert n.next_attempt_at is None

    def test_stale_device_is_not_sent_to(self, user, vapid_configured, sub):
        self._seen(sub, ago=timedelta(days=20))
        with patch("pywebpush.webpush") as wp:
            n = self._push(user)
        wp.assert_not_called()
        assert n.status == PushNotification.Status.FELL_BACK

    def test_vapid_unset_falls_back_without_sending(self, user, settings, sub):
        settings.WEB_PUSH_VAPID_PRIVATE_KEY = ""
        self._seen(sub)
        with patch("pywebpush.webpush") as wp:
            n = self._push(user)
        wp.assert_not_called()
        assert n.status == PushNotification.Status.FELL_BACK
        assert n.last_error == "VAPID keys not configured"

    def test_unexpected_exception_falls_back(self, user, vapid_configured, sub):
        self._seen(sub)
        with patch("notifications.utils.dispatcher._send_to", side_effect=RuntimeError("db")):
            n = self._push(user)
        assert n.status == PushNotification.Status.FELL_BACK
        assert n.last_error == "db"

    def test_fell_back_rows_are_never_retried(self, user, vapid_configured):
        self._push(user)
        with patch("notifications.utils.dispatcher.deliver") as d:
            assert dispatch_pending() == {"sent": 0, "failed": 0}
        d.assert_not_called()


@pytest.mark.django_db
class TestTtl:
    """TTL 0 (pywebpush's default) makes push services drop messages for any
    device that is not reachable at that instant."""

    def test_sends_a_ttl(self, user, vapid_configured, sub, settings):
        settings.WEB_PUSH_TTL_SECONDS = 3600
        with patch("pywebpush.webpush", return_value=_fake_webpush_response()) as webpush:
            queue_push(
                user=user, notification_type=PushNotification.Type.GENERAL, title="t", body="b"
            )
        assert webpush.call_args.kwargs["ttl"] == 3600

    def test_default_is_a_day(self, user, vapid_configured, sub):
        with patch("pywebpush.webpush", return_value=_fake_webpush_response()) as webpush:
            queue_push(
                user=user, notification_type=PushNotification.Type.GENERAL, title="t", body="b"
            )
        assert webpush.call_args.kwargs["ttl"] == 86400
