"""
Reports Set 1 — Django ORM implementations (PRD Section 8).

Day 11: report screens. Day 12: matching raw SQL in sql_raw.py + docs/SQL.md.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from django.db.models import Count, DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.core.query import annotate_stock_qty
from apps.masters.models import Customer, Product
from apps.purchases.models import Purchase
from apps.sales.models import Sale, SaleItem


ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)


def _as_aware_range(date_from: date, date_to: date):
    """Inclusive calendar range → aware datetimes for DateTimeField filters."""
    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
    return start, end


def default_date_range(days: int = 30) -> tuple[date, date]:
    today = timezone.localdate()
    return today - timedelta(days=days - 1), today


# ---------------------------------------------------------------------------
# 1. Daily sales totals (include zero-sales days)
# ---------------------------------------------------------------------------
def daily_sales_totals(date_from: date, date_to: date) -> list[dict]:
    start, end = _as_aware_range(date_from, date_to)
    rows = (
        Sale.objects.filter(sale_date__gte=start, sale_date__lte=end)
        .annotate(day=TruncDate("sale_date"))
        .values("day")
        .annotate(
            invoice_count=Count("id"),
            total_sales=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY),
        )
        .order_by("day")
    )
    by_day = {row["day"]: row for row in rows}

    out: list[dict] = []
    cursor = date_from
    while cursor <= date_to:
        hit = by_day.get(cursor)
        out.append(
            {
                "day": cursor,
                "invoice_count": hit["invoice_count"] if hit else 0,
                "total_sales": hit["total_sales"] if hit else ZERO,
            }
        )
        cursor += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# 2. Top 10 products by revenue / by quantity
# ---------------------------------------------------------------------------
def top_products(date_from: date, date_to: date, *, by: str = "revenue", limit: int = 10) -> list[dict]:
    start, end = _as_aware_range(date_from, date_to)
    qs = (
        SaleItem.objects.filter(sale__sale_date__gte=start, sale__sale_date__lte=end)
        .values("product_id", "product__sku", "product__name")
        .annotate(
            qty_sold=Coalesce(Sum("qty"), Value(ZERO), output_field=MONEY),
            revenue=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY),
        )
    )
    if by == "quantity":
        qs = qs.order_by("-qty_sold", "-revenue")
    else:
        qs = qs.order_by("-revenue", "-qty_sold")
    return list(qs[:limit])


# ---------------------------------------------------------------------------
# 3. Current stock valuation (qty × purchase_price)
# ---------------------------------------------------------------------------
def stock_valuation() -> dict:
    products = annotate_stock_qty(Product.objects.filter(is_active=True)).filter(stock_qty__gt=0)
    lines = []
    total_value = ZERO
    for p in products.select_related("category").order_by("name"):
        value = (p.stock_qty * p.purchase_price).quantize(Decimal("0.01"))
        total_value += value
        lines.append(
            {
                "sku": p.sku,
                "name": p.name,
                "category": p.category.name,
                "stock_qty": p.stock_qty,
                "purchase_price": p.purchase_price,
                "value": value,
            }
        )
    return {"lines": lines, "total_value": total_value, "product_count": len(lines)}


# ---------------------------------------------------------------------------
# 4. Products at or below reorder level
# ---------------------------------------------------------------------------
def low_stock_products() -> list:
    return list(
        annotate_stock_qty(Product.objects.filter(is_active=True, sellable=True))
        .filter(stock_qty__lte=F("reorder_level"))
        .select_related("category")
        .order_by("stock_qty", "name")
    )


def low_stock_count() -> int:
    return (
        annotate_stock_qty(Product.objects.filter(is_active=True, sellable=True))
        .filter(stock_qty__lte=F("reorder_level"))
        .count()
    )


# ---------------------------------------------------------------------------
# 5. Customers with no purchase in the last N days
# ---------------------------------------------------------------------------
def inactive_customers(days: int = 90) -> list[dict]:
    cutoff = timezone.now() - timedelta(days=days)
    last_sale_sq = (
        Sale.objects.filter(customer_id=OuterRef("pk"))
        .order_by("-sale_date")
        .values("sale_date")[:1]
    )
    qs = (
        Customer.objects.annotate(last_purchase_at=Subquery(last_sale_sq))
        .filter(Q(last_purchase_at__isnull=True) | Q(last_purchase_at__lt=cutoff))
        .order_by("last_purchase_at", "name")
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "last_purchase_at": c.last_purchase_at,
        }
        for c in qs
    ]


# ---------------------------------------------------------------------------
# 6. Supplier-wise purchase totals + distinct product count
# ---------------------------------------------------------------------------
def supplier_purchase_totals(date_from: date, date_to: date) -> list[dict]:
    qs = (
        Purchase.objects.filter(purchase_date__gte=date_from, purchase_date__lte=date_to)
        .values("supplier_id", "supplier__name")
        .annotate(
            purchase_count=Count("id"),
            total_amount=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY),
            distinct_products=Count("items__product_id", distinct=True),
        )
        .order_by("-total_amount", "supplier__name")
    )
    return list(qs)


# ---------------------------------------------------------------------------
# 7. Profit margin per product (divide-by-zero safe)
# ---------------------------------------------------------------------------
def profit_margin_by_product(date_from: date, date_to: date) -> list[dict]:
    start, end = _as_aware_range(date_from, date_to)
    rows = (
        SaleItem.objects.filter(sale__sale_date__gte=start, sale__sale_date__lte=end)
        .values("product_id", "product__sku", "product__name", "product__purchase_price")
        .annotate(
            qty_sold=Coalesce(Sum("qty"), Value(ZERO), output_field=MONEY),
            revenue=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY),
        )
        .order_by("product__name")
    )
    out = []
    for row in rows:
        qty = row["qty_sold"] or ZERO
        revenue = row["revenue"] or ZERO
        cost = (qty * row["product__purchase_price"]).quantize(Decimal("0.01"))
        profit = revenue - cost
        if revenue == 0:
            margin_pct = None
        else:
            margin_pct = ((profit / revenue) * Decimal("100")).quantize(Decimal("0.01"))
        out.append(
            {
                "sku": row["product__sku"],
                "name": row["product__name"],
                "qty_sold": qty,
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "margin_pct": margin_pct,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 8. Dead stock — on hand, zero movement in N days
# ---------------------------------------------------------------------------
def dead_stock(days: int = 60) -> list:
    cutoff = timezone.now() - timedelta(days=days)
    from apps.inventory.models import StockMovement

    recent_ids = (
        StockMovement.objects.filter(created_at__gte=cutoff)
        .values_list("product_id", flat=True)
        .distinct()
    )
    return list(
        annotate_stock_qty(Product.objects.filter(is_active=True))
        .filter(stock_qty__gt=0)
        .exclude(id__in=recent_ids)
        .select_related("category")
        .order_by("-stock_qty", "name")
    )


# ---------------------------------------------------------------------------
# 9. Data integrity — line items vs header totals
# ---------------------------------------------------------------------------
def invoice_integrity_issues() -> list[dict]:
    """
    Flag sales where SUM(line.amount) != subtotal, or
    total_amount != subtotal - discount + tax.
    """
    qs = (
        Sale.objects.annotate(
            lines_sum=Coalesce(Sum("items__amount"), Value(ZERO), output_field=MONEY),
        )
        .annotate(
            expected_total=ExpressionWrapper(
                F("subtotal") - F("discount") + F("tax"),
                output_field=MONEY,
            )
        )
        .filter(~Q(lines_sum=F("subtotal")) | ~Q(total_amount=F("expected_total")))
        .order_by("-sale_date", "-id")
        .values(
            "id",
            "invoice_no",
            "sale_date",
            "subtotal",
            "discount",
            "tax",
            "total_amount",
            "lines_sum",
            "expected_total",
        )
    )
    return list(qs)


# ---------------------------------------------------------------------------
# Dashboard (Module G)
# ---------------------------------------------------------------------------
def dashboard_metrics() -> dict:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    today_start, today_end = _as_aware_range(today, today)
    month_start_dt, month_end_dt = _as_aware_range(month_start, today)

    today_sales = Sale.objects.filter(sale_date__gte=today_start, sale_date__lte=today_end).aggregate(
        total=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY),
        count=Count("id"),
    )
    month_sales = Sale.objects.filter(sale_date__gte=month_start_dt, sale_date__lte=month_end_dt).aggregate(
        total=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY),
        count=Count("id"),
    )
    pending_total = Sale.objects.filter(
        payment_status__in=[Sale.PaymentStatus.PENDING, Sale.PaymentStatus.PARTIAL]
    ).aggregate(total=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY))["total"]

    top5 = top_products(month_start, today, by="revenue", limit=5)

    return {
        "today_total": today_sales["total"],
        "today_count": today_sales["count"],
        "month_total": month_sales["total"],
        "month_count": month_sales["count"],
        "low_stock_count": low_stock_count(),
        "pending_payment_total": pending_total,
        "top_products": top5,
        "today": today,
        "month_start": month_start,
    }
