"""What Settings shows under Devices: live sessions and where notifications go."""

from __future__ import annotations

from notifications.models import PushSubscription
from notifications.utils.delivery import choose_channel
from notifications.utils.preferences import email_address

from ..models import DeviceSession
from ..serializers import DeviceSessionSerializer


def push_state_by_session(user) -> dict[str, str]:
    """Session id → "receiving" (a reachable push subscription) or "idle"
    (subscribed, but not seen inside the activity window, so emailed)."""
    reachable = set(
        PushSubscription.objects.reachable(user)
        .filter(session__isnull=False)
        .values_list("session_id", flat=True)
    )
    state = {}
    for session_id in (
        PushSubscription.objects.filter(user=user, active=True, session__isnull=False)
        .values_list("session_id", flat=True)
        .distinct()
    ):
        state[str(session_id)] = "receiving" if session_id in reachable else "idle"
    return state


def session_overview(user, current_id: str | None) -> dict:
    """The payload of ``GET /api/sessions/``.

    ``notifications.channel`` is what the next notification would use ("push",
    "email" or None), from the same ``choose_channel`` the senders call, so the
    page can never disagree with what actually goes out. ``unlinked_devices``
    counts reachable devices whose session is unknown (their session row was
    swept); they receive pushes but are not listed until they next open the app.
    """
    push_state = push_state_by_session(user)
    sessions = sorted(
        DeviceSession.objects.live().filter(user=user),
        key=lambda s: (str(s.pk) != current_id, -s.last_seen_at.timestamp()),
    )
    data = DeviceSessionSerializer(
        sessions, many=True, context={"current_id": current_id, "push_state": push_state}
    ).data
    listed = {str(s.pk) for s in sessions}
    channel = choose_channel(user)
    return {
        "sessions": data,
        "notifications": {
            "channel": str(channel) if channel else None,
            "email": email_address(user),
            "devices": [
                sid for sid, state in push_state.items() if state == "receiving" and sid in listed
            ],
            "unlinked_devices": PushSubscription.objects.reachable(user)
            .filter(session__isnull=True)
            .count(),
        },
    }


def revoke_others(user, current_id: str | None) -> int:
    """End every live session but the caller's (all of them if it has none)."""
    qs = DeviceSession.objects.filter(user=user)
    if current_id:
        qs = qs.exclude(pk=current_id)
    return qs.revoke()
