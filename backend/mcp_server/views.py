"""MCP server HTTP surface.

Two endpoints:

  * ``POST /api/mcp/``           — the MCP JSON-RPC endpoint. Bearer-
                                   token authenticated. Accepts a
                                   single JSON-RPC request or a batch.
                                   Responds with JSON (no SSE — our
                                   tools are synchronous and fast).
  * ``/api/mcp/tokens/`` (DRF)  — admin REST API used by the in-app
                                   frontend (or admin site) to issue
                                   and revoke tokens. IsAuthenticated
                                   protects the path; the newly-issued
                                   raw secret is returned exactly once
                                   in the POST response.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import McpCallLog, McpToken, stable_arg_hash
from .utils.auth import authenticate, client_ip
from .utils.protocol import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PARSE_ERROR,
    PRIVACY_VIOLATION_CODE,
    RATE_LIMITED_CODE,
    JsonRpcError,
    dispatch,
)
from .utils.rate_limit import is_rate_limited

logger = logging.getLogger(__name__)


# =====================================================================
# MCP JSON-RPC endpoint
# =====================================================================


@csrf_exempt  # bearer-token auth replaces CSRF for this endpoint
@require_http_methods(["POST"])
def mcp_endpoint(request: HttpRequest) -> HttpResponse:
    """JSON-RPC entry point for MCP clients.

    Auth → rate-limit → parse → dispatch (per request in a batch) →
    audit log. The audit row is written for every call regardless of
    outcome so the operator can see exactly what each token did.
    """
    if not getattr(settings, "MCP_ENABLED", True):
        return _http_jsonrpc_error(
            id_=None,
            code=INVALID_REQUEST,
            message="MCP service is disabled on this instance.",
            status=503,
        )

    auth = authenticate(request)
    if not auth.ok:
        return _http_jsonrpc_error(
            id_=None,
            code=INVALID_REQUEST,
            message="unauthorized",
            status=401,
        )
    token = auth.token

    if is_rate_limited(token):
        McpCallLog.objects.create(
            token=token,
            method="",
            status=McpCallLog.Status.RATE_LIMITED,
            error="rate_limited",
            client_ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:240],
        )
        return _http_jsonrpc_error(
            id_=None,
            code=RATE_LIMITED_CODE,
            message="rate limit exceeded",
            status=429,
        )

    try:
        body = json.loads(request.body.decode("utf-8") or "null")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _http_jsonrpc_error(
            id_=None,
            code=PARSE_ERROR,
            message=f"parse error: {exc}",
            status=400,
        )

    # Single request or batch — MCP supports both. Batches MUST yield
    # a JSON array response of the same length, dropping notifications
    # (no id) per JSON-RPC 2.0.
    if isinstance(body, list):
        if not body:
            return _http_jsonrpc_error(
                id_=None,
                code=INVALID_REQUEST,
                message="empty batch",
                status=400,
            )
        responses = [
            r for r in (_handle_single(req, token, request) for req in body) if r is not None
        ]
        return JsonResponse(responses, safe=False)

    if not isinstance(body, dict):
        return _http_jsonrpc_error(
            id_=None,
            code=INVALID_REQUEST,
            message="request must be a JSON object or array of objects",
            status=400,
        )

    response = _handle_single(body, token, request)
    if response is None:
        # Notification — JSON-RPC says we MUST NOT respond. Use 202
        # Accepted with an empty body, which is the MCP convention for
        # notifications-only requests.
        return HttpResponse(status=202)
    return JsonResponse(response)


def _handle_single(
    request_obj: Any, token: McpToken, http_request: HttpRequest
) -> dict[str, Any] | None:
    """Process one JSON-RPC request. Returns the response dict, or None
    for a notification (no `id` field).
    """
    if not isinstance(request_obj, dict):
        return _error_envelope(None, INVALID_REQUEST, "request must be a JSON object")

    rpc_id = request_obj.get("id")
    is_notification = "id" not in request_obj

    if request_obj.get("jsonrpc") != "2.0":
        if is_notification:
            return None
        return _error_envelope(rpc_id, INVALID_REQUEST, "jsonrpc must be '2.0'")

    method = request_obj.get("method")
    if not isinstance(method, str):
        if is_notification:
            return None
        return _error_envelope(rpc_id, INVALID_REQUEST, "method must be a string")

    params = request_obj.get("params", {})
    start = time.monotonic()
    status_for_log = McpCallLog.Status.OK
    error_for_log = ""
    tool_name = ""

    try:
        outcome = dispatch(method, params, token)
        tool_name = outcome.tool_name
        if isinstance(outcome.result, dict) and outcome.result.get("isError"):
            status_for_log = McpCallLog.Status.TOOL_DENIED
            error_for_log = "tool_envelope_is_error"

        if outcome.privacy_violation is not None:
            status_for_log = McpCallLog.Status.ERROR
            error_for_log = f"privacy: {outcome.privacy_violation.reason}"
            McpCallLog.objects.create(
                token=token,
                method=method,
                tool_name=tool_name,
                argument_hash=stable_arg_hash(params),
                status=status_for_log,
                error=error_for_log[:240],
                duration_ms=int((time.monotonic() - start) * 1000),
                client_ip=client_ip(http_request),
                user_agent=http_request.META.get("HTTP_USER_AGENT", "")[:240],
            )
            return (
                None
                if is_notification
                else _error_envelope(
                    rpc_id,
                    PRIVACY_VIOLATION_CODE,
                    "privacy filter rejected the tool result",
                )
            )

        McpCallLog.objects.create(
            token=token,
            method=method,
            tool_name=tool_name,
            argument_hash=stable_arg_hash(params),
            status=status_for_log,
            error=error_for_log[:240],
            duration_ms=int((time.monotonic() - start) * 1000),
            client_ip=client_ip(http_request),
            user_agent=http_request.META.get("HTTP_USER_AGENT", "")[:240],
        )

        if is_notification:
            return None
        return _result_envelope(rpc_id, outcome.result)

    except JsonRpcError as exc:
        error_for_log = exc.message[:240]
        McpCallLog.objects.create(
            token=token,
            method=method,
            tool_name=tool_name,
            argument_hash=stable_arg_hash(params),
            status=McpCallLog.Status.BAD_REQUEST,
            error=error_for_log,
            duration_ms=int((time.monotonic() - start) * 1000),
            client_ip=client_ip(http_request),
            user_agent=http_request.META.get("HTTP_USER_AGENT", "")[:240],
        )
        if is_notification:
            return None
        return _error_envelope(rpc_id, exc.code, exc.message, data=exc.data)
    except Exception as exc:  # noqa: BLE001 — fence runtime errors
        logger.exception("mcp.dispatch_failed", extra={"method": method})
        McpCallLog.objects.create(
            token=token,
            method=method,
            tool_name=tool_name,
            argument_hash=stable_arg_hash(params),
            status=McpCallLog.Status.ERROR,
            error=f"{type(exc).__name__}: {exc}"[:240],
            duration_ms=int((time.monotonic() - start) * 1000),
            client_ip=client_ip(http_request),
            user_agent=http_request.META.get("HTTP_USER_AGENT", "")[:240],
        )
        if is_notification:
            return None
        return _error_envelope(rpc_id, INTERNAL_ERROR, "internal error")


# ---------------------------------------------------------------------
# JSON-RPC envelope helpers
# ---------------------------------------------------------------------


def _result_envelope(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _error_envelope(rpc_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": err}


def _http_jsonrpc_error(*, id_: Any, code: int, message: str, status: int) -> JsonResponse:
    return JsonResponse(_error_envelope(id_, code, message), status=status)


# =====================================================================
# Token management API
# =====================================================================


class McpTokenSerializer(serializers.ModelSerializer):
    """List/detail serializer for tokens (never includes the secret)."""

    state = serializers.SerializerMethodField()

    class Meta:
        model = McpToken
        fields = (
            "id",
            "name",
            "secret_prefix",
            "scopes",
            "rate_limit_per_minute",
            "created_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
            "last_used_ip",
            "notes",
            "state",
        )
        read_only_fields = fields

    def get_state(self, obj: McpToken) -> str:
        from django.utils import timezone

        if obj.revoked_at:
            return "revoked"
        if obj.expires_at is not None and obj.expires_at <= timezone.now():
            return "expired"
        return "active"


class McpTokenCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    scopes = serializers.CharField(required=False, default="tools:*")
    rate_limit_per_minute = serializers.IntegerField(required=False, default=60, min_value=0)
    ttl_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class McpTokenViewSet(viewsets.ViewSet):
    """Admin endpoints for issuing + revoking MCP tokens.

    GET    /api/mcp/tokens/                → list (no secrets)
    POST   /api/mcp/tokens/                → issue (returns secret ONCE)
    POST   /api/mcp/tokens/{id}/revoke/    → revoke
    GET    /api/mcp/tokens/{id}/calls/     → recent audit rows for this token

    Restricted to admin users by default. Loosen `permission_classes`
    if end users should be able to manage their own tokens (add a user
    FK to `McpToken` first).
    """

    permission_classes = [IsAdminUser]

    def list(self, request):
        qs = McpToken.objects.all()
        return Response(McpTokenSerializer(qs, many=True).data)

    def create(self, request):
        ser = McpTokenCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        token, raw = McpToken.issue(**ser.validated_data)
        return Response(
            {
                **McpTokenSerializer(token).data,
                # Returned ONCE — the only time the secret is ever
                # disclosed. Any UI showing this MUST warn the user it
                # cannot be recovered.
                "secret": raw,
            },
            status=201,
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        try:
            token = McpToken.objects.get(pk=pk)
        except McpToken.DoesNotExist as exc:
            raise NotFound("not_found") from exc
        token.revoke()
        return Response(McpTokenSerializer(token).data)

    @action(detail=True, methods=["get"])
    def calls(self, request, pk=None):
        try:
            token = McpToken.objects.get(pk=pk)
        except McpToken.DoesNotExist as exc:
            raise NotFound("not_found") from exc
        limit = min(int(request.query_params.get("limit", 50)), 200)
        rows = McpCallLog.objects.filter(token=token)[:limit]
        return Response(
            [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat(),
                    "method": r.method,
                    "tool_name": r.tool_name,
                    "status": r.status,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                    "client_ip": r.client_ip,
                }
                for r in rows
            ]
        )
