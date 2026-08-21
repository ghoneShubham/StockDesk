"""
Day 14 — drain EmailOutbox via Django EMAIL_* (SES SMTP in prod).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import EmailOutbox

# Backoff seconds after attempt N fails (capped by list length).
_BACKOFF = (60, 300, 900, 3600, 7200)


class Command(BaseCommand):
    help = "Send pending EmailOutbox rows (SES/SMTP). Safe to run every minute via systemd timer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max rows to attempt this run (default 50).",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        now = timezone.now()
        rows = list(
            EmailOutbox.objects.filter(status=EmailOutbox.Status.PENDING)
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .order_by("created_at")[:limit]
        )
        if not rows:
            self.stdout.write("No pending outbox rows ready to send.")
            return

        sent = failed = 0
        for row in rows:
            if self._send_one(row):
                sent += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(f"Outbox drain: sent={sent} failed/deferred={failed}"))

    def _send_one(self, row: EmailOutbox) -> bool:
        with transaction.atomic():
            locked = (
                EmailOutbox.objects.select_for_update()
                .filter(pk=row.pk, status=EmailOutbox.Status.PENDING)
                .first()
            )
            if locked is None:
                return False

            try:
                msg = EmailMultiAlternatives(
                    subject=locked.subject,
                    body=locked.body_text,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=list(locked.to_addresses),
                )
                if locked.body_html:
                    msg.attach_alternative(locked.body_html, "text/html")
                msg.send(fail_silently=False)
            except Exception as exc:  # noqa: BLE001 — record any SMTP/SES failure
                locked.attempts += 1
                locked.last_error = str(exc)[:2000]
                if locked.attempts >= locked.max_attempts:
                    locked.status = EmailOutbox.Status.FAILED
                    locked.next_attempt_at = None
                else:
                    delay = _BACKOFF[min(locked.attempts - 1, len(_BACKOFF) - 1)]
                    locked.next_attempt_at = timezone.now() + timedelta(seconds=delay)
                locked.save(
                    update_fields=[
                        "attempts",
                        "last_error",
                        "status",
                        "next_attempt_at",
                        "updated_at",
                    ]
                )
                self.stderr.write(f"Outbox #{locked.pk} attempt {locked.attempts} failed: {exc}")
                return False

            locked.status = EmailOutbox.Status.SENT
            locked.sent_at = timezone.now()
            locked.last_error = ""
            locked.next_attempt_at = None
            locked.attempts += 1
            locked.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "last_error",
                    "next_attempt_at",
                    "attempts",
                    "updated_at",
                ]
            )
            return True
