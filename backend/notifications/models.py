"""Web Push notification machinery (ported from LLMStockAnalysis).

Three models:

  - `PushSubscription`     one row per registered browser endpoint, per user
  - `PushNotification`     one row per intent to deliver (retry / dead-letter state)
  - `NotificationDispatch` audit row per (notification, subscription) attempt

Which channel a notification goes out on is decided per notification by
``notifications.utils.delivery.notify``: push when the user has a device that
is subscribed and has had the app open within ``PushSubscription.ACTIVE_WINDOW``,
email otherwise (and email when that push reaches no device). Per-type opt-outs
are one function, ``notifications.utils.preferences.allows``.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class PushSubscriptionQuerySet(models.QuerySet):
    def reachable(self, user=None):
        """Subscriptions on a device the user has had the app open on recently.

        Only these are worth a push: a device not seen inside ``ACTIVE_WINDOW``
        is probably in a drawer, and its user is better served by email. A row
        never seen (``last_seen_at`` null) does not count until the device
        next opens the app.
        """
        qs = self.filter(
            active=True,
            last_seen_at__gte=timezone.now() - PushSubscription.ACTIVE_WINDOW,
        )
        return qs.filter(user=user) if user is not None else qs


class PushSubscription(models.Model):
    """Browser-issued Web Push endpoint, scoped to one user.

    (endpoint, p256dh, auth) is what ``pywebpush.webpush()`` needs. Rotating
    the VAPID key invalidates these rows; the frontend re-registers.

    ``last_seen_at`` is when this device last had the app open, reported by
    the frontend (``POST /api/notifications/seen/``) at most once per
    ``SEEN_RESOLUTION``. It decides push versus email.

    ``session`` is the sign-in (``accounts.DeviceSession``) that registered or
    last reported this device: how Settings names the device notifications go
    to. Ending that session deactivates the subscription.
    """

    # A device seen within this window gets pushes; otherwise, email.
    ACTIVE_WINDOW = timedelta(days=14)
    # last_seen_at is only rewritten when older than this: an app reopened all
    # day costs one write an hour, not one per page load.
    SEEN_RESOLUTION = timedelta(hours=1)

    objects = PushSubscriptionQuerySet.as_manager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=1024, unique=True)
    p256dh = models.CharField(max_length=256)
    auth = models.CharField(max_length=64)
    user_agent = models.CharField(max_length=256, blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    session = models.ForeignKey(
        "accounts.DeviceSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="push_subscriptions",
    )

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "active"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"PushSubscription({self.user_id}, {self.endpoint[:60]}…)"


class PushNotification(models.Model):
    """One intent to deliver a push to a user.

    Lifecycle:  PENDING → SENT
                       → FAILED      (transient; retried)
                       → DEAD_LETTER (MAX_ATTEMPTS failures; given up)
                       → FELL_BACK   (reached no device; emailed instead.
                                      Never retried, or the user gets both)

    Retry policy (``queue_push`` only): 1m, 5m, 15m backoff. Pushes sent by
    ``notify`` fall back to email instead of retrying.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DEAD_LETTER = "dead_letter", "Dead Letter"
        FELL_BACK = "fell_back", "Fell Back to Email"

    class Type(models.TextChoices):
        # Add one per kind of notification your app sends; opt-outs key on it
        # (utils/preferences.py). A new choice needs `makemigrations`.
        GENERAL = "general", "General"
        TEST = "test", "Test"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_notifications"
    )
    notification_type = models.CharField(max_length=32, choices=Type.choices, default=Type.GENERAL)
    title = models.CharField(max_length=128)
    body = models.TextField()
    url = models.CharField(max_length=512, default="/")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    BACKOFF_MINUTES = (1, 5, 15)
    MAX_ATTEMPTS = 3

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["user", "notification_type", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.notification_type} · {self.status} · {self.title[:40]}"

    def schedule_retry(self) -> None:
        """Bump attempt_count and either schedule the next attempt or DEAD_LETTER."""
        self.attempt_count += 1
        self.last_attempted_at = timezone.now()
        if self.attempt_count >= self.MAX_ATTEMPTS:
            self.status = self.Status.DEAD_LETTER
            self.next_attempt_at = None
        else:
            self.status = self.Status.FAILED
            backoff = self.BACKOFF_MINUTES[min(self.attempt_count, len(self.BACKOFF_MINUTES) - 1)]
            self.next_attempt_at = timezone.now() + timedelta(minutes=backoff)

    def mark_fell_back(self, error: str) -> None:
        self.status = self.Status.FELL_BACK
        self.attempt_count += 1
        self.last_attempted_at = timezone.now()
        self.next_attempt_at = None
        self.last_error = error[:512]

    def mark_sent(self) -> None:
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.next_attempt_at = None
        self.last_error = ""


class NotificationDispatch(models.Model):
    """Audit row per (notification, subscription) dispatch attempt."""

    class Outcome(models.TextChoices):
        DELIVERED = "delivered", "Delivered"
        GONE = "gone", "Gone (404/410: subscription expired)"
        TIMEOUT = "timeout", "Timeout"
        ERROR = "error", "Error"

    notification = models.ForeignKey(
        PushNotification, related_name="dispatches", on_delete=models.CASCADE
    )
    subscription = models.ForeignKey(
        PushSubscription,
        related_name="dispatches",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error_detail = models.TextField(blank=True, default="")
    attempted_at = models.DateTimeField(auto_now_add=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-attempted_at"]
        indexes = [models.Index(fields=["notification"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"dispatch {self.notification_id} → {self.outcome}"
