from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding created/updated timestamps to every model that needs them."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """
    Generic audit trail. Written for sensitive/administrative actions (e.g.
    master data edits, adjustments, permission changes) so that "who changed
    what, when" can always be answered without digging through StockMovement.
    """

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.model_name}#{self.object_id} by {self.user_id}"


class EmailOutbox(models.Model):
    """
    Day 14 — transactional email outbox (PRD §7.4).

    Callers write intent in the same DB transaction as business work.
    `drain_email_outbox` sends via SES/SMTP and retries on failure so a
    transient SES outage never blocks the request or loses the email.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    to_addresses = models.JSONField(default=list)
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_error = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(max_length=128, blank=True, null=True, unique=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
        ]
        verbose_name_plural = "email outbox"

    def __str__(self):
        return f"EmailOutbox#{self.pk} [{self.status}] {self.subject[:40]}"
