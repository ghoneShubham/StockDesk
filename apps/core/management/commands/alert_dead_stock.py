"""
Day 14 — weekly dead-stock report email (enqueue only).
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.outbox import enqueue_email
from apps.reports.queries import dead_stock


class Command(BaseCommand):
    help = "Enqueue a weekly dead-stock report (on-hand, no movement in N days)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=60, help="Inactivity window (default 60).")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Enqueue even when the report is empty.",
        )

    def handle(self, *args, **options):
        recipients = list(getattr(settings, "LOW_STOCK_ALERT_RECIPIENTS", []) or [])
        if not recipients:
            self.stdout.write(self.style.WARNING("LOW_STOCK_ALERT_RECIPIENTS empty — skip."))
            return

        days = options["days"]
        products = dead_stock(days=days)
        if not products and not options["force"]:
            self.stdout.write("No dead-stock products — nothing to enqueue.")
            return

        today = timezone.localdate()
        week_key = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
        lines = [
            f"StockDesk dead-stock report — week {week_key}",
            f"On-hand products with no movement in {days} days: {len(products)}",
            "",
        ]
        for p in products[:200]:
            qty = getattr(p, "stock_qty", "?")
            lines.append(f"- {p.sku}  {p.name}  stock={qty}")
        if len(products) > 200:
            lines.append(f"... and {len(products) - 200} more")

        row = enqueue_email(
            to=recipients,
            subject=f"[StockDesk] Dead stock ({len(products)}) — {week_key}",
            body_text="\n".join(lines),
            idempotency_key=f"dead-stock-{week_key}",
        )
        if row:
            self.stdout.write(self.style.SUCCESS(f"Enqueued EmailOutbox#{row.pk}"))
        else:
            self.stdout.write("Nothing enqueued.")
