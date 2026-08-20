"""Day 14 — email outbox enqueue + drain."""

from __future__ import annotations

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.core.models import EmailOutbox
from apps.core.outbox import enqueue_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="ops@stockdesk.test",
)
class EmailOutboxTests(TestCase):
    def test_enqueue_and_drain_sends_mail(self):
        row = enqueue_email(
            to=["owner@example.com"],
            subject="Hello",
            body_text="Body",
            idempotency_key="test-key-1",
        )
        assert row is not None
        assert row.status == EmailOutbox.Status.PENDING

        call_command("drain_email_outbox")

        row.refresh_from_db()
        assert row.status == EmailOutbox.Status.SENT
        assert row.sent_at is not None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Hello"
        assert mail.outbox[0].to == ["owner@example.com"]

    def test_idempotency_key_dedupes(self):
        a = enqueue_email(
            to="a@example.com",
            subject="One",
            body_text="x",
            idempotency_key="same-key",
        )
        b = enqueue_email(
            to="b@example.com",
            subject="Two",
            body_text="y",
            idempotency_key="same-key",
        )
        assert a is not None and b is not None
        assert a.pk == b.pk
        assert EmailOutbox.objects.count() == 1

    def test_empty_recipients_returns_none(self):
        assert enqueue_email(to=[], subject="x", body_text="y") is None
        assert EmailOutbox.objects.count() == 0

    def test_drain_marks_failed_after_max_attempts(self):
        from unittest.mock import patch

        row = enqueue_email(
            to=["owner@example.com"],
            subject="Will fail",
            body_text="x",
            max_attempts=1,
        )
        assert row is not None

        with patch(
            "apps.core.management.commands.drain_email_outbox.EmailMultiAlternatives.send",
            side_effect=RuntimeError("simulated SES failure"),
        ):
            call_command("drain_email_outbox")

        row.refresh_from_db()
        assert row.status == EmailOutbox.Status.FAILED
        assert row.attempts >= 1
        assert "simulated SES failure" in row.last_error


@override_settings(LOW_STOCK_ALERT_RECIPIENTS=["owner@example.com"])
class AlertCommandsTests(TestCase):
    def test_alert_low_stock_force_enqueues(self):
        call_command("alert_low_stock", "--force")
        assert EmailOutbox.objects.filter(idempotency_key__startswith="low-stock-").exists()

    def test_alert_dead_stock_force_enqueues(self):
        call_command("alert_dead_stock", "--force")
        assert EmailOutbox.objects.filter(idempotency_key__startswith="dead-stock-").exists()
