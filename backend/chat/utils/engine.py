"""Chat answerer.

One turn runs in phases, so the JSON endpoint and the streaming endpoint
(`chat/views.py`, `llm/utils/sse.py`) share every line of it:

  start_turn()   request thread: cost-cap precheck, save the user message,
                 open the AgentRun. Raises CostCapExceededError when capped.
  run_turn()     any thread: the LLM tool loop only (no database writes),
                 reporting progress through `on_event`.
  finish_turn()  save cost, tool traces and the assistant message; close the
                 AgentRun. Runs once per successful turn.
  fail_turn()    mark the AgentRun FAILED (it used to stay RUNNING forever).

`answer()` runs them back to back. Streaming is the default client path:
a turn can take minutes, and a silent request is cut off by nginx (60 s)
and Cloudflare (~100 s) long before that.

When the monthly cost cap trips, the user message is still saved and an
assistant message explains the cap, so both endpoints return the normal shape
rather than an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from llm.models import AgentRun, LLMToolCall
from llm.utils.cost_cap import CostCapExceededError, precheck_only, record_after_call
from llm.utils.openrouter import LLMResponse
from llm.utils.prompts import DEFAULT_SYSTEM
from llm.utils.tool_loop import OnEvent, ToolCallTrace, chat_with_tools
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


@dataclass
class TurnContext:
    user: AbstractBaseUser
    today: object
    question: str
    user_message: ChatMessage
    agent_run: AgentRun
    history: list[dict[str, str]]
    system: str = DEFAULT_SYSTEM


@dataclass
class TurnOutcome:
    response: LLMResponse
    traces: list[ToolCallTrace]


def start_turn(
    *, user: AbstractBaseUser, question: str, system: str = DEFAULT_SYSTEM
) -> TurnContext:
    """Save the user message and open the run. Raises CostCapExceededError (after
    saving the user message and a capped reply: see `capped_reply`)."""
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
    return TurnContext(user, today, question, user_msg, agent_run, history, system)


def capped_reply(ctx: TurnContext, exc: CostCapExceededError) -> AnswerResult:
    """Close the run as CAPPED and answer with an explanation."""
    ctx.agent_run.status = AgentRun.Status.CAPPED
    ctx.agent_run.error = str(exc)[:1024]
    ctx.agent_run.completed_at = timezone.now()
    ctx.agent_run.save(update_fields=["status", "error", "completed_at"])
    assistant = ChatMessage.objects.create(
        user=ctx.user,
        date=ctx.today,
        role=ChatMessage.Role.ASSISTANT,
        content=(
            "I've hit this month's spending cap, so I can't run another LLM call "
            f"until next month. ({exc})"
        ),
        agent_run=ctx.agent_run,
    )
    return AnswerResult(ctx.user_message, assistant, cost_capped=True)


def run_turn(ctx: TurnContext, on_event: OnEvent | None = None) -> TurnOutcome:
    """The LLM tool loop. Touches no database rows itself (tools may read)."""
    resp, traces = chat_with_tools(
        system=ctx.system,
        user=ctx.question,
        history=ctx.history,
        tools=available_tools(),
        model="default",
        on_event=on_event,
    )
    return TurnOutcome(resp, traces)


def finish_turn(ctx: TurnContext, outcome: TurnOutcome) -> AnswerResult:
    """Record cost and traces, save the answer, close the run as COMPLETED."""
    resp, traces = outcome.response, outcome.traces
    record_after_call(
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        cost_usd=resp.cost_usd,
    )
    if traces:
        LLMToolCall.objects.bulk_create(
            [
                LLMToolCall(
                    agent_run=ctx.agent_run,
                    turn_index=t.turn,
                    tool_name=t.name,
                    arguments=t.arguments if isinstance(t.arguments, dict) else {},
                    result=t.result,
                    error=t.error or "",
                )
                for t in traces
            ]
        )

    run = ctx.agent_run
    run.status = AgentRun.Status.COMPLETED
    run.output = resp.content
    run.model_used = resp.model
    run.prompt_tokens = resp.prompt_tokens
    run.completion_tokens = resp.completion_tokens
    run.cost_usd = resp.cost_usd
    run.completed_at = timezone.now()
    run.save(
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
        user=ctx.user,
        date=ctx.today,
        role=ChatMessage.Role.ASSISTANT,
        content=resp.content,
        agent_run=run,
        model_used=resp.model,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        cost_usd=resp.cost_usd,
    )
    return AnswerResult(ctx.user_message, assistant)


def fail_turn(ctx: TurnContext, error: BaseException) -> None:
    """Close the run as FAILED. Called from the worker thread when streaming,
    so it updates by primary key rather than saving the shared instance."""
    AgentRun.objects.filter(pk=ctx.agent_run.pk).update(
        status=AgentRun.Status.FAILED,
        error=f"{type(error).__name__}: {error}"[:1024],
        completed_at=timezone.now(),
    )


def answer(*, user: AbstractBaseUser, question: str, system: str = DEFAULT_SYSTEM) -> AnswerResult:
    """The whole turn in one call (the JSON endpoint). Re-raises a failed turn
    after marking its run FAILED."""
    ctx = start_turn(user=user, question=question, system=system)
    try:
        precheck_only()
    except CostCapExceededError as exc:
        return capped_reply(ctx, exc)
    try:
        outcome = run_turn(ctx)
    except Exception as exc:
        fail_turn(ctx, exc)
        raise
    return finish_turn(ctx, outcome)
