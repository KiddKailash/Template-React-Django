"""Send a PushNotification via Web Push against a user's live subscriptions.

  - queue_push() drains any due retries, then creates a PENDING row
    (respecting the user's opt-out preferences) and attempts delivery.
  - deliver() sends to every active PushSubscription belonging to the
    notification's user; 404/410 responses mark the subscription inactive
    (browser-side unsubscribed).
  - dispatch_pending() picks up FAILED rows whose retry window has elapsed.
  - push_now() is the single-shot send ``notify()`` uses: reachable devices
    only, no retry. A push that reaches nobody is marked FELL_BACK and the
    caller emails instead.

Retries are governed by ``PushNotification.schedule_retry()`` (1m/5m/15m,
DEAD_LETTER after 3 attempts).

Retries are driven by the notification flow itself: every queue_push()
flushes the backlog first, so a retry rides along with the next notification
event (and those events are what produce failed rows in the first place).
`cron/orchestrate.sh daily` also runs `dispatch_pending_pushes` as a
backstop. LLMStockAnalysis found a `*/5` retry cron ran 288 times a day to
send nothing.
"""

from __future__ import annotations

import json
import logging
import threading
import time

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ..models import (
    NotificationDispatch,
    PushNotification,
    PushSubscription,
)
from .preferences import allows

logger = logging.getLogger(__name__)

WEB_PUSH_TIMEOUT_SEC = 5


def _ttl_seconds() -> int:
    """How long the push service holds a message for an unreachable device.

    pywebpush defaults to 0, which tells the push service to drop the message
    unless the device is reachable at that instant: a phone asleep, offline or
    in Doze silently never gets it, while the push service's 201 still marks
    the notification SENT. (LLMStockAnalysis sends with TTL 0.)
    """
    return int(getattr(settings, "WEB_PUSH_TTL_SECONDS", 24 * 60 * 60))


# queue_push() flushes due retries before queueing. Senders typically call it
# once per user in a loop, so the flush is throttled
# to one pass per process per interval — otherwise a 50-user digest run would
# re-scan the retry table 50 times to find the same (usually empty) set.
RETRY_FLUSH_INTERVAL_SEC = 60
_last_retry_flush = 0.0
_retry_flush_lock = threading.Lock()


def _vapid_claims() -> dict:
    return {"sub": getattr(settings, "WEB_PUSH_VAPID_SUBJECT", "mailto:admin@example.com")}


def _preference_allows(user, notification_type: str) -> bool:
    """The opt-out check shared with the email path (utils/preferences.py)."""
    return allows(user, notification_type)


def _send_one_web_push(
    notification: PushNotification, subscription: PushSubscription
) -> NotificationDispatch:
    # Import inside the function so environments without pywebpush installed
    # only crash at delivery time — model migrations and admin still work.
    from pywebpush import WebPushException, webpush

    payload = {
        "title": notification.title,
        "body": notification.body,
        "url": notification.url,
        "type": notification.notification_type,
        "notification_id": notification.id,
    }
    sub_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    started = time.monotonic()
    try:
        response = webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
            vapid_claims=_vapid_claims(),
            timeout=WEB_PUSH_TIMEOUT_SEC,
            ttl=_ttl_seconds(),
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        subscription.last_success_at = timezone.now()
        subscription.save(update_fields=["last_success_at", "updated_at"])
        return NotificationDispatch.objects.create(
            notification=notification,
            subscription=subscription,
            outcome=NotificationDispatch.Outcome.DELIVERED,
            http_status=getattr(response, "status_code", 201),
            latency_ms=latency_ms,
        )
    except WebPushException as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (404, 410):
            subscription.active = False
            subscription.save(update_fields=["active", "updated_at"])
            outcome = NotificationDispatch.Outcome.GONE
        else:
            outcome = NotificationDispatch.Outcome.ERROR
        return NotificationDispatch.objects.create(
            notification=notification,
            subscription=subscription,
            outcome=outcome,
            http_status=status_code,
            error_detail=str(exc)[:512],
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return NotificationDispatch.objects.create(
            notification=notification,
            subscription=subscription,
            outcome=NotificationDispatch.Outcome.TIMEOUT,
            error_detail=str(exc)[:512],
            latency_ms=latency_ms,
        )


def push_configured() -> bool:
    return bool(getattr(settings, "WEB_PUSH_VAPID_PRIVATE_KEY", ""))


def _send_to(notification: PushNotification, subs: list) -> str:
    """Send to each of ``subs``. Returns "" if any delivered, else the error."""
    delivered = False
    for sub in subs:
        dispatch = _send_one_web_push(notification, sub)
        if dispatch.outcome == NotificationDispatch.Outcome.DELIVERED:
            delivered = True
    if delivered:
        return ""
    last_error = notification.dispatches.order_by("-attempted_at").values_list(
        "error_detail", flat=True
    ).first() or ("no active subscriptions" if not subs else "no dispatch succeeded")
    return last_error


def deliver(notification: PushNotification) -> PushNotification:
    """Attempt delivery to every active subscription for the notification's user."""
    if not push_configured():
        logger.warning("notifications.web_push.no_vapid_key")
        notification.last_error = "VAPID keys not configured"
        notification.schedule_retry()
        notification.save(
            update_fields=[
                "status",
                "attempt_count",
                "last_attempted_at",
                "next_attempt_at",
                "last_error",
            ]
        )
        return notification

    subs = list(PushSubscription.objects.filter(user=notification.user, active=True))
    last_error = _send_to(notification, subs)

    if not last_error:
        notification.mark_sent()
        notification.save(update_fields=["status", "sent_at", "next_attempt_at", "last_error"])
    else:
        notification.last_error = last_error[:512]
        notification.schedule_retry()
        notification.save(
            update_fields=[
                "status",
                "attempt_count",
                "last_attempted_at",
                "next_attempt_at",
                "last_error",
            ]
        )
    return notification


def dispatch_pending() -> dict:
    """Worker entry point: send every notification ready to fire."""
    now = timezone.now()
    queryset = PushNotification.objects.filter(
        status__in=[
            PushNotification.Status.PENDING,
            PushNotification.Status.FAILED,
        ]
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))

    sent = 0
    failed = 0
    for notification in queryset:
        deliver(notification)
        if notification.status == PushNotification.Status.SENT:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


def flush_due_retries() -> None:
    """Best-effort drain of the retry backlog, throttled per process.

    Called by queue_push() so retries ride along with the next notification
    event instead of needing a timer of their own. Never raises: a stuck
    retry must not stop a fresh notification from going out.
    """
    global _last_retry_flush

    now = time.monotonic()
    with _retry_flush_lock:
        if now - _last_retry_flush < RETRY_FLUSH_INTERVAL_SEC:
            return
        _last_retry_flush = now

    try:
        result = dispatch_pending()
        if result["sent"] or result["failed"]:
            logger.info("push.retry_flush %s", result)
    except Exception:
        logger.exception("push.retry_flush_failed")


def queue_push(
    *,
    user,
    notification_type: str,
    title: str,
    body: str,
    url: str = "/",
) -> PushNotification | None:
    """Create a PushNotification and attempt delivery.

    Drains any due retries first, so the retry backlog is worked by the
    notification flow rather than by a recurring job.

    Returns None when the user has opted out of ``notification_type`` — no
    row is written so the audit trail only holds notifications we intended
    to deliver.
    """
    flush_due_retries()
    if not _preference_allows(user, notification_type):
        logger.info(
            "push.skipped_by_preference",
            extra={"user_id": user.id, "notification_type": notification_type},
        )
        return None
    notification = PushNotification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title[:128],
        body=body,
        url=url[:512],
    )
    try:
        deliver(notification)
    except Exception as exc:
        # Never let a push failure break the caller — the email path is the
        # authoritative delivery channel. Row remains in FAILED for the
        # dispatch_pending() worker to retry.
        logger.exception("push.deliver_failed: %s", exc)
    return notification


def push_now(
    *,
    user,
    notification_type: str,
    title: str,
    body: str,
    url: str = "/",
) -> PushNotification:
    """Push once to the user's reachable devices; never retry.

    The caller has already decided push is the channel (and checked the
    user's preference). Returns the row: SENT if any device took it,
    FELL_BACK otherwise — the caller then emails. A failed push is not
    retried because the email has gone by then, and a late push would
    deliver the same news twice.
    """
    notification = PushNotification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title[:128],
        body=body,
        url=url[:512],
    )
    if not push_configured():
        error = "VAPID keys not configured"
    else:
        try:
            error = _send_to(notification, list(PushSubscription.objects.reachable(user)))
        except Exception as exc:
            logger.exception("push.push_now_failed")
            error = str(exc) or exc.__class__.__name__

    if error:
        notification.mark_fell_back(error)
        notification.save(
            update_fields=[
                "status",
                "attempt_count",
                "last_attempted_at",
                "next_attempt_at",
                "last_error",
            ]
        )
    else:
        notification.attempt_count += 1
        notification.last_attempted_at = timezone.now()
        notification.mark_sent()
        notification.save(
            update_fields=[
                "status",
                "attempt_count",
                "last_attempted_at",
                "sent_at",
                "next_attempt_at",
                "last_error",
            ]
        )
    return notification
