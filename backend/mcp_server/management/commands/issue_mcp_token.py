"""``uv run python manage.py issue_mcp_token`` — admin CLI for MCP tokens.

Mirrors the REST POST endpoint but is reachable from a shell when the
frontend is offline or before the first deploy. Prints the raw secret
exactly once to stdout; the operator MUST capture it immediately —
the database stores only the SHA-256 hash.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from mcp_server.models import McpToken


class Command(BaseCommand):
    help = "Issue a new MCP bearer token. The raw secret is printed once."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--name", required=True, help="Human-readable token label")
        parser.add_argument(
            "--scopes",
            default="tools:*",
            help="Comma-separated scopes (default 'tools:*' = all read-only tools)",
        )
        parser.add_argument(
            "--rate-limit",
            type=int,
            default=60,
            help="Per-minute rate limit (0 = unlimited)",
        )
        parser.add_argument(
            "--ttl-days",
            type=int,
            default=None,
            help="Optional expiry in days (omit for non-expiring)",
        )
        parser.add_argument("--notes", default="", help="Free-text notes")

    def handle(self, *args, **opts) -> None:
        token, raw = McpToken.issue(
            name=opts["name"],
            scopes=opts["scopes"],
            rate_limit_per_minute=opts["rate_limit"],
            ttl_days=opts["ttl_days"],
            notes=opts["notes"],
        )
        self.stdout.write(self.style.SUCCESS("\nMCP token issued."))
        self.stdout.write(f"  id:         {token.id}")
        self.stdout.write(f"  name:       {token.name}")
        self.stdout.write(f"  scopes:     {token.scopes}")
        self.stdout.write(f"  rate_limit: {token.rate_limit_per_minute}/min")
        self.stdout.write(f"  expires_at: {token.expires_at or '(no expiry)'}")
        self.stdout.write(self.style.WARNING("\n  SECRET (shown once — store it now):"))
        self.stdout.write(self.style.WARNING(f"    {raw}\n"))
