"""Per-token sliding-window rate limit.

Computed from the `McpCallLog` table rather than an in-memory counter
because the backend may be multi-worker (gunicorn) — an in-memory
bucket would let a client multiply its quota by the worker count. The
audit log is already append-only and indexed on `(token, -timestamp)`,
so the lookup is cheap.

`rate_limit_per_minute=0` on a token disables the rate limit (use
sparingly — only for trusted in-network clients).
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from ..models import McpCallLog, McpToken


def is_rate_limited(token: McpToken) -> bool:
    """Return True if the token has exceeded its per-minute quota."""
    if token.rate_limit_per_minute <= 0:
        return False
    one_minute_ago = timezone.now() - timedelta(minutes=1)
    recent = McpCallLog.objects.filter(
        token=token,
        timestamp__gte=one_minute_ago,
    ).count()
    return recent >= token.rate_limit_per_minute
