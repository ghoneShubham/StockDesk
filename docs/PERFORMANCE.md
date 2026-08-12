# Performance

Day 10 — Review 2 notes. Measured on the local PostgreSQL 16 database after
`seed_demo_data` (~500 products, ~3,000 sales / ~50k sale lines, matching
stock movements). `django-debug-toolbar` is enabled in `config.settings.dev`
(RedirectsPanel removed so form POSTs are not intercepted).

## Query budget (≤ 15 queries / page)

| Page | Pattern | Queries (view only) | Notes |
|---|---|---|---|
| Sales list | `select_related(customer, created_by)` + **Subquery** `line_count` | ≤ 15 (guarded by test) | Paginated 25 |
| Product list | `select_related(category)` + **Subquery** `stock_qty` | ≤ 15 (guarded by test) | Paginated 25 |
| Purchase list | same Subquery pattern as sales | ≤ 15 | Paginated 25 |
| Sale / purchase detail | `select_related` + `Prefetch(items→product)` | low single digits | Already clean |
| Stock history | `select_related(created_by)`, paginated 50 | low single digits | Running balance without loading full ledger |

Automated guards: `apps/core/tests_performance.py` (debug-toolbar middleware
disabled in those tests so counts reflect the view).

## N+1 / aggregate fixes

| Issue | Before | After |
|---|---|---|
| Product “In stock” | `Sum("stock_movements__qty_delta")` JOIN — pagination `COUNT(*)` paid the join too | Correlated **Subquery** via `apps.core.query.annotate_stock_qty` |
| Sales / purchases `line_count` | `Count("items")` JOIN against ~50k lines (~606 ms for page plan) | Correlated **Subquery** via `annotate_line_count` (~36 ms) |
| Create sale/purchase forms | Separate product queryset per form + second query for price map | Shared `products_qs` via `form_kwargs` + one price map |
| Stock history | Loaded entire ledger into Python | Paginated 50; balance from `current_stock` − sum of newer rows |
| Success messages | Extra `.items.count()` | Use `len(lines)` already in hand |

## Indexes added (Day 10 migrations)

| Model | Index fields | Why |
|---|---|---|
| `Sale` | `(-sale_date, -id)`, `(invoice_no)` | List order + invoice search |
| `Purchase` | `(-purchase_date, -id)`, `(supplier_invoice_no)` | List order + search |
| `StockMovement` | `(product, created_at, id)` | ASC/DESC history page (keeps prior DESC index too) |
| `Adjustment` | `(-created_at, -id)`, `(product, -created_at)` | Adjustment list |
| `Product` | `(is_active, name)`, `(sku)` | Filtered catalog order + SKU lookup |
| `Supplier` | `(is_active, name)` | Purchase header dropdown / search |
| `Customer` | `(name)` | Sales list customer search |

Migrations: `masters.0002_day10_perf_indexes`, `inventory.0002_day10_perf_indexes`,
`purchases.0002_day10_perf_indexes`, `sales.0003_day10_perf_indexes`.

## EXPLAIN ANALYZE — three hottest queries

Re-run anytime with:

```bash
python manage.py profile_hot_queries
```

### 1) Product stock annotate (valuation-shaped, all active products)

**Shape:** each product’s `stock_qty` via correlated Subquery over `inventory_stockmovement`.

| | |
|---|---|
| Execution Time | **205.6 ms** (cold-ish buffers; Index Cond `is_active`) |
| Plan highlights | `Index Scan` on `masters_pro_is_acti_e128bf_idx`; SubPlan uses `inventory_stockmovement_product_id_*` Bitmap Index Scan |

Why this is the valuation precursor: Day 11 stock valuation is the same
aggregate plus `qty × purchase_price`. Keeping it a Subquery avoids blowing
up the product-list `COUNT(*)` used for pagination.

### 2) Sales list + line counts (page of 25)

| Variant | Execution Time | Plan highlights |
|---|---|---|
| **Subquery `line_count` (shipped)** | **35.7 ms** | Index Scan on `sales_sale_sale_da_cfa272_idx` (`-sale_date, -id`); SubPlan Index Scan on `sales_saleitem_sale_id_*` per row on the page only |
| JOIN `Count("items")` baseline | **606.2 ms** | GroupAggregate over **50,008** sale-item rows before Limit |

**Decision:** ship the Subquery form. The JOIN form forces aggregating every
sale line to produce a 25-row page.

### 3) Stock history page (busiest product, 50 rows)

| | |
|---|---|
| Product | id `266`, **138** movements |
| Execution Time | **5.7 ms** |
| Plan highlights | Index Scan Backward on `inventory_s_product_e4cc72_idx` `(product, created_at, id)`; Memoize for `created_by` |

## How to verify with django-debug-toolbar

1. `DJANGO_DEBUG=True` and runserver with `config.settings.dev`
2. Log in, open Sales list / Products / a product’s Stock history
3. Toolbar SQL panel — target **≤ 15** queries for list pages
4. Confirm no repeated `masters_product` / `sales_saleitem` selects in a loop

## Still deferred (later days)

- Full report suite timings (&lt; 500 ms gate) — Days 11–12
- `pg_trgm` for `icontains` search if name search becomes hot
- Materialized stock snapshot table only if product-list Subquery exceeds budget at larger scale
