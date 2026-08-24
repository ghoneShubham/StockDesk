from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.masters.models import Product, Supplier


class PurchaseSequence(models.Model):
    """
    One locked counter row per financial year. `apps.purchases.services.next_supplier_invoice_no`
    locks this row with `select_for_update()` so concurrent purchases cannot get the same
    auto-generated supplier invoice number.
    """

    financial_year = models.CharField(max_length=9, unique=True)  # e.g. "2025-26"
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.financial_year}: last={self.last_number}"


class Purchase(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    supplier_invoice_no = models.CharField(max_length=64, blank=True)
    purchase_date = models.DateField()
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="purchases"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchase_date", "-id"]
        indexes = [
            models.Index(fields=["-purchase_date"]),
            models.Index(fields=["-purchase_date", "-id"]),
            models.Index(fields=["supplier_invoice_no"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=Decimal("0")), name="purchase_total_gte_0"),
        ]

    def __str__(self):
        return f"Purchase #{self.pk} — {self.supplier.name} ({self.purchase_date})"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_items")
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gt=Decimal("0")), name="purchase_item_qty_gt_0"),
            models.CheckConstraint(condition=models.Q(rate__gte=Decimal("0")), name="purchase_item_rate_gte_0"),
        ]

    def __str__(self):
        return f"{self.product.sku} x{self.qty} @ {self.rate}"
