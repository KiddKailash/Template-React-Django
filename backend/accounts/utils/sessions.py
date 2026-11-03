"""What Settings shows under Devices, and signing the others out."""

from __future__ import annotations

from ..models import DeviceSession
from ..serializers import DeviceSessionSerializer


def session_overview(user, current_id: str | None) -> dict:
    """The payload of ``GET /api/sessions/``: live sessions, the caller's first."""
    sessions = sorted(
        DeviceSession.objects.live().filter(user=user),
        key=lambda s: (str(s.pk) != current_id, -s.last_seen_at.timestamp()),
    )
    data = DeviceSessionSerializer(sessions, many=True, context={"current_id": current_id}).data
    return {"sessions": data}


def revoke_others(user, current_id: str | None) -> int:
    """End every live session but the caller's (all of them if it has none)."""
    qs = DeviceSession.objects.filter(user=user)
    if current_id:
        qs = qs.exclude(pk=current_id)
    return qs.revoke()
