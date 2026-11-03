from django.contrib import admin

from .models import DeviceSession


@admin.register(DeviceSession)
class DeviceSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "ip_address", "last_seen_at", "expires_at", "revoked_at")
    list_filter = ("revoked_at",)
    search_fields = ("user__username", "user__email", "user_agent", "ip_address")
    readonly_fields = ("id", "created_at", "last_seen_at", "expires_at", "user_agent", "ip_address")
    actions = ["revoke_sessions"]

    @admin.action(description="Sign out the selected sessions")
    def revoke_sessions(self, request, queryset):
        count = queryset.revoke()
        self.message_user(request, f"Signed out {count} session(s).")
