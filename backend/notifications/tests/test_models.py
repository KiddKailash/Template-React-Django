"""Tests for notifications.models.

Coverage:
  PushNotification.schedule_retry
    ├── first failure → FAILED, next_attempt_at set in the future
    ├── second failure → FAILED, next_attempt_at set (backoff monotonically ≥)
    ├── third failure → DEAD_LETTER, next_attempt_at cleared
    ├── attempt_count monotonically increases
    └── last_attempted_at bumped every call

  PushNotification.mark_sent
    ├── status = SENT
    ├── sent_at populated
    ├── next_attempt_at cleared
    └── last_error cleared

  PushNotification.mark_fell_back
    └── FELL_BACK, attempt counted, never scheduled for retry

  PushSubscription
    ├── endpoint is globally unique (rebind across users at the view layer)
    └── reachable(): active and seen inside ACTIVE_WINDOW, scoped to the user

  NotificationDispatch
    └── subscription deletion preserves dispatch row (SET_NULL)
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from notifications.models import (
    NotificationDispatch,
    PushNotification,
    PushSubscription,
)


def _make(user, **overrides):
    defaults = {
        "user": user,
        "notification_type": PushNotification.Type.GENERAL,
        "title": "t",
        "body": "b",
    }
    defaults.update(overrides)
    return PushNotification.objects.create(**defaults)


@pytest.mark.django_db
class TestScheduleRetry:
    def test_first_failure_moves_to_failed_and_schedules_future_retry(self, user):
        n = _make(user)
        before = timezone.now()
        n.schedule_retry()

        assert n.status == PushNotification.Status.FAILED
        assert n.attempt_count == 1
        assert n.next_attempt_at is not None
        assert n.next_attempt_at > before

    def test_second_failure_backoff_monotonically_non_decreasing(self, user):
        n = _make(user)
        n.schedule_retry()
        first_delay = n.next_attempt_at - n.last_attempted_at

        n.schedule_retry()
        second_delay = n.next_attempt_at - n.last_attempted_at

        assert n.status == PushNotification.Status.FAILED
        assert n.attempt_count == 2
        assert second_delay >= first_delay

    def test_final_failure_moves_to_dead_letter(self, user):
        n = _make(user, attempt_count=PushNotification.MAX_ATTEMPTS - 1)
        n.schedule_retry()

        assert n.status == PushNotification.Status.DEAD_LETTER
        assert n.attempt_count == PushNotification.MAX_ATTEMPTS
        assert n.next_attempt_at is None

    def test_attempt_count_increments_monotonically(self, user):
        n = _make(user)
        for expected in range(1, PushNotification.MAX_ATTEMPTS + 1):
            n.schedule_retry()
            assert n.attempt_count == expected

    def test_last_attempted_at_bumped_on_each_call(self, user):
        n = _make(user)
        assert n.last_attempted_at is None
        n.schedule_retry()
        first = n.last_attempted_at
        assert first is not None
        n.schedule_retry()
        assert n.last_attempted_at >= first


@pytest.mark.django_db
class TestMarkSent:
    def test_transitions_to_sent_and_clears_retry_state(self, user):
        n = _make(user, last_error="prior failure")
        n.next_attempt_at = timezone.now() + timedelta(minutes=5)
        n.save()

        n.mark_sent()

        assert n.status == PushNotification.Status.SENT
        assert n.sent_at is not None
        assert n.next_attempt_at is None
        assert n.last_error == ""


@pytest.mark.django_db
class TestPushSubscription:
    def test_endpoint_is_globally_unique(self, user, other_user):
        PushSubscription.objects.create(
            user=user, endpoint="https://push.example/a", p256dh="k", auth="a"
        )
        with pytest.raises(IntegrityError):
            PushSubscription.objects.create(
                user=other_user,
                endpoint="https://push.example/a",
                p256dh="k2",
                auth="a2",
            )


@pytest.mark.django_db
class TestMarkFellBack:
    def test_terminal_and_not_retried(self, user):
        n = _make(user)
        n.mark_fell_back("x" * 600)
        n.save()
        n.refresh_from_db()
        assert n.status == PushNotification.Status.FELL_BACK
        assert n.attempt_count == 1
        assert n.next_attempt_at is None
        assert n.last_attempted_at is not None
        assert len(n.last_error) == 512


@pytest.mark.django_db
class TestReachable:
    def _sub(self, user, n, *, seen_ago, active=True):
        return PushSubscription.objects.create(
            user=user,
            endpoint=f"https://push.example/r{n}",
            p256dh="k",
            auth="a",
            active=active,
            last_seen_at=None if seen_ago is None else timezone.now() - seen_ago,
        )

    def test_filters_on_activity_and_active_flag(self, user, other_user):
        fresh = self._sub(user, 1, seen_ago=timedelta(days=1))
        self._sub(user, 2, seen_ago=timedelta(days=15))
        self._sub(user, 3, seen_ago=None)
        self._sub(user, 4, seen_ago=timedelta(days=1), active=False)
        theirs = self._sub(other_user, 5, seen_ago=timedelta(days=1))

        assert list(PushSubscription.objects.reachable(user)) == [fresh]
        assert set(PushSubscription.objects.reachable()) == {fresh, theirs}


@pytest.mark.django_db
class TestNotificationDispatch:
    def test_subscription_delete_preserves_dispatch_row(self, user):
        n = _make(user)
        sub = PushSubscription.objects.create(
            user=user, endpoint="https://push.example/x", p256dh="k", auth="a"
        )
        d = NotificationDispatch.objects.create(
            notification=n,
            subscription=sub,
            outcome=NotificationDispatch.Outcome.DELIVERED,
        )
        sub.delete()
        d.refresh_from_db()
        assert d.subscription is None
        assert d.outcome == NotificationDispatch.Outcome.DELIVERED
