"""Built-in read-only tools available to every project.

These are intentionally domain-neutral — they only touch Django's
built-in auth tables. Real projects should add their own tools in a
sibling module (e.g. `myapp/utils/tools.py`) that imports and uses
`@read_only_tool`, then import that module from `myapp.apps.<Config>.ready()`
so the decorators run at boot.

All handlers here are pure reads — the boot-time validator statically
rejects any call to `.save() / .delete() / .create() / .update() /
.bulk_create() / .bulk_update() / .get_or_create() / .update_or_create()`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.contrib.auth import get_user_model

from .decorator import read_only_tool

MAX_ROWS = 200


@read_only_tool(
    name="current_time_utc",
    description=(
        "Return the current UTC time as an ISO-8601 timestamp. Use this "
        "when the user asks about relative time ('what day is it', "
        "'how long ago was X') or when a computation depends on now."
    ),
)
def current_time_utc() -> dict[str, Any]:
    return {"now_utc": datetime.now(tz=UTC).isoformat()}


@read_only_tool(
    name="list_recent_users",
    description=(
        "Return up to `limit` users, newest-first. Fields: id, username, "
        "email, date_joined (ISO), is_staff. Use this when the user "
        "asks about recent sign-ups or which users exist. `limit` is "
        "clamped to 200."
    ),
)
def list_recent_users(limit: int) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), MAX_ROWS))
    User = get_user_model()
    qs = User.objects.order_by("-date_joined")[:n]
    return [
        {
            "id": u.pk,
            "username": u.get_username(),
            "email": getattr(u, "email", "") or "",
            "date_joined": u.date_joined.isoformat() if getattr(u, "date_joined", None) else None,
            "is_staff": bool(getattr(u, "is_staff", False)),
        }
        for u in qs
    ]


@read_only_tool(
    name="count_users_since",
    description=(
        "Return the number of users whose `date_joined` is within the "
        "last `days` days. Pass days=0 to count all users."
    ),
)
def count_users_since(days: int) -> dict[str, Any]:
    User = get_user_model()
    qs = User.objects.all()
    if days > 0:
        cutoff = datetime.now(tz=UTC) - timedelta(days=int(days))
        qs = qs.filter(date_joined__gte=cutoff)
    return {"count": qs.count(), "window_days": int(days)}
