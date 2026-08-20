"""
Day 14 — email outbox helpers.

Enqueue inside `transaction.atomic()` alongside business writes. Never call
`send_mail` from request/handlers for ops alerts — drain the outbox instead.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from django.db import transaction
from django.utils import timezone

from apps.core.models import EmailOutbox


def _normalize_recipients(to: str | Iterable[str]) -> list[str]:
    if isinstance(to, str):
        parts = [p.strip() for p in to.split(",")]
    else:
        parts = [str(p).strip() for p in to]
    return [p for p in parts if p]


@transaction.atomic
def enqueue_email(
    *,
    to: str | Sequence[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    idempotency_key: str | None = None,
    max_attempts: int = 5,
) -> EmailOutbox | None:
    """
    Persist an email intent. Returns None when there are no recipients.
    If ``idempotency_key`` already exists, returns the existing row (no duplicate).
    """
    recipients = _normalize_recipients(to)
    if not recipients:
        return None

    if idempotency_key:
        existing = EmailOutbox.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    return EmailOutbox.objects.create(
        to_addresses=recipients,
        subject=subject[:255],
        body_text=body_text,
        body_html=body_html or "",
        status=EmailOutbox.Status.PENDING,
        max_attempts=max_attempts,
        next_attempt_at=timezone.now(),
        idempotency_key=idempotency_key or None,
    )
