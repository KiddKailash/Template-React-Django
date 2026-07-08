"""Monthly cost cap for LLM spend.

Simple guard so a runaway agent (or a webhook flood) can't burn through
the OpenRouter budget. Configured via `OPENROUTER_MONTHLY_USD_CAP` in
settings; set to 0 to disable.

The cap is enforced against the sum of `AgentRun.cost_usd` in the
current UTC month. Each LLM caller MUST:

  1. Call `precheck_only()` before the LLM request. Raises
     `CostCapExceededError` if the cap is already blown.
  2. Call `record_after_call()` after a successful LLM request so the
     spend counts toward the cap.

This is not a hard atomic guarantee across concurrent workers — two
requests firing at the same instant can both pass the precheck. That's
acceptable for a template: the cap is a budget alarm, not a payment
processor. If you need atomic accounting, replace the sum-query with a
row-level lock on a `MonthlyBudget` row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum

from ..models import AgentRun


class CostCapExceededError(RuntimeError):
    """Raised when the monthly OpenRouter spend cap has been reached."""


def _month_start() -> datetime:
    now = datetime.now(tz=UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_to_date_usd() -> Decimal:
    """Sum of `AgentRun.cost_usd` for the current UTC month."""
    agg = AgentRun.objects.filter(started_at__gte=_month_start()).aggregate(total=Sum("cost_usd"))
    return Decimal(agg["total"] or 0)


def precheck_only() -> None:
    """Raise `CostCapExceededError` if the month-to-date spend already blew the cap."""
    cap = Decimal(str(getattr(settings, "OPENROUTER_MONTHLY_USD_CAP", 0) or 0))
    if cap <= 0:
        return
    spent = month_to_date_usd()
    if spent >= cap:
        raise CostCapExceededError(f"monthly LLM spend ${spent} has reached cap ${cap}")


def record_after_call(*, prompt_tokens: int, completion_tokens: int, cost_usd: Decimal) -> None:
    """Post-call hook — no-op today.

    Kept as a stable seam because per-model accounting or a
    Prometheus/Slack alert almost always gets bolted on later, and the
    call site is easier to grep for than a git-blame trail.
    """
    # Intentionally empty: `AgentRun.cost_usd` is the source of truth.
    _ = (prompt_tokens, completion_tokens, cost_usd)
