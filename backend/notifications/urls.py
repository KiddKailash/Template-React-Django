from django.urls import path

from . import views

# Mounted at /api/notifications/
urlpatterns = [
    path("vapid-public-key/", views.vapid_public_key, name="vapid_public_key"),
    path("subscribe/", views.subscribe, name="subscribe"),
    path("unsubscribe/", views.unsubscribe, name="unsubscribe"),
    path("seen/", views.seen, name="seen"),
    path("test/", views.test_push, name="test_push"),
]
