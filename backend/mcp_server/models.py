"""MCP server persistence: bearer tokens + immutable call audit.

Security model
==============

The MCP endpoint sits behind a separate auth path from the rest of the
backend. The in-app frontend (browser) uses session/JWT auth; external
MCP clients (Claude Desktop, scripts) authenticate with a bearer token
issued through the admin API or the `issue_mcp_token` management
command.

The raw secret is shown to the user **exactly once**, at creation
time, and only its SHA-256 hash is persisted. A revoked or expired
token cannot authenticate — `McpToken.verify()` is the single
authoritative check.

Every successful or failed authentication and every tool call writes
an `McpCallLog` row. The audit trail is append-only and includes the
SHA-256 hash of the arguments (not the arguments themselves) so the
log itself cannot become a privacy leak.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.db import models
from django.utils import timezone

# 24 bytes (~192 bits) of entropy for the server-side bearer secret.
# The visible token string is `mcp_<urlsafe-32>`; the prefix is stored
# so users can tell tokens apart in the UI without revealing the
# secret. Change TOKEN_PREFIX to something project-specific if you want
# tokens to be visually attributable (e.g. `acme_mcp_`).
TOKEN_PREFIX = "mcp_"
TOKEN_SECRET_BYTES = 24
TOKEN_DISPLAY_PREFIX_LEN = 8


class McpToken(models.Model):
    """Bearer token granting MCP access to a subset of the read-only tool surface.

    A token never grants write access — write access does not exist on
    the MCP surface (the underlying tool registry is AST-validated to
    forbid it). Scopes control which read-only tools the holder can
    invoke; the default scope `tools:*` exposes every connected tool,
    while a narrower scope (e.g. `tools:current_time_utc,tools:count_users_since`)
    is appropriate for third-party clients.
    """

    name = models.CharField(
        max_length=120,
        help_text="Human-readable label (e.g. 'Claude Desktop — laptop').",
    )
    secret_hash = models.CharField(max_length=64, unique=True, db_index=True)
    secret_prefix = models.CharField(max_length=32)
    scopes = models.TextField(
        default="tools:*",
        help_text=(
            "Comma-separated scopes. Use 'tools:*' for full read-only access, "
            "or list specific tools: 'tools:current_time_utc,tools:count_users_since'."
        ),
    )
    rate_limit_per_minute = models.PositiveIntegerField(
        default=60,
        help_text="Per-minute rate limit. 0 means unlimited (use sparingly).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional hard expiry. Tokens without an expiry are valid until revoked.",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["revoked_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        state = "revoked" if self.revoked_at else "active"
        return f"{self.name} ({self.secret_prefix}…, {state})"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def issue(
        cls,
        *,
        name: str,
        scopes: str = "tools:*",
        rate_limit_per_minute: int = 60,
        ttl_days: int | None = None,
        notes: str = "",
    ) -> tuple[McpToken, str]:
        """Create a token, returning the row and the raw secret.

        The raw secret string is returned exactly once. The caller is
        responsible for surfacing it to the user (and only to the user)
        immediately; the row's `secret_hash` is the only persisted
        artefact.
        """
        raw_secret = TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_SECRET_BYTES)
        digest = _hash_secret(raw_secret)
        expires_at = None
        if ttl_days is not None and ttl_days > 0:
            expires_at = timezone.now() + timedelta(days=int(ttl_days))
        token = cls.objects.create(
            name=name.strip()[:120] or "unnamed",
            secret_hash=digest,
            secret_prefix=raw_secret[: len(TOKEN_PREFIX) + TOKEN_DISPLAY_PREFIX_LEN],
            scopes=scopes.strip() or "tools:*",
            rate_limit_per_minute=int(rate_limit_per_minute),
            expires_at=expires_at,
            notes=notes,
        )
        return token, raw_secret

    @classmethod
    def verify(cls, raw_secret: str) -> McpToken | None:
        """Lookup an active token by raw secret.

        Returns the row iff the secret matches a token that is neither
        revoked nor expired. All other paths return None — the caller
        must not distinguish between "no such token" and "token revoked".
        """
        if not raw_secret or not raw_secret.startswith(TOKEN_PREFIX):
            return None
        digest = _hash_secret(raw_secret)
        token = cls.objects.filter(secret_hash=digest).first()
        if token is None or not token.is_active():
            return None
        return token

    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return not (self.expires_at is not None and self.expires_at <= timezone.now())

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    # ------------------------------------------------------------------
    # Scope helpers
    # ------------------------------------------------------------------

    def scope_set(self) -> set[str]:
        return {s.strip() for s in (self.scopes or "").split(",") if s.strip()}

    def can_call_tool(self, tool_name: str) -> bool:
        scopes = self.scope_set()
        if "tools:*" in scopes:
            return True
        return f"tools:{tool_name}" in scopes

    def record_use(self, ip: str | None) -> None:
        self.last_used_at = timezone.now()
        if ip:
            self.last_used_ip = ip
        self.save(update_fields=["last_used_at", "last_used_ip"])


class McpCallLog(models.Model):
    """Append-only audit row for every authenticated MCP request.

    One row per JSON-RPC call: `initialize`, `ping`, `tools/list`,
    `tools/call`. Failed auth attempts also write a row (with
    `token=None`) so brute-force attempts are visible to the operator.

    The `argument_hash` column stores the SHA-256 of the JSON-serialised
    arguments — never the arguments themselves. This keeps the audit
    log usable for replay detection / abuse triage without making the
    log itself a privacy surface.
    """

    class Status(models.TextChoices):
        OK = "ok", "Success"
        AUTH_FAILED = "auth_failed", "Auth failed"
        TOOL_DENIED = "tool_denied", "Tool denied (scope or source)"
        RATE_LIMITED = "rate_limited", "Rate limited"
        BAD_REQUEST = "bad_request", "Bad request"
        ERROR = "error", "Handler error"

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    token = models.ForeignKey(
        McpToken,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="calls",
    )
    method = models.CharField(max_length=64, blank=True, default="")
    tool_name = models.CharField(max_length=120, blank=True, default="")
    argument_hash = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=24, choices=Status.choices)
    error = models.CharField(max_length=240, blank=True, default="")
    duration_ms = models.PositiveIntegerField(default=0)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["token", "-timestamp"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        label = self.tool_name or self.method or "<unknown>"
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} {label} → {self.status}"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _hash_secret(raw_secret: str) -> str:
    """SHA-256 hex digest of a raw token secret.

    Plain SHA-256 (not bcrypt/argon2) because the secret is a 24-byte
    URL-safe random string — there is no password-space to defend
    against. The hash exists so a DB read is not equivalent to a token
    grant.
    """
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


def stable_arg_hash(payload: Any) -> str:
    """SHA-256 of a deterministic JSON representation of `payload`.

    Used by the audit log to record *which* call happened without
    persisting the data itself. `sort_keys=True` keeps the hash stable
    across key reorderings; `default=str` accepts datetimes / sets.
    """
    import json

    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
