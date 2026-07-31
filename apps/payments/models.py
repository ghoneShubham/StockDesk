from decimal import Decimal

from django.db import models

from apps.sales.models import Sale


class PaymentLink(models.Model):
    """A Razorpay Payment Link (test mode only) created against a pending-payment invoice."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payment_links")
    razorpay_payment_link_id = models.CharField(max_length=64, unique=True)
    short_url = models.URLField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PaymentLink {self.razorpay_payment_link_id} for {self.sale.invoice_no}"


class PaymentEvent(models.Model):
    """
    Every webhook delivery from Razorpay, recorded verbatim. `razorpay_event_id`
    is unique so that a webhook delivered twice (Razorpay explicitly does not
    guarantee at-most-once delivery) is processed exactly once — the row
    simply fails to insert a second time and the handler treats that as
    "already handled" (PRD Section 9).
    """

    payment_link = models.ForeignKey(
        PaymentLink, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name="payment_events")
    razorpay_event_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} ({self.razorpay_event_id})"
