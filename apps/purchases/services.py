"""
Purchase write-path: business record + stock-in in one DB transaction (PRD R1).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.inventory.models import StockMovement
from apps.masters.models import Product

from .models import Purchase, PurchaseItem, PurchaseSequence


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def financial_year_for(dt: datetime | date) -> str:
    """Indian FY label, e.g. 2025-04-01 -> '2025-26'."""
    year, month = dt.year, dt.month
    if month < 4:
        return f"{year - 1}-{str(year)[2:]}"
    return f"{year}-{str(year + 1)[2:]}"


def format_supplier_invoice_no(fy: str, number: int) -> str:
    return f"PINV-{fy}-{number:06d}"


def peek_next_supplier_invoice_no(*, when: datetime | date | None = None) -> str:
    """Preview of the next auto supplier invoice number without allocating it."""
    when = when or timezone.localdate()
    fy = financial_year_for(timezone.localtime(when) if isinstance(when, datetime) and timezone.is_aware(when) else when)
    seq = PurchaseSequence.objects.filter(financial_year=fy).first()
    n = (seq.last_number if seq else 0) + 1
    return format_supplier_invoice_no(fy, n)


def next_supplier_invoice_no(*, when: datetime | date | None = None) -> str:
    """
    Atomically allocate the next supplier invoice number for the financial year.

    Must be called inside `transaction.atomic()`.
    """
    when = when or timezone.localdate()
    fy = financial_year_for(timezone.localtime(when) if isinstance(when, datetime) and timezone.is_aware(when) else when)

    try:
        seq = PurchaseSequence.objects.select_for_update().get(financial_year=fy)
    except PurchaseSequence.DoesNotExist:
        try:
            PurchaseSequence.objects.create(financial_year=fy, last_number=0)
        except IntegrityError:
            pass
        seq = PurchaseSequence.objects.select_for_update().get(financial_year=fy)

    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return format_supplier_invoice_no(fy, seq.last_number)


@transaction.atomic
def create_purchase_with_stock(
    *,
    supplier,
    purchase_date,
    supplier_invoice_no: str,
    lines: list[dict],
    user,
) -> Purchase:
    """
    Create a Purchase + PurchaseItems and matching StockMovement rows (+qty)
    inside a single atomic block. A crash mid-way leaves no partial stock.

    Each line dict: {"product": Product|id, "qty": Decimal, "rate": Decimal}
    """
    if not lines:
        raise ValueError("A purchase needs at least one line item.")

    invoice_no = (supplier_invoice_no or "").strip()
    if not invoice_no:
        invoice_no = next_supplier_invoice_no(when=purchase_date)

    purchase = Purchase.objects.create(
        supplier=supplier,
        supplier_invoice_no=invoice_no,
        purchase_date=purchase_date,
        total_amount=Decimal("0.00"),
        created_by=user,
    )

    total = Decimal("0.00")
    for line in lines:
        product = line["product"]
        if not isinstance(product, Product):
            product = Product.objects.select_for_update().get(pk=product)
        else:
            product = Product.objects.select_for_update().get(pk=product.pk)

        qty = money(line["qty"])
        rate = money(line["rate"])
        if qty <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if rate < 0:
            raise ValueError("Rate cannot be negative.")

        amount = money(qty * rate)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            qty=qty,
            rate=rate,
            amount=amount,
        )
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.MovementType.PURCHASE,
            qty_delta=qty,
            reference_type=StockMovement.ReferenceType.PURCHASE,
            reference_id=purchase.pk,
            reason=f"Purchase #{purchase.pk}"
            + (f" / {purchase.supplier_invoice_no}" if purchase.supplier_invoice_no else ""),
            created_by=user,
        )
        total += amount

    purchase.total_amount = money(total)
    purchase.save(update_fields=["total_amount"])
    return purchase
