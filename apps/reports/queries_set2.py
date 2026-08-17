"""
Reports Set 2 — subquery-first then window rewrite (PRD Section 8 items 10–13).

UI ships the *_window helpers (backed by real SQL windows in sql_raw where
Django ORM cannot Window over a grouped VALUES queryset cleanly).
Subquery / Python-lag variants remain for comparison in docs/SQL.md.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import F, OuterRef, Subquery, Sum, Value, Window
from django.db.models.functions import Coalesce, RowNumber, TruncDate, TruncMonth
from django.db.models import DecimalField
from django.utils import timezone

from apps.sales.models import Sale, SaleItem

from . import sql_raw

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _aware_range(date_from: date, date_to: date):
    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
    return start, end


def _daily_totals(date_from: date, date_to: date) -> dict[date, Decimal]:
    start, end = _aware_range(date_from, date_to)
    rows = (
        Sale.objects.filter(sale_date__gte=start, sale_date__lte=end)
        .annotate(day=TruncDate("sale_date"))
        .values("day")
        .annotate(day_total=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY))
    )
    return {r["day"]: r["day_total"] for r in rows}


# ---------------------------------------------------------------------------
# 10. Running total of sales across a month, day by day
# ---------------------------------------------------------------------------
def running_total_subquery(year: int, month: int) -> list[dict]:
    """
    Subquery-style: for each calendar day, day_total + SUM of prior days
    (correlated running sum over the daily aggregate).
    """
    date_from, date_to = _month_bounds(year, month)
    by_day = _daily_totals(date_from, date_to)
    running = ZERO
    out = []
    cursor = date_from
    while cursor <= date_to:
        day_total = by_day.get(cursor, ZERO)
        running += day_total
        out.append({"day": cursor, "day_total": day_total, "running_total": running})
        cursor += timedelta(days=1)
    return out


def running_total_window(year: int, month: int) -> list[dict]:
    """SUM(day_total) OVER (ORDER BY day) — raw SQL window; zero-fills days."""
    return sql_raw.running_total_window(year, month)


# ---------------------------------------------------------------------------
# 11. Rank of each product by revenue within its category
# ---------------------------------------------------------------------------
def product_rank_subquery(date_from: date, date_to: date) -> list[dict]:
    """Rank = 1 + count of same-category products with strictly higher revenue."""
    start, end = _aware_range(date_from, date_to)
    base = list(
        SaleItem.objects.filter(sale__sale_date__gte=start, sale__sale_date__lte=end)
        .values(
            "product_id",
            "product__sku",
            "product__name",
            "product__category_id",
            "product__category__name",
        )
        .annotate(revenue=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY))
    )
    out = []
    for row in base:
        higher = sum(
            1
            for other in base
            if other["product__category_id"] == row["product__category_id"]
            and other["revenue"] > row["revenue"]
        )
        out.append(
            {
                "sku": row["product__sku"],
                "name": row["product__name"],
                "category": row["product__category__name"],
                "revenue": row["revenue"],
                "rank": higher + 1,
            }
        )
    out.sort(key=lambda r: (r["category"], r["rank"], r["sku"]))
    return out


def product_rank_window(date_from: date, date_to: date) -> list[dict]:
    """RANK() OVER (PARTITION BY category_id ORDER BY revenue DESC)."""
    return sql_raw.product_rank_window(date_from, date_to)


# ---------------------------------------------------------------------------
# 12. Month-on-month growth percentage
# ---------------------------------------------------------------------------
def mom_growth_subquery(months_back: int = 12) -> list[dict]:
    """Lag previous month in Python after TruncMonth aggregate (subquery-style)."""
    today = timezone.localdate()
    y, m = today.year, today.month
    for _ in range(months_back - 1):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    date_from = date(y, m, 1)
    start, end = _aware_range(date_from, today)
    rows = list(
        Sale.objects.filter(sale_date__gte=start, sale_date__lte=end)
        .annotate(month=TruncMonth("sale_date"))
        .values("month")
        .annotate(total=Coalesce(Sum("total_amount"), Value(ZERO), output_field=MONEY))
        .order_by("month")
    )
    out = []
    prev_total = None
    for r in rows:
        month = r["month"]
        if hasattr(month, "date"):
            month = month.date()
        total = r["total"]
        if prev_total is None or prev_total == 0:
            growth = None
        else:
            growth = ((total - prev_total) / prev_total * Decimal("100")).quantize(Decimal("0.01"))
        out.append(
            {
                "month": month,
                "total": total,
                "prev_total": prev_total,
                "growth_pct": growth,
            }
        )
        prev_total = total
    return out


def mom_growth_window(months_back: int = 12) -> list[dict]:
    """LAG(total) OVER (ORDER BY month) via raw SQL."""
    return sql_raw.mom_growth_window(months_back)


# ---------------------------------------------------------------------------
# 13. Each customer's most recent invoice (one query)
# ---------------------------------------------------------------------------
def latest_invoice_subquery() -> list[dict]:
    """Correlated subquery picking the latest sale id per customer."""
    latest_id = (
        Sale.objects.filter(customer_id=OuterRef("customer_id"))
        .order_by("-sale_date", "-id")
        .values("id")[:1]
    )
    return list(
        Sale.objects.filter(customer_id__isnull=False)
        .annotate(_latest_id=Subquery(latest_id))
        .filter(id=F("_latest_id"))
        .order_by("customer__name")
        .values(
            "customer_id",
            "customer__name",
            "customer__phone",
            "invoice_no",
            "sale_date",
            "total_amount",
            "payment_status",
        )
    )


def latest_invoice_window() -> list[dict]:
    """ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY sale_date DESC, id DESC)."""
    qs = (
        Sale.objects.filter(customer_id__isnull=False)
        .annotate(
            rn=Window(
                expression=RowNumber(),
                partition_by=[F("customer_id")],
                order_by=[F("sale_date").desc(), F("id").desc()],
            )
        )
        .filter(rn=1)
        .order_by("customer__name")
        .values(
            "customer_id",
            "customer__name",
            "customer__phone",
            "invoice_no",
            "sale_date",
            "total_amount",
            "payment_status",
        )
    )
    return list(qs)
