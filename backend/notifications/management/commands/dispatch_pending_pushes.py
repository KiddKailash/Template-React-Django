"""Retry FAILED PushNotification rows whose backoff window has elapsed.

Not the primary retry driver: ``queue_push()`` flushes the backlog before it
queues anything, so a retry rides along with the next notification. This is
the backstop for a push that failed with nothing queued since; it runs from
``cron/orchestrate.sh daily``. PENDING rows are picked up too, in case
``queue_push`` ran while VAPID was unset.

    uv run python manage.py dispatch_pending_pushes
"""

from django.core.management.base import BaseCommand

from notifications.utils.dispatcher import dispatch_pending


class Command(BaseCommand):
    help = "Deliver every push notification currently ready to fire."

    def handle(self, *args, **options):
        result = dispatch_pending()
        self.stdout.write(self.style.SUCCESS(f"Push dispatch: {result}"))
