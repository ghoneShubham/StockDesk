from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.masters.models import Product, Supplier


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
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(total_amount__gte=Decimal("0")), name="purchase_total_gte_0"),
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
            models.CheckConstraint(check=models.Q(qty__gt=Decimal("0")), name="purchase_item_qty_gt_0"),
            models.CheckConstraint(check=models.Q(rate__gte=Decimal("0")), name="purchase_item_rate_gte_0"),
        ]

    def __str__(self):
        return f"{self.product.sku} x{self.qty} @ {self.rate}"
