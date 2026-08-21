"""
Day 14 — daily low-stock alert. Enqueues email intent; does not send SMTP itself.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.outbox import enqueue_email
from apps.reports.queries import low_stock_products


class Command(BaseCommand):
    help = "Enqueue a low-stock alert email when products are at/below reorder level."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Enqueue even when there are zero low-stock products (smoke test).",
        )

    def handle(self, *args, **options):
        recipients = list(getattr(settings, "LOW_STOCK_ALERT_RECIPIENTS", []) or [])
        if not recipients:
            self.stdout.write(self.style.WARNING("LOW_STOCK_ALERT_RECIPIENTS empty — skip."))
            return

        products = low_stock_products()
        if not products and not options["force"]:
            self.stdout.write("No low-stock products — nothing to enqueue.")
            return

        today = timezone.localdate().isoformat()
        lines = [
            f"StockDesk low-stock alert — {today}",
            f"Products at or below reorder level: {len(products)}",
            "",
        ]
        for p in products[:200]:
            qty = getattr(p, "stock_qty", "?")
            lines.append(f"- {p.sku}  {p.name}  stock={qty}  reorder={p.reorder_level}")
        if len(products) > 200:
            lines.append(f"... and {len(products) - 200} more")

        body = "\n".join(lines)
        row = enqueue_email(
            to=recipients,
            subject=f"[StockDesk] Low stock alert ({len(products)} products) — {today}",
            body_text=body,
            idempotency_key=f"low-stock-{today}",
        )
        if row:
            self.stdout.write(self.style.SUCCESS(f"Enqueued EmailOutbox#{row.pk}"))
        else:
            self.stdout.write("Nothing enqueued.")
