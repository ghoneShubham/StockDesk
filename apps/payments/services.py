"""
Day 15 — Razorpay Payment Links (test mode) + webhook processing (PRD §9).

Live keys are forbidden. When RAZORPAY_KEY_ID/SECRET are empty, create_link
raises a clear configuration error (no silent fake success).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.payments.models import PaymentEvent, PaymentLink
from apps.sales.models import Sale

logger = logging.getLogger("stockdesk.payments")

RAZORPAY_API = "https://api.razorpay.com/v1"


class PaymentsConfigError(ValueError):
    """Missing or invalid Razorpay settings."""


class PaymentsAPIError(ValueError):
    """Razorpay API rejected the request."""


class WebhookSignatureError(ValueError):
    """Webhook signature missing or invalid."""


def _require_test_keys() -> tuple[str, str]:
    key_id = (settings.RAZORPAY_KEY_ID or "").strip()
    key_secret = (settings.RAZORPAY_KEY_SECRET or "").strip()
    if not key_id or not key_secret:
        raise PaymentsConfigError(
            "Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET "
            "(test mode only) in .env."
        )
    if key_id.startswith("rzp_live"):
        raise PaymentsConfigError("Live Razorpay keys are forbidden — use test mode keys only.")
    return key_id, key_secret


def _basic_auth_header(key_id: str, key_secret: str) -> str:
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    return f"Basic {token}"


def _amount_paise(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal("1")))


def create_payment_link_for_sale(sale: Sale) -> PaymentLink:
    """
    Call Razorpay Payment Links API and persist PaymentLink.
    Only for sales that are not already fully paid.
    """
    if sale.payment_status == Sale.PaymentStatus.PAID:
        raise PaymentsConfigError(f"Sale {sale.invoice_no} is already paid.")

    key_id, key_secret = _require_test_keys()
    amount = sale.total_amount
    if amount <= 0:
        raise PaymentsConfigError("Sale total must be positive to create a payment link.")

    customer = {}
    if sale.customer_id:
        customer = {
            "name": (sale.customer.name or "Customer")[:100],
            "contact": (sale.customer.phone or "")[:15] or None,
        }
        customer = {k: v for k, v in customer.items() if v}

    body = {
        "amount": _amount_paise(amount),
        "currency": "INR",
        "accept_partial": False,
        "description": f"StockDesk invoice {sale.invoice_no}",
        "customer": customer or {"name": "Walk-in customer"},
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {
            "sale_id": str(sale.pk),
            "invoice_no": sale.invoice_no,
        },
    }

    data = _razorpay_request("POST", "/payment_links", body, key_id, key_secret)
    link_id = data.get("id") or ""
    short_url = data.get("short_url") or ""
    if not link_id or not short_url:
        raise PaymentsAPIError(f"Unexpected Razorpay response: {data!r}")

    return PaymentLink.objects.create(
        sale=sale,
        razorpay_payment_link_id=link_id,
        short_url=short_url,
        amount=amount,
        status=PaymentLink.Status.CREATED,
    )


def _razorpay_request(
    method: str, path: str, body: dict, key_id: str, key_secret: str
) -> dict[str, Any]:
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{RAZORPAY_API}{path}",
        data=payload if method != "GET" else None,
        method=method,
        headers={
            "Authorization": _basic_auth_header(key_id, key_secret),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode(errors="replace")
        raise PaymentsAPIError(f"Razorpay HTTP {exc.code}: {err_body}") from exc
    except urllib.error.URLError as exc:
        raise PaymentsAPIError(f"Razorpay network error: {exc}") from exc

    return json.loads(raw) if raw else {}


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> None:
    secret = (settings.RAZORPAY_WEBHOOK_SECRET or "").strip()
    if not secret:
        raise WebhookSignatureError("RAZORPAY_WEBHOOK_SECRET is not configured.")
    if not signature:
        raise WebhookSignatureError("Missing X-Razorpay-Signature header.")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookSignatureError("Invalid webhook signature.")


def process_webhook(raw_body: bytes, signature: str | None) -> dict[str, Any]:
    """
    Verify signature, record PaymentEvent once, mark sale paid when appropriate.
    Idempotent: duplicate event id → success without double-updating.
    """
    verify_webhook_signature(raw_body, signature)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebhookSignatureError("Invalid JSON body.") from exc

    event_id = str(payload.get("event_id") or payload.get("id") or "")
    event_type = str(payload.get("event") or "")
    if not event_id:
        # Some payloads nest id differently; fall back to hash of body for uniqueness.
        event_id = hashlib.sha256(raw_body).hexdigest()

    amount = _extract_amount(payload)
    payment_link, sale = _resolve_link_and_sale(payload)

    try:
        with transaction.atomic():
            event = PaymentEvent.objects.create(
                payment_link=payment_link,
                sale=sale,
                razorpay_event_id=event_id,
                event_type=event_type or "unknown",
                amount=amount,
                payload=payload,
            )
            _apply_paid_side_effects(event, payment_link, sale, event_type, amount)
            event.processed_at = timezone.now()
            event.save(update_fields=["processed_at"])
            return {"status": "processed", "event_id": event_id}
    except IntegrityError:
        logger.info("Duplicate Razorpay event %s — already processed", event_id)
        return {"status": "duplicate", "event_id": event_id}


def _extract_amount(payload: dict) -> Decimal:
    entity = _payment_link_entity(payload) or _payment_entity(payload) or {}
    paise = entity.get("amount") or entity.get("amount_paid") or 0
    try:
        return (Decimal(int(paise)) / Decimal("100")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _payment_link_entity(payload: dict) -> dict | None:
    try:
        return payload["payload"]["payment_link"]["entity"]
    except (KeyError, TypeError):
        return None


def _payment_entity(payload: dict) -> dict | None:
    try:
        return payload["payload"]["payment"]["entity"]
    except (KeyError, TypeError):
        return None


def _resolve_link_and_sale(payload: dict) -> tuple[PaymentLink | None, Sale | None]:
    entity = _payment_link_entity(payload) or {}
    link_id = entity.get("id") or ""
    notes = entity.get("notes") or {}
    sale = None
    sale_id = notes.get("sale_id")
    if sale_id:
        sale = Sale.objects.filter(pk=sale_id).first()

    payment_link = None
    if link_id:
        payment_link = PaymentLink.objects.select_related("sale").filter(
            razorpay_payment_link_id=link_id
        ).first()
        if payment_link and sale is None:
            sale = payment_link.sale

    if sale is None:
        # payment.captured may only include payment entity — try notes there
        pay = _payment_entity(payload) or {}
        notes = pay.get("notes") or {}
        if notes.get("sale_id"):
            sale = Sale.objects.filter(pk=notes["sale_id"]).first()

    return payment_link, sale


def _apply_paid_side_effects(
    event: PaymentEvent,
    payment_link: PaymentLink | None,
    sale: Sale | None,
    event_type: str,
    amount: Decimal,
) -> None:
    paid_events = {
        "payment_link.paid",
        "payment.captured",
        "payment_link.partially_paid",
    }
    if event_type not in paid_events and "paid" not in event_type:
        return

    if payment_link and payment_link.status != PaymentLink.Status.PAID:
        payment_link.status = PaymentLink.Status.PAID
        payment_link.save(update_fields=["status", "updated_at"])

    if sale and sale.payment_status != Sale.PaymentStatus.PAID:
        # Webhook is source of truth for paid marking (PRD §9).
        paid_so_far = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
        if paid_so_far and sale.total_amount and paid_so_far < sale.total_amount:
            sale.payment_status = Sale.PaymentStatus.PARTIAL
            sale.amount_paid = paid_so_far
        else:
            sale.payment_status = Sale.PaymentStatus.PAID
            sale.amount_paid = sale.total_amount
        sale.save(update_fields=["payment_status", "amount_paid"])


def payment_reconciliation_rows() -> list[dict]:
    """
    List disagreements between gateway (PaymentLink/PaymentEvent) and books (Sale).
    """
    issues: list[dict] = []

    # Gateway says paid, books still pending
    for link in PaymentLink.objects.filter(status=PaymentLink.Status.PAID).select_related("sale"):
        sale = link.sale
        if sale.payment_status == Sale.PaymentStatus.PENDING:
            issues.append(
                {
                    "kind": "gateway_paid_books_pending",
                    "invoice_no": sale.invoice_no,
                    "sale_id": sale.pk,
                    "detail": f"Link {link.razorpay_payment_link_id} paid; sale still pending",
                }
            )
        elif link.amount != sale.total_amount:
            issues.append(
                {
                    "kind": "amount_mismatch",
                    "invoice_no": sale.invoice_no,
                    "sale_id": sale.pk,
                    "detail": f"Link amount {link.amount} != sale total {sale.total_amount}",
                }
            )

    # Books say paid, no paid link / processed paid event
    paid_sales = Sale.objects.filter(payment_status=Sale.PaymentStatus.PAID)
    for sale in paid_sales.iterator(chunk_size=200):
        has_paid_link = sale.payment_links.filter(status=PaymentLink.Status.PAID).exists()
        has_paid_event = sale.payment_events.filter(
            processed_at__isnull=False,
            event_type__icontains="paid",
        ).exists() or sale.payment_events.filter(
            processed_at__isnull=False,
            event_type__icontains="captured",
        ).exists()
        if not has_paid_link and not has_paid_event:
            issues.append(
                {
                    "kind": "books_paid_no_gateway",
                    "invoice_no": sale.invoice_no,
                    "sale_id": sale.pk,
                    "detail": "Sale marked paid with no paid PaymentLink/PaymentEvent",
                }
            )

    # Orphan / unprocessed events
    for ev in PaymentEvent.objects.filter(processed_at__isnull=True)[:100]:
        issues.append(
            {
                "kind": "unprocessed_event",
                "invoice_no": ev.sale.invoice_no if ev.sale_id else "—",
                "sale_id": ev.sale_id,
                "detail": f"Event {ev.razorpay_event_id} ({ev.event_type}) not processed",
            }
        )

    return issues
