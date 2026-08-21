"""Day 15 — Module F payments: webhook idempotency, signature, reconcile."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import CASHIER, OWNER
from apps.masters.models import Category, Customer, Product, Supplier
from apps.payments.models import PaymentEvent, PaymentLink
from apps.payments.services import (
    PaymentsConfigError,
    WebhookSignatureError,
    create_payment_link_for_sale,
    payment_reconciliation_rows,
    process_webhook,
    verify_webhook_signature,
)
from apps.purchases.services import create_purchase_with_stock
from apps.sales.models import Sale
from apps.sales.services import create_sale_with_stock

User = get_user_model()


@pytest.fixture
def roles(db):
    call_command("bootstrap_roles")


@pytest.fixture
def user_factory(db, roles):
    def make(username, group_name, **extra):
        user = User.objects.create_user(username=username, password="pass1234!", **extra)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    return make


@pytest.fixture
def pending_sale(db, user_factory):
    owner = user_factory("pay_owner", OWNER)
    cat = Category.objects.create(name="Pay Cat")
    supplier = Supplier.objects.create(name="Pay Sup", phone="9333333333")
    customer = Customer.objects.create(name="Pay Cust", phone="9444444444")
    product = Product.objects.create(
        sku="PAY-1",
        name="Paid Widget",
        category=cat,
        purchase_price=Decimal("10.00"),
        sale_price=Decimal("50.00"),
    )
    create_purchase_with_stock(
        supplier=supplier,
        purchase_date=timezone.localdate(),
        supplier_invoice_no="P1",
        lines=[{"product": product, "qty": Decimal("5"), "rate": product.purchase_price}],
        user=owner,
    )
    sale = create_sale_with_stock(
        customer=customer,
        sale_date=timezone.now(),
        lines=[
            {
                "product": product,
                "qty": Decimal("1"),
                "rate": Decimal("50.00"),
                "discount": Decimal("0"),
            }
        ],
        header_discount=Decimal("0"),
        tax=Decimal("0"),
        payment_status=Sale.PaymentStatus.PENDING,
        user=owner,
    )
    return {"owner": owner, "sale": sale, "customer": customer}


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.django_db
def test_create_link_requires_keys(pending_sale, settings):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    with pytest.raises(PaymentsConfigError):
        create_payment_link_for_sale(pending_sale["sale"])


@pytest.mark.django_db
def test_create_link_rejects_live_keys(pending_sale, settings):
    settings.RAZORPAY_KEY_ID = "rzp_live_forbidden"
    settings.RAZORPAY_KEY_SECRET = "secret"
    with pytest.raises(PaymentsConfigError, match="Live"):
        create_payment_link_for_sale(pending_sale["sale"])


@pytest.mark.django_db
def test_create_payment_link_persists(pending_sale, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_abc"
    settings.RAZORPAY_KEY_SECRET = "secret"
    fake = {
        "id": "plink_test_1",
        "short_url": "https://rzp.io/i/test1",
        "amount": 5000,
        "status": "created",
    }
    with patch("apps.payments.services._razorpay_request", return_value=fake):
        link = create_payment_link_for_sale(pending_sale["sale"])
    assert link.razorpay_payment_link_id == "plink_test_1"
    assert link.short_url.endswith("test1")
    assert link.amount == pending_sale["sale"].total_amount
    assert link.status == PaymentLink.Status.CREATED


@pytest.mark.django_db
def test_webhook_rejects_bad_signature(settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
    body = b'{"event":"payment_link.paid"}'
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(body, "not-valid")


@pytest.mark.django_db
def test_webhook_marks_sale_paid_and_is_idempotent(pending_sale, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
    sale = pending_sale["sale"]
    link = PaymentLink.objects.create(
        sale=sale,
        razorpay_payment_link_id="plink_paid_1",
        short_url="https://rzp.io/i/paid1",
        amount=sale.total_amount,
        status=PaymentLink.Status.CREATED,
    )
    payload = {
        "event_id": "evt_unique_1",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_paid_1",
                    "amount": int(sale.total_amount * 100),
                    "amount_paid": int(sale.total_amount * 100),
                    "notes": {"sale_id": str(sale.pk), "invoice_no": sale.invoice_no},
                }
            }
        },
    }
    raw = json.dumps(payload).encode()
    sig = _sign(raw, "whsec")

    first = process_webhook(raw, sig)
    assert first["status"] == "processed"
    sale.refresh_from_db()
    link.refresh_from_db()
    assert sale.payment_status == Sale.PaymentStatus.PAID
    assert link.status == PaymentLink.Status.PAID
    assert PaymentEvent.objects.filter(razorpay_event_id="evt_unique_1").count() == 1

    second = process_webhook(raw, sig)
    assert second["status"] == "duplicate"
    assert PaymentEvent.objects.filter(razorpay_event_id="evt_unique_1").count() == 1


@pytest.mark.django_db
def test_webhook_view_forbidden_without_valid_signature(client, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
    url = reverse("razorpay_webhook")
    resp = client.post(
        url,
        data=b'{"event":"x"}',
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE="bad",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_webhook_view_accepts_valid_signature(client, pending_sale, settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
    sale = pending_sale["sale"]
    PaymentLink.objects.create(
        sale=sale,
        razorpay_payment_link_id="plink_view_1",
        short_url="https://rzp.io/i/v1",
        amount=sale.total_amount,
    )
    payload = {
        "event_id": "evt_view_1",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_view_1",
                    "amount": int(sale.total_amount * 100),
                    "notes": {"sale_id": str(sale.pk)},
                }
            }
        },
    }
    raw = json.dumps(payload).encode()
    resp = client.post(
        reverse("razorpay_webhook"),
        data=raw,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=_sign(raw, "whsec"),
    )
    assert resp.status_code == 200
    sale.refresh_from_db()
    assert sale.payment_status == Sale.PaymentStatus.PAID


@pytest.mark.django_db
def test_reconcile_detects_books_paid_without_gateway(pending_sale):
    sale = pending_sale["sale"]
    sale.payment_status = Sale.PaymentStatus.PAID
    sale.save(update_fields=["payment_status"])
    issues = payment_reconciliation_rows()
    assert any(i["kind"] == "books_paid_no_gateway" and i["sale_id"] == sale.pk for i in issues)


@pytest.mark.django_db
def test_cashier_can_post_send_link_when_configured(client, pending_sale, user_factory, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_x"
    settings.RAZORPAY_KEY_SECRET = "secret"
    cashier = user_factory("pay_cashier", CASHIER)
    client.force_login(cashier)
    fake = {
        "id": "plink_ui_1",
        "short_url": "https://rzp.io/i/ui1",
        "amount": 5000,
    }
    with patch("apps.payments.services._razorpay_request", return_value=fake):
        resp = client.post(reverse("payments:send_payment_link", args=[pending_sale["sale"].pk]))
    assert resp.status_code == 302
    assert PaymentLink.objects.filter(razorpay_payment_link_id="plink_ui_1").exists()


@pytest.mark.django_db
def test_cashier_cannot_open_payment_reconcile(client, user_factory):
    cashier = user_factory("pay_c2", CASHIER)
    client.force_login(cashier)
    resp = client.get(reverse("payments:reconcile"))
    assert resp.status_code == 403
