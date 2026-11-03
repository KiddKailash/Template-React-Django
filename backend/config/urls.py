"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import (
    ChangePasswordView,
    LogoutView,
    SessionTokenObtainPairView,
    SessionTokenRefreshView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    # Sign-in opens a DeviceSession and binds the tokens to it (accounts/).
    path("api/token/", SessionTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", SessionTokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/auth/password/", ChangePasswordView.as_view(), name="change_password"),
    path("api/sessions/", include("accounts.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
