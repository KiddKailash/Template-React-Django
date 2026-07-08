"""High-level agent helpers.

`run_agent()` is the recommended entry point for anything that needs a
persisted, cost-accounted LLM call with the full tool loop and audit
trail — chat messages, webhook triggers, cron jobs.

Callers that only need a raw LLM completion can use
`llm.utils.tool_loop.chat_with_tools()` directly, but they lose the
`AgentRun` row and cost-cap enforcement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.utils import timezone

from ..models import AgentRun, LLMToolCall
from .cost_cap import CostCapExceededError, precheck_only, record_after_call
from .openrouter import LLMResponse, Model
from .tool_loop import ToolCallTrace, chat_with_tools
from .tools import ToolSpec

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Outcome of `run_agent()`.

    `status` mirrors `AgentRun.Status`. On COMPLETED, `response` is the
    LLM's final message and `traces` contains every tool dispatch. On
    CAPPED or FAILED, `response` is None and `error` explains why.
    """

    agent_run: AgentRun
    status: str
    response: LLMResponse | None = None
    traces: list[ToolCallTrace] | None = None
    error: str = ""


def run_agent(
    *,
    system: str,
    user: str,
    kind: str = AgentRun.Kind.AGENT,
    trigger_type: str = "",
    trigger_data: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    tools: list[ToolSpec] | None = None,
    model: Model = "default",
) -> AgentResult:
    """Run a full agent turn with persistence, cost cap, and audit trail.

    Persists an `AgentRun` up front (`status=RUNNING`) so concurrent
    workers can see the in-flight call. Writes one `LLMToolCall` per
    tool dispatch. Updates the `AgentRun` with the final status +
    cost/token totals when the loop returns.
    """
    trigger_data = dict(trigger_data or {})
    agent_run = AgentRun.objects.create(
        kind=kind,
        trigger_type=trigger_type,
        trigger_data=trigger_data,
        status=AgentRun.Status.RUNNING,
    )

    logger.info(
        "agent.run_agent.start",
        extra={"kind": kind, "trigger_type": trigger_type, "agent_run_id": agent_run.pk},
    )

    try:
        precheck_only()
        response, traces = chat_with_tools(
            system=system,
            user=user,
            history=history,
            tools=tools,
            model=model,
        )
        record_after_call(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
        )
    except CostCapExceededError as exc:
        logger.warning("agent.run_agent.capped", extra={"reason": str(exc)})
        agent_run.status = AgentRun.Status.CAPPED
        agent_run.error = str(exc)[:1024]
        agent_run.completed_at = timezone.now()
        agent_run.save(update_fields=["status", "error", "completed_at"])
        return AgentResult(agent_run=agent_run, status=agent_run.status, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent.run_agent.failed")
        agent_run.status = AgentRun.Status.FAILED
        agent_run.error = f"{type(exc).__name__}: {exc}"[:1024]
        agent_run.completed_at = timezone.now()
        agent_run.save(update_fields=["status", "error", "completed_at"])
        return AgentResult(agent_run=agent_run, status=agent_run.status, error=str(exc))

    if traces:
        LLMToolCall.objects.bulk_create(
            [
                LLMToolCall(
                    agent_run=agent_run,
                    turn_index=t.turn,
                    tool_name=t.name,
                    arguments=t.arguments if isinstance(t.arguments, dict) else {},
                    result=t.result,
                    error=t.error or "",
                )
                for t in traces
            ]
        )

    agent_run.status = AgentRun.Status.COMPLETED
    agent_run.output = response.content
    agent_run.model_used = response.model
    agent_run.prompt_tokens = response.prompt_tokens
    agent_run.completion_tokens = response.completion_tokens
    agent_run.cost_usd = Decimal(str(response.cost_usd))
    agent_run.completed_at = timezone.now()
    agent_run.save(
        update_fields=[
            "status",
            "output",
            "model_used",
            "prompt_tokens",
            "completion_tokens",
            "cost_usd",
            "completed_at",
        ]
    )

    logger.info(
        "agent.run_agent.completed",
        extra={
            "agent_run_id": agent_run.pk,
            "cost_usd": float(response.cost_usd),
            "tool_calls": len(traces),
        },
    )

    return AgentResult(
        agent_run=agent_run,
        status=agent_run.status,
        response=response,
        traces=traces,
    )
