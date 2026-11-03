"""Device sessions: one row per sign-in, so a user can see and end them.

The API authenticates with SimpleJWT, which on its own is stateless: a token
is valid until it expires and nothing on the server can take it back. A
``DeviceSession`` is the server-side half that makes sign-out real:

  - signing in creates one, and its id rides in every token as the ``sid``
    claim (refresh and access alike; SimpleJWT copies custom claims across);
  - ``SessionJWTAuthentication`` rejects any token whose session is revoked
    or expired, on every request, so revoking takes effect immediately rather
    than when the 24-hour access token runs out;
  - refreshing extends the session to the refresh token's new expiry, and a
    revoked session cannot be refreshed.

Ported from LLMStockAnalysis (accounts/), minus its push-notification link.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def session_lifetime() -> timedelta:
    """A session lives as long as the refresh token that carries it."""
    return settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


class DeviceSessionQuerySet(models.QuerySet):
    def live(self):
        return self.filter(revoked_at__isnull=True, expires_at__gt=timezone.now())

    def revoke(self) -> int:
        """End these sessions. Returns how many were live (ended ones are skipped).

        Extend here if a device holds anything else that should stop with its
        session (LLMStockAnalysis deactivates the device's push subscriptions).
        """
        return self.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


class DeviceSession(models.Model):
    """One signed-in device (strictly: one sign-in on one browser)."""

    # last_seen_at / ip_address are only rewritten when older than this, so an
    # active tab costs one write per interval, not one per request.
    TOUCH_INTERVAL = timedelta(minutes=5)
    # Ended and expired rows are kept this long (the list never shows them),
    # then swept on the user's next sign-in.
    RETENTION = timedelta(days=30)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_sessions"
    )
    user_agent = models.CharField(max_length=512, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = DeviceSessionQuerySet.as_manager()

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [models.Index(fields=["user", "revoked_at", "expires_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"DeviceSession({self.user_id}, {self.id})"

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()

    @classmethod
    def start(cls, user, *, user_agent: str = "", ip_address: str | None = None):
        """Open a session for a fresh sign-in, sweeping long-dead rows first."""
        cutoff = timezone.now() - cls.RETENTION
        cls.objects.filter(user=user).filter(
            models.Q(revoked_at__lt=cutoff) | models.Q(expires_at__lt=cutoff)
        ).delete()
        return cls.objects.create(
            user=user,
            user_agent=user_agent[:512],
            ip_address=ip_address,
            expires_at=timezone.now() + session_lifetime(),
        )

    def touch(self, *, ip_address: str | None = None, extend: bool = False) -> None:
        """Record activity; with ``extend``, push expiry out (a token refresh)."""
        now = timezone.now()
        fields = {}
        if extend:
            fields["expires_at"] = now + session_lifetime()
        if extend or now - self.last_seen_at >= self.TOUCH_INTERVAL:
            fields["last_seen_at"] = now
        if ip_address and ip_address != self.ip_address:
            fields["ip_address"] = ip_address
        if not fields:
            return
        DeviceSession.objects.filter(pk=self.pk).update(**fields)
        for name, value in fields.items():
            setattr(self, name, value)
