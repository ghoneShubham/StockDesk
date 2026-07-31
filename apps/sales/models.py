from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.masters.models import Customer, Product


class InvoiceSequence(models.Model):
    """
    One locked counter row per financial year. `apps.sales.services.next_invoice_no`
    locks this row with `select_for_update()` inside `transaction.atomic()` and
    increments it, guaranteeing sequential, gap-free, duplicate-free invoice
    numbers under concurrent billing (PRD R3). Never derive invoice numbers
    from `max(id) + 1` in Python — that has a race condition.
    """

    financial_year = models.CharField(max_length=9, unique=True)  # e.g. "2025-26"
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.financial_year}: last={self.last_number}"


class Sale(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PARTIAL = "partial", "Partial"

    invoice_no = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales"
    )
    sale_date = models.DateTimeField()
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="sales"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sale_date", "-id"]
        indexes = [
            models.Index(fields=["-sale_date"]),
            models.Index(fields=["payment_status"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(subtotal__gte=Decimal("0")), name="sale_subtotal_gte_0"),
            models.CheckConstraint(check=models.Q(discount__gte=Decimal("0")), name="sale_discount_gte_0"),
            models.CheckConstraint(check=models.Q(tax__gte=Decimal("0")), name="sale_tax_gte_0"),
            models.CheckConstraint(check=models.Q(total_amount__gte=Decimal("0")), name="sale_total_gte_0"),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_no}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(qty__gt=Decimal("0")), name="sale_item_qty_gt_0"),
            models.CheckConstraint(check=models.Q(rate__gte=Decimal("0")), name="sale_item_rate_gte_0"),
            models.CheckConstraint(check=models.Q(discount__gte=Decimal("0")), name="sale_item_discount_gte_0"),
            # Discount cannot exceed the line amount (qty * rate) — PRD test #11.
            models.CheckConstraint(
                check=models.Q(discount__lte=models.F("qty") * models.F("rate")),
                name="sale_item_discount_lte_line_amount",
            ),
        ]

    def __str__(self):
        return f"{self.product.sku} x{self.qty} @ {self.rate}"
