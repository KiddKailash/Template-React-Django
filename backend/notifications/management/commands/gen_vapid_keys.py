"""Generate a fresh VAPID keypair for Web Push.

Outputs two env-var lines to stdout. Put them in ``backend/.env`` (or the
BACKEND_ENV deploy secret), set WEB_PUSH_VAPID_SUBJECT to a mailto: you read,
and restart the backend. Existing PushSubscription rows are invalidated by
rotation — the frontend re-registers on next load.

    uv run python manage.py gen_vapid_keys
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Command(BaseCommand):
    help = "Generate a VAPID keypair for Web Push (uncompressed P-256)."

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())

        private_numbers = private_key.private_numbers()
        private_der = private_numbers.private_value.to_bytes(32, "big")

        public_key = private_key.public_key()
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        self.stdout.write("# Add to .env (replace existing values):")
        self.stdout.write(f"WEB_PUSH_VAPID_PRIVATE_KEY={_urlsafe_b64encode(private_der)}")
        self.stdout.write(f"WEB_PUSH_VAPID_PUBLIC_KEY={_urlsafe_b64encode(public_bytes)}")
        self.stdout.write("# Rotation invalidates existing subscriptions.")
