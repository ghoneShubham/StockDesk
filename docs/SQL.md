# SQL — Reports (ORM vs. Raw SQL)

## Day 11 status

Reports **Set 1** (items 1–9) are live in the app via Django ORM helpers in
`apps/reports/queries.py`, with date filters and CSV export on each screen.

| # | Report | ORM entry point | Access |
|---|---|---|---|
| 1 | Daily sales (incl. zero days) | `daily_sales_totals` | Operational |
| 2 | Top 10 by revenue / qty | `top_products` | Operational |
| 3 | Stock valuation | `stock_valuation` | Financial (Owner) |
| 4 | Low stock / reorder | `low_stock_products` | Operational |
| 5 | Inactive customers (90d) | `inactive_customers` | Operational |
| 6 | Supplier purchase totals | `supplier_purchase_totals` | Operational |
| 7 | Profit margin / product | `profit_margin_by_product` | Financial (Owner) |
| 8 | Dead stock (60d) | `dead_stock` | Operational |
| 9 | Invoice integrity audit | `invoice_integrity_issues` | Operational |

## Day 12 (next)

For each report above (and Set 2 window-function reports):

1. Capture ORM-generated SQL (`str(queryset.query)` / debug toolbar)
2. Hand-written raw SQL via `connection.cursor()`
3. Note which version would ship and why
