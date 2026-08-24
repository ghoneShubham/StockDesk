"""
Sale write-path: invoice numbering + stock-out in one DB transaction (PRD R1–R3).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import StockMovement
from apps.masters.models import Product

from .models import InvoiceSequence, Sale, SaleItem


class InsufficientStockError(ValueError):
    """Raised when a sale would drive stock negative (PRD R2)."""


class SaleValidationError(ValueError):
    """Raised for business-rule failures that should roll the whole sale back."""


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def financial_year_for(dt: datetime | date) -> str:
    """Indian FY label, e.g. 2025-04-01 -> '2025-26'."""
    if isinstance(dt, datetime):
        year, month = dt.year, dt.month
    else:
        year, month = dt.year, dt.month
    if month < 4:
        return f"{year - 1}-{str(year)[2:]}"
    return f"{year}-{str(year + 1)[2:]}"


def current_stock(product_id: int) -> Decimal:
    total = StockMovement.objects.filter(product_id=product_id).aggregate(s=Sum("qty_delta"))["s"]
    return total or Decimal("0.00")


def next_invoice_no(*, when: datetime | None = None) -> str:
    """
    Atomically allocate the next invoice number for the financial year.

    Must be called inside `transaction.atomic()`. Locks the InvoiceSequence
    row with `select_for_update()` — never use max(id)+1 in Python (PRD R3).
    """
    when = when or timezone.now()
    fy = financial_year_for(timezone.localtime(when) if timezone.is_aware(when) else when)

    try:
        seq = InvoiceSequence.objects.select_for_update().get(financial_year=fy)
    except InvoiceSequence.DoesNotExist:
        try:
            InvoiceSequence.objects.create(financial_year=fy, last_number=0)
        except IntegrityError:
            pass
        seq = InvoiceSequence.objects.select_for_update().get(financial_year=fy)

    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"INV-{fy}-{seq.last_number:06d}"


def peek_next_invoice_no(*, when: datetime | None = None) -> str:
    """Preview of the next sales invoice number without allocating it."""
    when = when or timezone.now()
    fy = financial_year_for(timezone.localtime(when) if timezone.is_aware(when) else when)
    seq = InvoiceSequence.objects.filter(financial_year=fy).first()
    n = (seq.last_number if seq else 0) + 1
    return f"INV-{fy}-{n:06d}"


@transaction.atomic
def create_sale_with_stock(
    *,
    customer,
    sale_date,
    lines: list[dict],
    header_discount=Decimal("0"),
    tax=Decimal("0"),
    payment_status: str = Sale.PaymentStatus.PENDING,
    amount_paid=Decimal("0"),
    user,
) -> Sale:
    """
    Create Sale + SaleItems and matching StockMovement rows (-qty) inside one
    atomic block. Products are locked in pk order so concurrent cashiers cannot
    oversell the last unit (PRD R2).
    """
    if not lines:
        raise SaleValidationError("A sale needs at least one line item.")

    header_discount = money(header_discount)
    tax = money(tax)
    if header_discount < 0:
        raise SaleValidationError("Invoice discount cannot be negative.")
    if tax < 0:
        raise SaleValidationError("Tax cannot be negative.")

    # Normalize + validate lines first (no locks yet).
    normalized: list[dict] = []
    for line in lines:
        product = line.get("product", line.get("product_id"))
        if product is None:
            raise SaleValidationError("Each line needs a product.")
        product_id = product.pk if isinstance(product, Product) else int(product)
        qty = money(line["qty"])
        rate = money(line["rate"])
        discount = money(line.get("discount") or 0)
        if qty <= 0:
            raise SaleValidationError("Quantity must be greater than zero.")
        if rate < 0:
            raise SaleValidationError("Rate cannot be negative.")
        if discount < 0:
            raise SaleValidationError("Line discount cannot be negative.")
        line_gross = money(qty * rate)
        if discount > line_gross:
            raise SaleValidationError("Discount cannot exceed the line amount.")
        amount = money(line_gross - discount)
        normalized.append(
            {
                "product_id": product_id,
                "qty": qty,
                "rate": rate,
                "discount": discount,
                "amount": amount,
            }
        )

    # Lock products in stable order to avoid deadlocks across concurrent sales.
    product_ids = sorted({row["product_id"] for row in normalized})
    locked = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }
    if len(locked) != len(product_ids):
        raise SaleValidationError("One or more products no longer exist.")

    for product_id in product_ids:
        product = locked[product_id]
        if not product.is_active or not product.sellable:
            raise SaleValidationError(f"{product.sku} is not sellable.")

    # Aggregate demand per product (same SKU on multiple lines).
    demand: dict[int, Decimal] = {}
    for row in normalized:
        demand[row["product_id"]] = demand.get(row["product_id"], Decimal("0")) + row["qty"]

    for product_id, needed in demand.items():
        available = current_stock(product_id)
        if available < needed:
            product = locked[product_id]
            raise InsufficientStockError(
                f"Insufficient stock for {product.sku} - available {available}, needed {needed}."
            )

    if sale_date is None:
        sale_date = timezone.now()
    elif isinstance(sale_date, date) and not isinstance(sale_date, datetime):
        sale_date = timezone.make_aware(
            datetime.combine(sale_date, datetime.min.time().replace(hour=12))
        )

    invoice_no = next_invoice_no(when=sale_date if isinstance(sale_date, datetime) else timezone.now())

    subtotal = money(sum((row["amount"] for row in normalized), Decimal("0")))
    if header_discount > subtotal:
        raise SaleValidationError("Invoice discount cannot exceed the subtotal.")
    total_amount = money(subtotal - header_discount + tax)

    status = payment_status or Sale.PaymentStatus.PENDING
    paid = money(amount_paid or 0)
    if paid < 0:
        raise SaleValidationError("Amount paid cannot be negative.")
    if status == Sale.PaymentStatus.PAID:
        paid = total_amount
    elif status == Sale.PaymentStatus.PENDING:
        paid = money(0)
    elif status == Sale.PaymentStatus.PARTIAL:
        if paid <= 0:
            raise SaleValidationError("Enter how much was paid for a partial payment.")
        if paid >= total_amount:
            raise SaleValidationError(
                "Partial payment must be less than the invoice total. Use Paid if fully settled."
            )
    else:
        if paid > total_amount:
            raise SaleValidationError("Amount paid cannot exceed the invoice total.")

    sale = Sale.objects.create(
        invoice_no=invoice_no,
        customer=customer,
        sale_date=sale_date,
        subtotal=subtotal,
        discount=header_discount,
        tax=tax,
        total_amount=total_amount,
        amount_paid=paid,
        payment_status=status,
        created_by=user,
    )

    for row in normalized:
        product = locked[row["product_id"]]
        SaleItem.objects.create(
            sale=sale,
            product=product,
            qty=row["qty"],
            rate=row["rate"],
            discount=row["discount"],
            amount=row["amount"],
        )
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.MovementType.SALE,
            qty_delta=-row["qty"],
            reference_type=StockMovement.ReferenceType.SALE,
            reference_id=sale.pk,
            reason=f"Sale {sale.invoice_no}",
            created_by=user,
        )

    return sale
