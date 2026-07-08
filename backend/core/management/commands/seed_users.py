"""Bootstrap users listed in the INITIAL_USERS env var.

Format: `INITIAL_USERS=alice:pw1,bob:pw2`

Idempotent — existing users are skipped. Safe to run on every deploy.
"""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create users listed in INITIAL_USERS env var (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would be created without touching the DB.",
        )

    def handle(self, *args, **options):
        raw = os.getenv("INITIAL_USERS", "").strip()
        if not raw:
            self.stdout.write("INITIAL_USERS is empty — nothing to seed.")
            return

        dry = options["dry_run"]
        created = 0
        skipped = 0

        for entry in raw.split(","):
            entry = entry.strip()
            if not entry or ":" not in entry:
                self.stderr.write(f"Skipping malformed entry: {entry!r}")
                continue

            username, password = entry.split(":", 1)
            username, password = username.strip(), password.strip()

            if not username or not password:
                self.stderr.write(f"Skipping empty username or password in: {entry!r}")
                continue

            if User.objects.filter(username=username).exists():
                self.stdout.write(f"= {username} already exists")
                skipped += 1
                continue

            if dry:
                self.stdout.write(f"+ would create {username}")
            else:
                User.objects.create_user(username=username, password=password)
                self.stdout.write(self.style.SUCCESS(f"+ created {username}"))
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_users done — created={created} skipped={skipped} dry_run={dry}"
            )
        )
