"""
Shared queryset helpers for Day 10 performance work.

Prefer Subquery aggregates over JOIN+GROUP BY so list pages (and their
COUNT(*) for pagination) do not multiply against 50k+ child rows.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, DecimalField, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce


def annotate_stock_qty(queryset):
    """Annotate each product with stock_qty = SUM(stock_movements.qty_delta)."""
    from apps.inventory.models import StockMovement

    stock_sq = (
        StockMovement.objects.filter(product_id=OuterRef("pk"))
        .values("product_id")
        .annotate(total=Sum("qty_delta"))
        .values("total")[:1]
    )
    return queryset.annotate(
        stock_qty=Coalesce(
            Subquery(stock_sq, output_field=DecimalField(max_digits=14, decimal_places=2)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


def annotate_line_count(queryset, *, related_model, fk_field: str):
    """
    Annotate parent rows with line_count via a correlated Subquery.

    related_model: SaleItem / PurchaseItem class
    fk_field: "sale_id" / "purchase_id"
    """
    count_sq = (
        related_model.objects.filter(**{fk_field: OuterRef("pk")})
        .values(fk_field)
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    return queryset.annotate(
        line_count=Coalesce(
            Subquery(count_sq, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        )
    )
