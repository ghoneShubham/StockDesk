"""
Hand-written raw SQL for all 13 PRD reports (`connection.cursor()`).

Parameterized — never string-interpolate user dates into SQL.
Used by Day 12 Set 2 window UIs and documented in docs/SQL.md.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import connection
from django.utils import timezone

ZERO = Decimal("0.00")


def _aware_bounds(date_from: date, date_to: date):
    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
    return start, end


def _fetch(sql: str, params=None) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Set 1
# ---------------------------------------------------------------------------
def daily_sales_totals(date_from: date, date_to: date) -> list[dict]:
    start, end = _aware_bounds(date_from, date_to)
    sql = """
        WITH days AS (
            SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS day
        ),
        agg AS (
            SELECT (sale_date AT TIME ZONE %s)::date AS day,
                   COUNT(*) AS invoice_count,
                   COALESCE(SUM(total_amount), 0) AS total_sales
            FROM sales_sale
            WHERE sale_date >= %s AND sale_date <= %s
            GROUP BY 1
        )
        SELECT d.day,
               COALESCE(a.invoice_count, 0) AS invoice_count,
               COALESCE(a.total_sales, 0) AS total_sales
        FROM days d
        LEFT JOIN agg a ON a.day = d.day
        ORDER BY d.day
    """
    tz = timezone.get_current_timezone_name()
    rows = _fetch(sql, [date_from, date_to, tz, start, end])
    for r in rows:
        r["total_sales"] = Decimal(r["total_sales"]).quantize(Decimal("0.01"))
    return rows


def top_products(date_from: date, date_to: date, *, by: str = "revenue", limit: int = 10) -> list[dict]:
    start, end = _aware_bounds(date_from, date_to)
    order = "revenue DESC, qty_sold DESC" if by != "quantity" else "qty_sold DESC, revenue DESC"
    sql = f"""
        SELECT p.id AS product_id, p.sku AS product__sku, p.name AS product__name,
               COALESCE(SUM(si.qty), 0) AS qty_sold,
               COALESCE(SUM(si.amount), 0) AS revenue
        FROM sales_saleitem si
        JOIN sales_sale s ON s.id = si.sale_id
        JOIN masters_product p ON p.id = si.product_id
        WHERE s.sale_date >= %s AND s.sale_date <= %s
        GROUP BY p.id, p.sku, p.name
        ORDER BY {order}
        LIMIT %s
    """
    rows = _fetch(sql, [start, end, limit])
    for r in rows:
        r["qty_sold"] = Decimal(r["qty_sold"]).quantize(Decimal("0.01"))
        r["revenue"] = Decimal(r["revenue"]).quantize(Decimal("0.01"))
    return rows


def stock_valuation() -> dict:
    sql = """
        SELECT p.sku, p.name, c.name AS category,
               COALESCE(SUM(m.qty_delta), 0) AS stock_qty,
               p.purchase_price,
               COALESCE(SUM(m.qty_delta), 0) * p.purchase_price AS value
        FROM masters_product p
        JOIN masters_category c ON c.id = p.category_id
        LEFT JOIN inventory_stockmovement m ON m.product_id = p.id
        WHERE p.is_active = TRUE
        GROUP BY p.id, p.sku, p.name, c.name, p.purchase_price
        HAVING COALESCE(SUM(m.qty_delta), 0) > 0
        ORDER BY p.name
    """
    lines = _fetch(sql)
    total = ZERO
    for r in lines:
        r["stock_qty"] = Decimal(r["stock_qty"]).quantize(Decimal("0.01"))
        r["purchase_price"] = Decimal(r["purchase_price"]).quantize(Decimal("0.01"))
        r["value"] = Decimal(r["value"]).quantize(Decimal("0.01"))
        total += r["value"]
    return {"lines": lines, "total_value": total, "product_count": len(lines)}


def low_stock_products() -> list[dict]:
    sql = """
        SELECT p.sku, p.name, c.name AS category_name,
               COALESCE(SUM(m.qty_delta), 0) AS stock_qty,
               p.reorder_level
        FROM masters_product p
        JOIN masters_category c ON c.id = p.category_id
        LEFT JOIN inventory_stockmovement m ON m.product_id = p.id
        WHERE p.is_active = TRUE AND p.sellable = TRUE
        GROUP BY p.id, p.sku, p.name, c.name, p.reorder_level
        HAVING COALESCE(SUM(m.qty_delta), 0) <= p.reorder_level
        ORDER BY stock_qty, p.name
    """
    return _fetch(sql)


def inactive_customers(days: int = 90) -> list[dict]:
    sql = """
        SELECT c.id, c.name, c.phone,
               (
                   SELECT MAX(s.sale_date) FROM sales_sale s WHERE s.customer_id = c.id
               ) AS last_purchase_at
        FROM masters_customer c
        WHERE NOT EXISTS (
            SELECT 1 FROM sales_sale s
            WHERE s.customer_id = c.id AND s.sale_date >= %s
        )
        ORDER BY last_purchase_at NULLS FIRST, c.name
    """
    cutoff = timezone.now() - timedelta(days=days)
    return _fetch(sql, [cutoff])


def supplier_purchase_totals(date_from: date, date_to: date) -> list[dict]:
    sql = """
        SELECT s.id AS supplier_id, s.name AS supplier__name,
               COUNT(DISTINCT p.id) AS purchase_count,
               COALESCE(SUM(p.total_amount), 0) AS total_amount,
               COUNT(DISTINCT pi.product_id) AS distinct_products
        FROM masters_supplier s
        JOIN purchases_purchase p ON p.supplier_id = s.id
        LEFT JOIN purchases_purchaseitem pi ON pi.purchase_id = p.id
        WHERE p.purchase_date >= %s AND p.purchase_date <= %s
        GROUP BY s.id, s.name
        ORDER BY total_amount DESC, s.name
    """
    rows = _fetch(sql, [date_from, date_to])
    for r in rows:
        r["total_amount"] = Decimal(r["total_amount"]).quantize(Decimal("0.01"))
    return rows


def profit_margin_by_product(date_from: date, date_to: date) -> list[dict]:
    start, end = _aware_bounds(date_from, date_to)
    sql = """
        SELECT p.sku, p.name,
               COALESCE(SUM(si.qty), 0) AS qty_sold,
               COALESCE(SUM(si.amount), 0) AS revenue,
               COALESCE(SUM(si.qty), 0) * p.purchase_price AS cost
        FROM sales_saleitem si
        JOIN sales_sale s ON s.id = si.sale_id
        JOIN masters_product p ON p.id = si.product_id
        WHERE s.sale_date >= %s AND s.sale_date <= %s
        GROUP BY p.id, p.sku, p.name, p.purchase_price
        ORDER BY p.name
    """
    rows = _fetch(sql, [start, end])
    out = []
    for r in rows:
        qty = Decimal(r["qty_sold"]).quantize(Decimal("0.01"))
        revenue = Decimal(r["revenue"]).quantize(Decimal("0.01"))
        cost = Decimal(r["cost"]).quantize(Decimal("0.01"))
        profit = revenue - cost
        margin = None if revenue == 0 else ((profit / revenue) * Decimal("100")).quantize(Decimal("0.01"))
        out.append(
            {
                "sku": r["sku"],
                "name": r["name"],
                "qty_sold": qty,
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "margin_pct": margin,
            }
        )
    return out


def dead_stock(days: int = 60) -> list[dict]:
    cutoff = timezone.now() - timedelta(days=days)
    sql = """
        SELECT p.sku, p.name, c.name AS category_name,
               COALESCE(SUM(m.qty_delta), 0) AS stock_qty
        FROM masters_product p
        JOIN masters_category c ON c.id = p.category_id
        LEFT JOIN inventory_stockmovement m ON m.product_id = p.id
        WHERE p.is_active = TRUE
          AND p.id NOT IN (
              SELECT DISTINCT product_id FROM inventory_stockmovement
              WHERE created_at >= %s
          )
        GROUP BY p.id, p.sku, p.name, c.name
        HAVING COALESCE(SUM(m.qty_delta), 0) > 0
        ORDER BY stock_qty DESC, p.name
    """
    return _fetch(sql, [cutoff])


def invoice_integrity_issues() -> list[dict]:
    sql = """
        SELECT s.id, s.invoice_no, s.sale_date, s.subtotal, s.discount, s.tax, s.total_amount,
               COALESCE(SUM(si.amount), 0) AS lines_sum,
               (s.subtotal - s.discount + s.tax) AS expected_total
        FROM sales_sale s
        LEFT JOIN sales_saleitem si ON si.sale_id = s.id
        GROUP BY s.id
        HAVING COALESCE(SUM(si.amount), 0) <> s.subtotal
            OR s.total_amount <> (s.subtotal - s.discount + s.tax)
        ORDER BY s.sale_date DESC, s.id DESC
    """
    return _fetch(sql)


# ---------------------------------------------------------------------------
# Set 2 — window functions
# ---------------------------------------------------------------------------
def running_total_window(year: int, month: int) -> list[dict]:
    date_from = date(year, month, 1)
    date_to = date(year, month, monthrange(year, month)[1])
    start, end = _aware_bounds(date_from, date_to)
    tz = timezone.get_current_timezone_name()
    sql = """
        WITH days AS (
            SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS day
        ),
        agg AS (
            SELECT (sale_date AT TIME ZONE %s)::date AS day,
                   COALESCE(SUM(total_amount), 0) AS day_total
            FROM sales_sale
            WHERE sale_date >= %s AND sale_date <= %s
            GROUP BY 1
        ),
        filled AS (
            SELECT d.day, COALESCE(a.day_total, 0) AS day_total
            FROM days d
            LEFT JOIN agg a ON a.day = d.day
        )
        SELECT day, day_total,
               SUM(day_total) OVER (ORDER BY day
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
        FROM filled
        ORDER BY day
    """
    rows = _fetch(sql, [date_from, date_to, tz, start, end])
    for r in rows:
        r["day_total"] = Decimal(r["day_total"]).quantize(Decimal("0.01"))
        r["running_total"] = Decimal(r["running_total"]).quantize(Decimal("0.01"))
    return rows


def product_rank_window(date_from: date, date_to: date) -> list[dict]:
    start, end = _aware_bounds(date_from, date_to)
    sql = """
        WITH rev AS (
            SELECT p.sku, p.name, c.name AS category,
                   COALESCE(SUM(si.amount), 0) AS revenue,
                   p.category_id
            FROM sales_saleitem si
            JOIN sales_sale s ON s.id = si.sale_id
            JOIN masters_product p ON p.id = si.product_id
            JOIN masters_category c ON c.id = p.category_id
            WHERE s.sale_date >= %s AND s.sale_date <= %s
            GROUP BY p.id, p.sku, p.name, c.name, p.category_id
        )
        SELECT sku, name, category, revenue,
               RANK() OVER (PARTITION BY category_id ORDER BY revenue DESC) AS rank
        FROM rev
        ORDER BY category, rank, sku
    """
    rows = _fetch(sql, [start, end])
    for r in rows:
        r["revenue"] = Decimal(r["revenue"]).quantize(Decimal("0.01"))
        r["rank"] = int(r["rank"])
    return rows


def mom_growth_window(months_back: int = 12) -> list[dict]:
    today = timezone.localdate()
    y, m = today.year, today.month
    for _ in range(months_back - 1):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    date_from = date(y, m, 1)
    start, end = _aware_bounds(date_from, today)
    tz = timezone.get_current_timezone_name()
    sql = """
        WITH monthly AS (
            SELECT date_trunc('month', sale_date AT TIME ZONE %s)::date AS month,
                   COALESCE(SUM(total_amount), 0) AS total
            FROM sales_sale
            WHERE sale_date >= %s AND sale_date <= %s
            GROUP BY 1
        ),
        lagged AS (
            SELECT month, total,
                   LAG(total) OVER (ORDER BY month) AS prev_total
            FROM monthly
        )
        SELECT month, total, prev_total,
               CASE
                   WHEN prev_total IS NULL OR prev_total = 0 THEN NULL
                   ELSE ROUND(((total - prev_total) / prev_total) * 100, 2)
               END AS growth_pct
        FROM lagged
        ORDER BY month
    """
    rows = _fetch(sql, [tz, start, end])
    for r in rows:
        r["total"] = Decimal(r["total"]).quantize(Decimal("0.01"))
        if r["prev_total"] is not None:
            r["prev_total"] = Decimal(r["prev_total"]).quantize(Decimal("0.01"))
        if r["growth_pct"] is not None:
            r["growth_pct"] = Decimal(r["growth_pct"]).quantize(Decimal("0.01"))
    return rows


def latest_invoice_window() -> list[dict]:
    sql = """
        WITH ranked AS (
            SELECT s.customer_id,
                   c.name AS customer__name,
                   c.phone AS customer__phone,
                   s.invoice_no, s.sale_date, s.total_amount, s.payment_status,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.customer_id
                       ORDER BY s.sale_date DESC, s.id DESC
                   ) AS rn
            FROM sales_sale s
            JOIN masters_customer c ON c.id = s.customer_id
            WHERE s.customer_id IS NOT NULL
        )
        SELECT customer_id, customer__name, customer__phone,
               invoice_no, sale_date, total_amount, payment_status
        FROM ranked
        WHERE rn = 1
        ORDER BY customer__name
    """
    rows = _fetch(sql)
    for r in rows:
        r["total_amount"] = Decimal(r["total_amount"]).quantize(Decimal("0.01"))
    return rows
