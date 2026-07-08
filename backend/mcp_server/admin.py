"""Admin surface for MCP tokens + call log.

Tokens are listed with their prefix (never the secret), state, and
usage telemetry. The `revoke_selected` action flips `revoked_at` so a
compromised token can be killed without deleting the audit history.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils import timezone

from .models import McpCallLog, McpToken


@admin.register(McpToken)
class McpTokenAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "secret_prefix",
        "scopes",
        "rate_limit_per_minute",
        "created_at",
        "expires_at",
        "revoked_at",
        "last_used_at",
    )
    list_filter = ("revoked_at",)
    search_fields = ("name", "secret_prefix", "notes")
    readonly_fields = (
        "secret_hash",
        "secret_prefix",
        "created_at",
        "last_used_at",
        "last_used_ip",
    )
    actions = ["revoke_selected"]

    @admin.action(description="Revoke selected tokens")
    def revoke_selected(self, request, queryset):
        updated = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, f"Revoked {updated} token(s).")


@admin.register(McpCallLog)
class McpCallLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "token",
        "method",
        "tool_name",
        "status",
        "duration_ms",
        "client_ip",
    )
    list_filter = ("status", "method", "tool_name")
    search_fields = ("tool_name", "method", "error", "client_ip", "user_agent")
    readonly_fields = tuple(f.name for f in McpCallLog._meta.fields)

    def has_add_permission(self, request) -> bool:  # append-only
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # immutable
        return False
