"""
Purchase write-path: business record + stock-in in one DB transaction (PRD R1).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.inventory.models import StockMovement
from apps.masters.models import Product

from .models import Purchase, PurchaseItem


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


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

    purchase = Purchase.objects.create(
        supplier=supplier,
        supplier_invoice_no=(supplier_invoice_no or "").strip(),
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
