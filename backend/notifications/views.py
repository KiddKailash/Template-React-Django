"""DRF endpoints for the Web Push surface (ported from LLMStockAnalysis).

Routes (mounted at /api/notifications/):

  GET  vapid-public-key/   public VAPID key for browser registration ("" = push off)
  POST subscribe/          upsert this browser's PushSubscription (scoped to caller)
  POST unsubscribe/        mark a subscription inactive
  POST seen/               this device has the app open (keeps it on push, not email)
  POST test/               push a test notification to the caller's own devices

Not ported: LLMStockAnalysis's `<id>/read/`. Its service worker calls it with
`credentials: 'same-origin'`, but the API authenticates with a bearer token,
not a cookie, so that request is always refused.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.authentication import current_session_id

from .models import PushNotification, PushSubscription
from .serializers import PushSubscriptionSerializer
from .throttling import PushTestRateThrottle
from .utils.dispatcher import push_configured, push_now


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def vapid_public_key(_request):
    """Public VAPID key; an empty string means push is not configured on this server."""
    return Response({"public_key": getattr(settings, "WEB_PUSH_VAPID_PUBLIC_KEY", "") or ""})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscribe(request):
    """Upsert the caller's Web Push subscription.

    Re-registering the same endpoint refreshes the keys. If a different user
    hands us the same endpoint it is rebound: a browser owns one subscription
    per origin, so a collision means the previous owner signed out on this
    device.
    """
    serializer = PushSubscriptionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    endpoint = serializer.validated_data["endpoint"]
    keys = serializer.validated_data["keys"]
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:256]

    obj, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": keys["p256dh"],
            "auth": keys["auth"],
            "user_agent": user_agent,
            "active": True,
            # Subscribing is the device in use, so it qualifies for push now.
            "last_seen_at": timezone.now(),
            "session_id": current_session_id(request),
        },
    )
    return Response({"id": obj.id, "created": created}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def seen(request):
    """Record that the caller has the app open on the device owning ``endpoint``.

    The write is coalesced to one per ``SEEN_RESOLUTION``. Answers
    ``{"active": false}`` when the server holds no live subscription for this
    endpoint under this user (expired, or its session was signed out), so the
    client can re-register it.
    """
    endpoint = request.data.get("endpoint")
    if not endpoint:
        return Response({"detail": "endpoint required"}, status=status.HTTP_400_BAD_REQUEST)
    mine = PushSubscription.objects.filter(user=request.user, endpoint=endpoint, active=True)
    now = timezone.now()
    sid = current_session_id(request)
    stale = Q(last_seen_at__isnull=True) | Q(
        last_seen_at__lt=now - PushSubscription.SEEN_RESOLUTION
    )
    if sid:
        # Re-link when this device signed in again since it subscribed.
        stale |= ~Q(session_id=sid) | Q(session__isnull=True)
    mine.filter(stale).update(last_seen_at=now, **({"session_id": sid} if sid else {}))
    return Response({"active": mine.exists()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unsubscribe(request):
    endpoint = request.data.get("endpoint")
    if not endpoint:
        return Response({"detail": "endpoint required"}, status=status.HTTP_400_BAD_REQUEST)
    updated = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).update(
        active=False
    )
    return Response({"unsubscribed": updated})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([PushTestRateThrottle])
def test_push(request):
    """Push a test notification to the caller's own reachable devices, once.

    Works in production on purpose: it is how you check a deployment's VAPID
    keys and a phone's subscription end to end. Throttled per user.
    """
    if not push_configured():
        return Response(
            {"detail": "Push is not configured on this server."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    notification = push_now(
        user=request.user,
        notification_type=PushNotification.Type.TEST,
        title="Test notification",
        body="Push notifications are working on this device.",
        url="/settings",
    )
    delivered = notification.dispatches.filter(outcome="delivered").count()
    return Response(
        {
            "status": notification.status,
            "delivered": delivered,
            "error": notification.last_error,
        },
        status=status.HTTP_200_OK if delivered else status.HTTP_502_BAD_GATEWAY,
    )
