"""Per-user, per-type opt-outs: the one place push AND email ask "may I?".

The template ships no preference model, so everything is allowed. Wire your
own here (LLMStockAnalysis keeps `notify_*` booleans on a UserPreference row
and maps each notification type to one). Both channels call this, so push and
email can never disagree about an opt-out.
"""

from __future__ import annotations


def allows(user, notification_type: str) -> bool:
    """Whether ``user`` wants notifications of ``notification_type``."""
    return True


def email_address(user) -> str:
    """Where the email fallback goes; empty means "do not email"."""
    return (getattr(user, "email", "") or "").strip()
