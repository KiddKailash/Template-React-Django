"""JWT authentication that also requires the token's device session to be live."""

from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from .models import DeviceSession
from .utils.devices import client_ip

SESSION_CLAIM = "sid"


def live_session_for(token, user) -> DeviceSession:
    """The live session a validated token belongs to, or AuthenticationFailed.

    Tokens with no ``sid`` are refused, so every token in use can be listed
    and ended from Settings.
    """
    sid = token.get(SESSION_CLAIM)
    if not sid:
        raise AuthenticationFailed("Signed out. Please sign in again.", code="no_session")
    try:
        return DeviceSession.objects.live().get(pk=sid, user_id=user.pk)
    except (DeviceSession.DoesNotExist, ValueError, TypeError):
        raise AuthenticationFailed("This device was signed out.", code="session_revoked") from None


class SessionJWTAuthentication(JWTAuthentication):
    """SimpleJWT, plus a check that the token's ``DeviceSession`` is live.

    One indexed primary-key read per request is the price of sign-out taking
    effect immediately. Activity is recorded on the session at most once per
    ``DeviceSession.TOUCH_INTERVAL``. The session is exposed to views as
    ``request.auth.device_session``.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        session = live_session_for(token, user)
        session.touch(ip_address=client_ip(request))
        token.device_session = session
        return user, token


def current_session_id(request) -> str | None:
    """The caller's session id, or None (unauthenticated, or a test client
    using ``force_authenticate`` with no token)."""
    token = getattr(request, "auth", None)
    if token is None:
        return None
    session = getattr(token, "device_session", None)
    if session is not None:
        return str(session.pk)
    try:
        sid = token.get(SESSION_CLAIM)
    except AttributeError:
        return None
    return str(sid) if sid else None
