from __future__ import annotations

from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.send, name="send"),
    path("stream/", views.ChatStreamView.as_view(), name="stream"),
    path("today/", views.today_thread, name="today_thread"),
]
