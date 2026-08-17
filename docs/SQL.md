# SQL — Reports (ORM vs. Raw SQL)

Day 12. Every PRD Section 8 report is implemented twice:

- **ORM** — `apps/reports/queries.py` (Set 1) and `apps/reports/queries_set2.py` (Set 2 subquery-first)
- **Raw SQL** — `apps/reports/sql_raw.py` via `connection.cursor()` with bound parameters

Set 2 UI screens ship the **window-function** raw SQL (or Django `Window` where it works cleanly). Subquery variants stay in code for comparison.

---

## How to re-check ORM SQL

```bash
python manage.py shell
>>> from django.db import connection
>>> from apps.reports import queries
>>> # run a report, then:
>>> print(connection.queries[-1]["sql"])  # with DEBUG=True
```

Or inspect `str(queryset.query)` on the underlying queryset before `.list()`.

---

## Set 1

### 1. Daily sales (incl. zero-sales days)

**ORM:** `TruncDate` + `Sum` / `Count`, then Python fills missing calendar days.

**Raw (ships for completeness / zero-fill in SQL):**

```sql
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
SELECT d.day, COALESCE(a.invoice_count, 0), COALESCE(a.total_sales, 0)
FROM days d LEFT JOIN agg a ON a.day = d.day
ORDER BY d.day;
```

**Ship:** ORM for the app screen (matches Day 11 UI); raw when you want zero-days entirely in Postgres (`generate_series`).

### 2. Top 10 products by revenue / quantity

**ORM:** `SaleItem.values(product).annotate(Sum).order_by(...)[:10]`

**Raw:**

```sql
SELECT p.sku, p.name,
       COALESCE(SUM(si.qty), 0) AS qty_sold,
       COALESCE(SUM(si.amount), 0) AS revenue
FROM sales_saleitem si
JOIN sales_sale s ON s.id = si.sale_id
JOIN masters_product p ON p.id = si.product_id
WHERE s.sale_date >= %s AND s.sale_date <= %s
GROUP BY p.id, p.sku, p.name
ORDER BY revenue DESC  -- or qty_sold DESC
LIMIT 10;
```

**Ship:** ORM — clear and fast enough with indexes on `sale_date` / `sale_id`.

### 3. Stock valuation

**ORM:** `annotate_stock_qty` Subquery × `purchase_price` in Python loop.

**Raw:**

```sql
SELECT p.sku, p.name, c.name,
       COALESCE(SUM(m.qty_delta), 0) AS stock_qty,
       p.purchase_price,
       COALESCE(SUM(m.qty_delta), 0) * p.purchase_price AS value
FROM masters_product p
JOIN masters_category c ON c.id = p.category_id
LEFT JOIN inventory_stockmovement m ON m.product_id = p.id
WHERE p.is_active
GROUP BY p.id, c.name
HAVING COALESCE(SUM(m.qty_delta), 0) > 0;
```

**Ship:** Raw for a one-shot valuation export (single round-trip); ORM Subquery when composing with other Product filters.

### 4. Low stock

Same stock aggregate as valuation with `HAVING stock_qty <= reorder_level`.

**Ship:** ORM (`annotate_stock_qty` + `F` compare) — reuses Day 10 helper.

### 5. Inactive customers (90d)

**ORM:** `Subquery` last sale date + `Q(isnull|lt cutoff)`.

**Raw:** `NOT EXISTS (sale in last 90 days)` + scalar `MAX(sale_date)`.

**Ship:** ORM — readable permission-layer code; raw `NOT EXISTS` is slightly clearer to the planner.

### 6. Supplier purchase totals

**ORM:** `Purchase.values(supplier).annotate(Sum, Count(distinct products))`.

**Raw:** join purchase + items, `COUNT(DISTINCT product_id)`.

**Ship:** ORM.

### 7. Profit margin

**ORM / Raw:** revenue − qty×purchase_price; margin `%` null when revenue = 0.

**Ship:** ORM (business rules in Python are explicit); raw mirrors it for SQL.md parity.

### 8. Dead stock (60d)

**ORM:** stock > 0 and product id not in recent movements.

**Raw:** same with `NOT IN (SELECT DISTINCT product_id … WHERE created_at >= %s)`.

**Ship:** ORM.

### 9. Invoice integrity

**ORM:** `Sum(items__amount)` vs `subtotal`; `total` vs `subtotal - discount + tax`.

**Raw:** `GROUP BY sale HAVING …`.

**Ship:** Raw for a nightly audit job; ORM for the interactive report (already wired).

---

## Set 2 (window functions)

PRD: attempt subqueries first, then rewrite with windows.

| # | Technique | Subquery helper | Window helper (UI) |
|---|---|---|---|
| 10 | `SUM() OVER` | `running_total_subquery` | `running_total_window` → raw |
| 11 | `RANK() OVER (PARTITION BY …)` | `product_rank_subquery` | `product_rank_window` → raw |
| 12 | `LAG()` | `mom_growth_subquery` | `mom_growth_window` → raw |
| 13 | `ROW_NUMBER()` | `latest_invoice_subquery` | `latest_invoice_window` → Django `Window` |

### 10. Running total (month)

**Subquery approach:** daily aggregate, then cumulative sum in Python (same math as correlated `SUM … WHERE day <= d`).

**Window (shipped):**

```sql
WITH days AS (SELECT generate_series(... )::date AS day),
agg AS (... GROUP BY day),
filled AS (SELECT d.day, COALESCE(a.day_total,0) FROM days d LEFT JOIN agg a ...)
SELECT day, day_total,
       SUM(day_total) OVER (ORDER BY day
         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
FROM filled
ORDER BY day;
```

**Ship:** **Raw window** — one query, zero-fill + running total in Postgres.

### 11. Product rank within category

**Subquery:** rank = 1 + count of peers with higher revenue (Python over aggregated rows).

**Window (shipped):**

```sql
WITH rev AS (
  SELECT p.sku, p.name, c.name AS category, p.category_id,
         COALESCE(SUM(si.amount),0) AS revenue
  FROM sales_saleitem si
  JOIN sales_sale s ON s.id = si.sale_id
  JOIN masters_product p ON p.id = si.product_id
  JOIN masters_category c ON c.id = p.category_id
  WHERE s.sale_date BETWEEN %s AND %s
  GROUP BY p.id, c.name, p.category_id
)
SELECT *, RANK() OVER (PARTITION BY category_id ORDER BY revenue DESC) AS rank
FROM rev
ORDER BY category, rank;
```

**Ship:** **Raw window** — Django cannot cleanly `Window(Rank)` after `values().annotate(Sum)`.

### 12. Month-on-month growth %

**Subquery / lag-in-Python:** `TruncMonth` aggregate then previous row.

**Window (shipped):**

```sql
WITH monthly AS (
  SELECT date_trunc('month', sale_date AT TIME ZONE %s)::date AS month,
         COALESCE(SUM(total_amount),0) AS total
  FROM sales_sale
  WHERE sale_date BETWEEN %s AND %s
  GROUP BY 1
),
lagged AS (
  SELECT month, total, LAG(total) OVER (ORDER BY month) AS prev_total
  FROM monthly
)
SELECT month, total, prev_total,
       CASE WHEN prev_total IS NULL OR prev_total = 0 THEN NULL
            ELSE ROUND(((total - prev_total) / prev_total) * 100, 2)
       END AS growth_pct
FROM lagged
ORDER BY month;
```

**Ship:** **Raw window** (`LAG`) — divide-by-zero handled in SQL.

### 13. Latest invoice per customer

**Subquery (ORM):** correlated `Subquery` of latest `id` per `customer_id`, filter `id = latest`.

**Window (shipped in UI via Django `Window(RowNumber)`):**

```sql
WITH ranked AS (
  SELECT s.*, c.name, c.phone,
         ROW_NUMBER() OVER (
           PARTITION BY s.customer_id
           ORDER BY s.sale_date DESC, s.id DESC
         ) AS rn
  FROM sales_sale s
  JOIN masters_customer c ON c.id = s.customer_id
  WHERE s.customer_id IS NOT NULL
)
SELECT * FROM ranked WHERE rn = 1
ORDER BY name;
```

**Ship:** **Django `Window(RowNumber)`** for the screen (one ORM query); raw CTE is equivalent and good for ad-hoc SQL.

---

## Summary — what we'd ship

| Report | Prefer |
|---|---|
| 1 Daily sales | ORM (+ Python zero-fill) or raw `generate_series` |
| 2 Top products | ORM |
| 3 Valuation | Raw for bulk export; ORM Subquery in-app |
| 4–8 | ORM |
| 9 Integrity | Raw for scheduled audit |
| 10–12 | **Raw SQL windows** |
| 13 Latest invoice | **ORM Window** (or raw CTE) |

All raw paths use `%s` placeholders — never concatenate request parameters into SQL (SQL-injection audit item).
