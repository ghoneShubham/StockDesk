"""
Adjustment write-path: business record + StockMovement in one transaction (PRD R1).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.masters.models import Product

from .models import Adjustment, StockMovement


class AdjustmentError(ValueError):
    """Business-rule failure that rolls the whole adjustment back."""


def money_qty(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def current_stock(product_id: int) -> Decimal:
    total = StockMovement.objects.filter(product_id=product_id).aggregate(s=Sum("qty_delta"))["s"]
    return total or Decimal("0.00")


@transaction.atomic
def apply_adjustment(
    *,
    product,
    qty_delta,
    reason: str,
    notes: str = "",
    user,
) -> Adjustment:
    """
    Create an Adjustment and matching StockMovement inside one atomic block.

    Negative deltas (damage/theft/correction down) are rejected if they would
    drive stock below zero. Opening stock / positive corrections increase stock.
    """
    qty_delta = money_qty(qty_delta)
    if qty_delta == 0:
        raise AdjustmentError("Quantity change cannot be zero.")
    if reason not in Adjustment.Reason.values:
        raise AdjustmentError("Select a valid reason.")

    if not isinstance(product, Product):
        product = Product.objects.select_for_update().get(pk=product)
    else:
        product = Product.objects.select_for_update().get(pk=product.pk)

    available = current_stock(product.pk)
    if qty_delta < 0 and available + qty_delta < 0:
        raise AdjustmentError(
            f"Insufficient stock for {product.sku} - available {available}, "
            f"adjustment {qty_delta}."
        )

    # Opening stock uses OPENING movement type; everything else is ADJUSTMENT.
    if reason == Adjustment.Reason.OPENING_STOCK:
        movement_type = StockMovement.MovementType.OPENING
    else:
        movement_type = StockMovement.MovementType.ADJUSTMENT

    reason_label = dict(Adjustment.Reason.choices).get(reason, reason)
    movement_reason = reason_label
    if notes:
        movement_reason = f"{reason_label}: {notes.strip()[:200]}"

    adjustment = Adjustment.objects.create(
        product=product,
        qty_delta=qty_delta,
        reason=reason,
        notes=(notes or "").strip(),
        created_by=user,
    )
    movement = StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        qty_delta=qty_delta,
        reference_type=StockMovement.ReferenceType.ADJUSTMENT,
        reference_id=adjustment.pk,
        reason=movement_reason,
        created_by=user,
    )
    adjustment.stock_movement = movement
    adjustment.save(update_fields=["stock_movement"])
    return adjustment
