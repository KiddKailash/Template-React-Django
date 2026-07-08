"""Chat history.

Per-user: `user` FK is required. `date` is the UTC calendar day the
message was sent, indexed so the UI can scope a visible thread to
"today" and a cleanup job can range-scan old rows.

Cost/token fields mirror `AgentRun` so a chat message row is
independently readable in the admin without joining. The optional
`agent_run` FK points at the run that produced the assistant message
(null for user messages).
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from llm.models import AgentRun


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    date = models.DateField()
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    agent_run = models.ForeignKey(
        AgentRun,
        on_delete=models.SET_NULL,
        related_name="chat_messages",
        null=True,
        blank=True,
    )
    model_used = models.CharField(max_length=128, blank=True, default="")
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.role}@{self.date} u={self.user_id}"
