"""Chat answerer.

Synchronous: the request blocks while the LLM tool loop runs. This is
fine for the template's single-server layout; if you need
concurrent-safe non-blocking chat, put the loop behind a task queue
(Django-Q, Celery, RQ) and stream results via SSE.

When the monthly cost cap trips, we still persist the user message and
write an assistant message explaining the cap so the API returns a
normal shape rather than a 500.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from llm.models import AgentRun, LLMToolCall
from llm.utils.cost_cap import CostCapExceededError, precheck_only, record_after_call
from llm.utils.prompts import DEFAULT_SYSTEM
from llm.utils.tool_loop import chat_with_tools
from llm.utils.tools import available_tools

from ..models import ChatMessage

CHAT_HISTORY_MAX_MESSAGES = 40


@dataclass
class AnswerResult:
    user_message: ChatMessage
    assistant_message: ChatMessage
    cost_capped: bool = False


def _today() -> datetime:
    """UTC calendar day. Override if your app needs a user-local timezone."""
    return datetime.now(tz=UTC).date()


def _today_history(
    user: AbstractBaseUser, today, exclude_id: int | None = None
) -> list[dict[str, str]]:
    qs = ChatMessage.objects.filter(user=user, date=today).order_by("created_at")
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    rows = list(qs[:CHAT_HISTORY_MAX_MESSAGES])
    return [{"role": m.role, "content": m.content} for m in rows]


def answer(*, user: AbstractBaseUser, question: str, system: str = DEFAULT_SYSTEM) -> AnswerResult:
    """Persist the user turn, run the tool loop, persist the assistant turn."""
    today = _today()

    user_msg = ChatMessage.objects.create(
        user=user,
        date=today,
        role=ChatMessage.Role.USER,
        content=question,
    )
    history = _today_history(user, today, exclude_id=user_msg.pk)

    agent_run = AgentRun.objects.create(
        kind=AgentRun.Kind.CHAT,
        trigger_type="chat:message",
        trigger_data={"user_id": user.pk, "user_message_id": user_msg.pk},
        status=AgentRun.Status.RUNNING,
    )

    try:
        precheck_only()
        resp, traces = chat_with_tools(
            system=system,
            user=question,
            history=history,
            tools=available_tools(),
            model="default",
        )
        record_after_call(
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            cost_usd=resp.cost_usd,
        )
    except CostCapExceededError as exc:
        agent_run.status = AgentRun.Status.CAPPED
        agent_run.error = str(exc)[:1024]
        agent_run.completed_at = timezone.now()
        agent_run.save(update_fields=["status", "error", "completed_at"])
        assistant = ChatMessage.objects.create(
            user=user,
            date=today,
            role=ChatMessage.Role.ASSISTANT,
            content=(
                "I've hit this month's spending cap, so I can't run another LLM call "
                f"until next month. ({exc})"
            ),
            agent_run=agent_run,
        )
        return AnswerResult(user_msg, assistant, cost_capped=True)

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
    agent_run.output = resp.content
    agent_run.model_used = resp.model
    agent_run.prompt_tokens = resp.prompt_tokens
    agent_run.completion_tokens = resp.completion_tokens
    agent_run.cost_usd = resp.cost_usd
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

    assistant = ChatMessage.objects.create(
        user=user,
        date=today,
        role=ChatMessage.Role.ASSISTANT,
        content=resp.content,
        agent_run=agent_run,
        model_used=resp.model,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        cost_usd=resp.cost_usd,
    )
    return AnswerResult(user_msg, assistant)
