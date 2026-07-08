"""Persistence for the LLM harness.

`AgentRun` — one row per top-level agent invocation (chat turn, cron
trigger, webhook trigger). Records the trigger, status, token/cost
accounting, and the final output.

`LLMToolCall` — one row per tool dispatch across all turns of an
`AgentRun`, kept for audit + replay.

Both models are generic. Domain-specific tables (a briefing letter, a
report, etc.) should live in the app that owns that concept and carry
their own nullable FK to `AgentRun` when the agent produced them.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models


class AgentRun(models.Model):
    """Unified audit row for every agent-loop invocation.

    `trigger_type` is intentionally free-text so new sources (webhooks,
    cron jobs, chat turns) don't need a schema change to be recorded.
    Convention: `<subsystem>:<event>` — e.g. `chat:message`,
    `cron:daily`, `webhook:stripe.checkout.completed`.
    """

    class Kind(models.TextChoices):
        CHAT = "chat", "Chat"
        AGENT = "agent", "Agent"
        CRON = "cron", "Cron"
        WEBHOOK = "webhook", "Webhook"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CAPPED = "capped", "Capped"
        SUPPRESSED = "suppressed", "Suppressed"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    trigger_type = models.CharField(max_length=64, blank=True, default="")
    trigger_data = models.JSONField(default=dict, blank=True)
    output = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    suppressed_reason = models.CharField(max_length=64, blank=True, default="")
    model_used = models.CharField(max_length=128, blank=True, default="")
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal("0"))
    error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["kind", "-started_at"]),
            models.Index(fields=["trigger_type", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover — admin only
        label = self.trigger_type or self.kind
        return f"AgentRun({label}, {self.status}, {self.started_at:%Y-%m-%d %H:%M})"


class LLMToolCall(models.Model):
    """One row per tool dispatch inside an AgentRun."""

    agent_run = models.ForeignKey(
        AgentRun,
        on_delete=models.CASCADE,
        related_name="tool_calls",
        null=True,
        blank=True,
    )
    turn_index = models.PositiveIntegerField()
    tool_name = models.CharField(max_length=120)
    arguments = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["agent_run_id", "turn_index"]
        indexes = [
            models.Index(fields=["agent_run", "turn_index"]),
            models.Index(fields=["tool_name", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.tool_name}#{self.turn_index}"
