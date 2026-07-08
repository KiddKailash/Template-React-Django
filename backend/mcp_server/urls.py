"""MCP server URL routes.

Two surfaces:

  * ``/api/mcp/``              — POST-only JSON-RPC endpoint. Bearer-
                                 token auth. CSRF-exempt.
  * ``/api/mcp/tokens/``       — token-management REST API.
                                 Admin-only by default.
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

app_name = "mcp_server"

# SimpleRouter (not DefaultRouter) — DefaultRouter mounts a GET API
# root at "", which would shadow the POST-only mcp_endpoint at the
# same path. SimpleRouter omits the root view; each viewset still
# lands at its registered prefix.
router = SimpleRouter()
router.register("tokens", views.McpTokenViewSet, basename="mcp-token")

urlpatterns = [
    path("", views.mcp_endpoint, name="mcp_endpoint"),
    path("", include(router.urls)),
]
