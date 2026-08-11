"""
Day 9 — stock reconciliation command (PRD R1 deliverable).

Current stock is always sum(StockMovement.qty_delta). This command checks that
business documents (purchases, sales, adjustments) match their linked movements,
and reports negative stock or orphaned ledger rows.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.inventory.models import Adjustment, StockMovement
from apps.masters.models import Product
from apps.purchases.models import Purchase
from apps.sales.models import Sale


class Command(BaseCommand):
    help = (
        "Verify stock ledger integrity: document totals vs StockMovement rows, "
        "orphaned movements, and negative balances."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-drift",
            action="store_true",
            help="Exit with code 1 if any drift/orphan/negative stock is found.",
        )

    def handle(self, *args, **options):
        issues: list[str] = []

        issues.extend(self._check_purchases())
        issues.extend(self._check_sales())
        issues.extend(self._check_adjustments())
        issues.extend(self._check_orphaned_movements())
        issues.extend(self._check_negative_stock())

        if not issues:
            self.stdout.write(self.style.SUCCESS("Stock reconciliation OK - no drift found."))
            return

        self.stdout.write(self.style.ERROR(f"Stock reconciliation found {len(issues)} issue(s):"))
        for line in issues:
            self.stdout.write(f"  - {line}")

        if options["fail_on_drift"]:
            raise SystemExit(1)

    def _movement_sum(self, reference_type: str, reference_id: int) -> Decimal:
        total = (
            StockMovement.objects.filter(
                reference_type=reference_type, reference_id=reference_id
            ).aggregate(s=Sum("qty_delta"))["s"]
            or Decimal("0")
        )
        return total

    def _check_purchases(self) -> list[str]:
        issues = []
        for purchase in Purchase.objects.prefetch_related("items").all():
            expected = sum((item.qty for item in purchase.items.all()), Decimal("0"))
            actual = self._movement_sum(StockMovement.ReferenceType.PURCHASE, purchase.pk)
            if expected != actual:
                issues.append(
                    f"Purchase #{purchase.pk}: items sum to {expected}, "
                    f"movements sum to {actual}"
                )
        return issues

    def _check_sales(self) -> list[str]:
        issues = []
        for sale in Sale.objects.prefetch_related("items").all():
            expected = -sum((item.qty for item in sale.items.all()), Decimal("0"))
            actual = self._movement_sum(StockMovement.ReferenceType.SALE, sale.pk)
            if expected != actual:
                issues.append(
                    f"Sale {sale.invoice_no}: items imply {expected}, "
                    f"movements sum to {actual}"
                )
        return issues

    def _check_adjustments(self) -> list[str]:
        issues = []
        for adj in Adjustment.objects.select_related("stock_movement").all():
            if adj.stock_movement_id is None:
                issues.append(f"Adjustment #{adj.pk}: missing linked stock_movement")
                continue
            move = adj.stock_movement
            if move.qty_delta != adj.qty_delta:
                issues.append(
                    f"Adjustment #{adj.pk}: qty_delta {adj.qty_delta} != "
                    f"movement {move.qty_delta}"
                )
            if move.reference_type != StockMovement.ReferenceType.ADJUSTMENT:
                issues.append(f"Adjustment #{adj.pk}: movement has wrong reference_type")
            elif move.reference_id != adj.pk:
                issues.append(f"Adjustment #{adj.pk}: movement reference_id mismatch")
        return issues

    def _check_orphaned_movements(self) -> list[str]:
        issues = []
        purchase_ids = set(Purchase.objects.values_list("id", flat=True))
        sale_ids = set(Sale.objects.values_list("id", flat=True))
        adj_ids = set(Adjustment.objects.values_list("id", flat=True))

        for m in StockMovement.objects.only("id", "reference_type", "reference_id").iterator(
            chunk_size=500
        ):
            if m.reference_type == StockMovement.ReferenceType.PURCHASE:
                if m.reference_id not in purchase_ids:
                    issues.append(f"Movement #{m.id}: orphan purchase reference {m.reference_id}")
            elif m.reference_type == StockMovement.ReferenceType.SALE:
                if m.reference_id not in sale_ids:
                    issues.append(f"Movement #{m.id}: orphan sale reference {m.reference_id}")
            elif m.reference_type == StockMovement.ReferenceType.ADJUSTMENT:
                if m.reference_id not in adj_ids:
                    issues.append(
                        f"Movement #{m.id}: orphan adjustment reference {m.reference_id}"
                    )
        return issues

    def _check_negative_stock(self) -> list[str]:
        issues = []
        rows = (
            Product.objects.annotate(stock=Sum("stock_movements__qty_delta"))
            .filter(stock__lt=0)
            .values_list("sku", "stock")
        )
        for sku, stock in rows:
            issues.append(f"Product {sku}: negative stock {stock}")
        return issues
