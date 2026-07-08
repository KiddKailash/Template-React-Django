from __future__ import annotations

from django.contrib import admin

from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "date", "created_at", "cost_usd")
    list_filter = ("role", "date")
    search_fields = ("content", "user__username")
    readonly_fields = (
        "user",
        "date",
        "role",
        "content",
        "agent_run",
        "model_used",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "created_at",
    )
