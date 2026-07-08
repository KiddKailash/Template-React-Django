"""Bearer-token authentication for the MCP endpoint.

External MCP clients (Claude Desktop, scripts) can't share the browser
session used by the in-app frontend, so authentication happens at the
view layer with a bearer token in the `Authorization` header:

    Authorization: Bearer mcp_<secret>

Failed auth writes an `McpCallLog` row with `token=None` so brute-
force or token-spraying attacks are visible to the operator without
extra infra. The SHA-256 lookup on the secret means a DB read cannot
recover the raw token.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.http import HttpRequest

from ..models import McpCallLog, McpToken


@dataclass
class AuthResult:
    token: McpToken | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.token is not None and self.error is None


def authenticate(request: HttpRequest) -> AuthResult:
    """Extract + verify the bearer token from an HTTP request."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    raw = _extract_bearer(header)
    if raw is None:
        return AuthResult(token=None, error="missing_or_malformed_authorization_header")
    token = McpToken.verify(raw)
    if token is None:
        # Persist the failed attempt for ops visibility; never disclose
        # which arm failed (no such token vs revoked vs expired).
        McpCallLog.objects.create(
            token=None,
            method="",
            tool_name="",
            status=McpCallLog.Status.AUTH_FAILED,
            error="invalid_or_expired_token",
            client_ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:240],
        )
        return AuthResult(token=None, error="invalid_or_expired_token")
    token.record_use(client_ip(request))
    return AuthResult(token=token)


def client_ip(request: HttpRequest) -> str | None:
    """Best-effort client IP, honouring an X-Forwarded-For chain."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _extract_bearer(header: str) -> str | None:
    parts = header.strip().split()
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "bearer":
        return None
    if not value:
        return None
    return value
