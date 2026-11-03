"""Deliver one notification on one channel: push if the user is around, else email.

Ported from LLMStockAnalysis. Every user-facing notification goes through
``notify()``. It sends **one** of the two, never both:

  1. **Push**, when the user has a device that is subscribed and has had the
     app open within ``PushSubscription.ACTIVE_WINDOW`` (14 days): someone
     using the app is better served on the device in their hand.
  2. **Email**, when no device qualifies, when push is not configured on the
     server, or when the push reached none of the devices it was sent to. A
     dead subscription never costs the user the notification.

Nothing is sent when the user opted out of the type (utils/preferences.py),
or when email is the channel and the user has no address.

``choose_channel()`` is the same decision without sending (for dry runs and
the Settings page).

Example::

    from notifications.utils.delivery import Email, notify

    notify(
        user=user,
        notification_type=PushNotification.Type.GENERAL,
        title="Report ready",
        body="Your weekly report is ready.",
        url="/reports/42",
        email=Email(subject="Your weekly report", text="It is ready: ..."),
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from ..models import PushNotification, PushSubscription
from .dispatcher import _preference_allows, push_configured, push_now
from .preferences import email_address

logger = logging.getLogger(__name__)


class Channel(StrEnum):
    PUSH = "push"
    EMAIL = "email"


@dataclass(frozen=True)
class Email:
    """An email, rendered only if email turns out to be the channel.

    ``template`` (optional) is an HTML template rendered with ``context`` plus
    ``frontend_url``; without one the email is plain text.
    """

    subject: str
    text: str
    template: str | None = None
    context: dict = field(default_factory=dict)

    def html(self) -> str | None:
        if not self.template:
            return None
        return render_to_string(
            self.template,
            {
                "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:5173"),
                **self.context,
            },
        )


def choose_channel(user) -> Channel | None:
    """The channel ``notify()`` would try first, or None if neither can reach them."""
    if push_configured() and PushSubscription.objects.reachable(user).exists():
        return Channel.PUSH
    return Channel.EMAIL if email_address(user) else None


def notify(
    *,
    user,
    title: str,
    body: str,
    email: Email,
    url: str = "/",
    notification_type: str = PushNotification.Type.GENERAL,
) -> Channel | None:
    """Send the notification on one channel. Returns the channel that took it.

    Never raises: a failed email is logged and reported as None, so a batch
    job notifying many users carries on to the next one.
    """
    if not _preference_allows(user, notification_type):
        return None

    if choose_channel(user) == Channel.PUSH:
        pushed = push_now(
            user=user,
            notification_type=notification_type,
            title=title,
            body=body,
            url=url,
        )
        if pushed.status == PushNotification.Status.SENT:
            return Channel.PUSH
        logger.info("notify.push_fell_back_to_email user=%s error=%s", user.pk, pushed.last_error)

    address = email_address(user)
    if not address:
        return None
    try:
        send_mail(
            subject=email.subject,
            message=email.text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[address],
            html_message=email.html(),
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to email %s (%s): %s", address, notification_type, exc)
        return None
    return Channel.EMAIL
