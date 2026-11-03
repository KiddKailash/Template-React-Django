from django.contrib import admin

from .models import NotificationDispatch, PushNotification, PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "endpoint", "active", "updated_at", "last_success_at")
    list_filter = ("active",)
    search_fields = ("endpoint", "user_agent", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "last_success_at")


@admin.register(PushNotification)
class PushNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "notification_type",
        "status",
        "title",
        "attempt_count",
        "created_at",
        "sent_at",
    )
    list_filter = ("status", "notification_type")
    search_fields = ("title", "body", "user__username")
    readonly_fields = ("created_at", "sent_at", "last_attempted_at")


@admin.register(NotificationDispatch)
class NotificationDispatchAdmin(admin.ModelAdmin):
    list_display = ("id", "notification", "outcome", "http_status", "attempted_at")
    list_filter = ("outcome",)
    readonly_fields = ("attempted_at",)
