from django.conf import settings
from django.db import models

from apps.masters.models import Product


class StockMovement(models.Model):
    """
    The single source of truth for stock. Current stock for a product is
    always `sum(qty_delta)` over its movements — never a separately
    maintained counter. Every sale, purchase, and adjustment writes one of
    these rows inside the same DB transaction as the business record it
    belongs to (PRD R1). This is what makes "stock shows 37, what happened
    since yesterday?" answerable at all times.
    """

    class MovementType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"
        OPENING = "opening", "Opening stock"

    class ReferenceType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=12, choices=MovementType.choices)
    qty_delta = models.DecimalField(max_digits=12, decimal_places=2)
    reference_type = models.CharField(max_length=12, choices=ReferenceType.choices)
    reference_id = models.BigIntegerField()
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="stock_movements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(qty_delta=0), name="stock_movement_qty_delta_nonzero"),
        ]
        indexes = [
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["product", "created_at", "id"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.product.sku} {self.qty_delta:+} ({self.movement_type})"


class Adjustment(models.Model):
    """
    A manual stock correction (damage, theft, physical-count correction,
    opening stock). Saving one writes a matching StockMovement row in the
    same transaction (see apps.inventory.services.apply_adjustment).
    """

    class Reason(models.TextChoices):
        DAMAGE = "damage", "Damage"
        THEFT = "theft", "Theft"
        CORRECTION = "correction", "Stock count correction"
        OPENING_STOCK = "opening_stock", "Opening stock"
        OTHER = "other", "Other"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="adjustments")
    qty_delta = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    notes = models.TextField(blank=True)
    stock_movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, null=True, related_name="adjustment"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="adjustments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at", "-id"]),
            models.Index(fields=["product", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(qty_delta=0), name="adjustment_qty_delta_nonzero"),
        ]

    def __str__(self):
        return f"Adjustment #{self.pk}: {self.product.sku} {self.qty_delta:+} ({self.reason})"
