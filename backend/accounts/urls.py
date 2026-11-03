from django.urls import path

from . import views

# Mounted at /api/sessions/ (the auth routes are in config/urls.py).
urlpatterns = [
    path("", views.SessionListView.as_view(), name="session_list"),
    path("revoke-others/", views.RevokeOtherSessionsView.as_view(), name="session_revoke_others"),
    path("<uuid:pk>/", views.SessionDetailView.as_view(), name="session_detail"),
]
