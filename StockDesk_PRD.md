# Product Requirements Document (PRD)
## StockDesk — Inventory & Billing System

| | |
|---|---|
| **Document version** | 1.0 |
| **Owner / Developer** | Shubham |
| **Reviewer** | Ram (peer PR reviewer) |
| **Duration** | 15 working days (3 weeks) |
| **Stack** | Python 3.12 · Django 5.x · PostgreSQL 16 · AWS (EC2, S3, SES) |
| **Status** | Approved for build |

---

## 1. Overview

### 1.1 Problem statement
A small retail/distribution business currently has no reliable way to track incoming stock (from suppliers), outgoing stock (to customers), payments collected, and profit made. The owner needs real-time, trustworthy visibility into inventory and finances.

### 1.2 Product summary
StockDesk is a web-based inventory and billing system that lets a business:
- Record purchases from suppliers (stock in)
- Bill customers (stock out) and generate invoices
- Track and explain every stock movement
- Collect online payments and reconcile them
- Generate operational and financial reports
- Operate reliably under concurrent, multi-user, real-world usage (50,000+ rows)

### 1.3 What this is *not*
- Not a UI/frontend showcase — Django templates + Bootstrap only, no SPA framework.
- Not a prototype — must behave correctly under concurrency, scale, and failure conditions, and must be operable by someone other than the original developer.

### 1.4 Success definition
A business owner can log in on a phone, see today's sales, check low stock, and print an invoice — on a system with 50,000 line items behind it — where every stock number is traceable to the document that changed it, the last unit can never be sold twice, and the whole system can be restored from backup if the server dies. A person who has never seen the code can deploy and operate it using only the runbook.

---

## 2. Goals & Non-Goals

### 2.1 Goals
- Correct, auditable inventory tracking at all times
- Safe concurrent billing (no overselling, no duplicate invoice numbers)
- Role-based access control enforced server-side, not just in the UI
- Production-grade deployment on AWS within a tight budget ($6–9 total spend)
- Demonstrated understanding of SQL, ORM internals, and query performance
- A basic online payment collection + reconciliation workflow
- Documentation good enough that someone else can operate the system

### 2.2 Non-goals
- No React/DRF/SPA frontend
- No RDS, load balancer, or NAT Gateway (cost control)
- No live payment processing (test mode only)
- No multi-tenant / multi-store support
- No mobile native app

---

## 3. Users & Roles

| Capability | Owner | Store Manager | Cashier |
|---|---|---|---|
| View masters (products, suppliers, customers) | ✅ | ✅ | ✅ (no purchase price) |
| Add/edit masters | ✅ | ✅ | ❌ |
| Edit selling price | ✅ | ❌ | ❌ |
| Purchases | ✅ | ✅ | ❌ |
| Sales / billing | ✅ | ✅ | ✅ |
| Stock adjustments | ✅ | ✅ | ❌ |
| Financial reports (margin, valuation, P&L) | ✅ | ❌ | ❌ |
| Operational reports (stock, low stock) | ✅ | ✅ | ❌ |
| User management | ✅ | ❌ | ❌ |

**Enforcement principle:** Permissions must be enforced at the view layer and the query layer — never by hiding UI elements alone. Assume every user will attempt to access data they shouldn't (e.g., by editing a URL or reading page source). Use Django Groups + `PermissionRequiredMixin` / `UserPassesTestMixin`. Do not build a custom permission system.

---

## 4. Technical Requirements

### 4.1 Fixed stack
- **Language/Framework:** Python 3.12, Django 5.x
- **Database:** PostgreSQL 16 (never SQLite — hides concurrency bugs)
- **Config:** python-decouple (`.env`-based settings)
- **DB driver:** psycopg[binary]
- **Dev tools:** django-debug-toolbar (dev only), Faker (data seeding)
- **PDF generation:** WeasyPrint or xhtml2pdf (invoices)
- **File storage:** django-storages + boto3 (S3)
- **Serving:** gunicorn + nginx + systemd
- **Testing:** pytest-django
- **Frontend:** Django templates + Bootstrap 5 only

### 4.2 Non-negotiable engineering rules
1. PostgreSQL only, in every environment.
2. All monetary fields: `DecimalField(max_digits=12, decimal_places=2)` — never `FloatField`.
3. `DEBUG = False` in production from the first deploy, not just before final demo.
4. No secrets committed to git, ever. `.env` in `.gitignore` from commit #1. If a key leaks, rotate it immediately and report it same-day.
5. Every stock number must be explainable — reconstructable from history, down to the exact transaction, timestamp, and user.
6. No direct pushes to `main`. All changes via pull request, even solo (PRs are peer-reviewed by Ram, and vice versa).

### 4.3 Project structure
```
stockdesk/
├── config/
│   ├── settings/{base.py, dev.py, prod.py}
│   ├── urls.py, wsgi.py
├── apps/
│   ├── core/        # middleware, mixins, audit, utils, health check
│   ├── accounts/    # login/logout, groups, permission mixins
│   ├── masters/     # Category, Product, Supplier, Customer
│   ├── inventory/   # StockMovement, Adjustment, reconcile command
│   ├── purchases/   # Purchase, PurchaseItem
│   ├── sales/       # Sale, SaleItem, invoice + PDF
│   ├── payments/    # PaymentLink, PaymentEvent
│   └── reports/     # all reports, CSV export
├── templates/
├── static/
├── requirements/{base.txt, dev.txt, prod.txt}
└── docs/            # PERFORMANCE.md, RUNBOOK.md, SQL.md, SECURITY.md
```

---

## 5. Data Model

| Model | Key Fields |
|---|---|
| **User** | Django auth; Groups = Owner / Store Manager / Cashier |
| **Category** | name, is_active |
| **Product** | sku (unique), name, category (FK), unit, hsn_code, purchase_price (Decimal), sale_price (Decimal), reorder_level (int), image_key, sellable (bool), is_active, created_at, updated_at |
| **Supplier** | name, phone, gstin, address, is_active |
| **Customer** | name, phone (unique), address, created_at |
| **Purchase** | supplier (FK), supplier_invoice_no, purchase_date, total_amount, created_by (FK), created_at |
| **PurchaseItem** | purchase (FK), product (FK), qty, rate, amount |
| **Sale** | invoice_no (unique), customer (FK, nullable), sale_date, subtotal, discount, tax, total_amount, payment_status (pending/paid/partial), created_by (FK), created_at |
| **SaleItem** | sale (FK), product (FK), qty, rate, discount, amount |
| **StockMovement** | product (FK), movement_type, qty_delta (+/-), reference_type, reference_id, reason, created_by (FK), created_at |
| **Adjustment** | product (FK), qty_delta, reason (required, choice field + notes), created_by |
| **AuditLog** | user (FK), action, model_name, object_id, changes (JSONField), created_at |

### 5.1 Critical data-integrity requirements

**R1 — Stock must be explainable**
At any moment, for any product, the system must answer: *"Stock shows 37. Yesterday it showed 40. What happened?"* — with an exact, timestamped list of changes, the source document, and the responsible user. A crashed/partial request must never leave stock silently wrong.
- **Design approach:** Every stock-affecting action (sale, purchase, adjustment) writes a `StockMovement` row inside the same DB transaction as the business record. Current stock = sum of movements for that product.
- **Deliverable:** A management command that verifies reported stock against movement history and reports any drift.

**R2 — Correctness under concurrency**
Two cashiers billing the last unit of a product at the same time must not both succeed. Stock must never go negative; the losing transaction must fail cleanly with a readable error.
- **Design approach:** Use row-level locking (`select_for_update()`) within `transaction.atomic()` blocks when decrementing stock.
- **Deliverable:** A script that fires two concurrent sales against the last unit and captures the output (one success, one clean failure).

**R3 — Invoice numbers**
Must be sequential, gap-free within a financial year, and impossible to duplicate under concurrent billing. `max(id) + 1` in Python is explicitly disallowed (race condition risk).
- **Design approach:** Use a database sequence or a locked counter row to atomically generate the next invoice number.

---

## 6. Functional Requirements (Modules)

### Module A — Masters
- CRUD for Category, Product, Supplier, Customer
- Django forms with server-side validation
- Product image upload (stored in S3)
- Django admin properly configured: `list_display`, `search_fields`, `list_filter`, read-only audit fields (owner will use admin for one-off fixes)

### Module B — Purchases
- Multi-line purchase entry via Django formsets
- One supplier, many products, quantity + rate per line, computed total
- Stock increases; `StockMovement` rows written

### Module C — Sales / Billing (primary screen)
- Optional customer (supports walk-ins)
- Multiple line items, per-line discount, tax, computed total
- Stock decreases; `StockMovement` rows written; concurrency-safe (see R2)
- Optimized for speed/keyboard flow — used ~100x/day
- Invoice detail page + printable PDF

### Module D — Adjustments
- For damage, theft, correction, opening stock
- Reason: mandatory choice field + optional free-text notes

### Module E — Reports
See Section 8. All reports support date filters and CSV export.

### Module F — Payment Collection
See Section 9.

### Module G — Dashboard
- Today's sales
- This month's sales
- Low stock count
- Pending payment total
- Top 5 products this month

---

## 7. Non-Functional Requirements

### 7.1 Scale & seed data
Before any performance/report work begins (Day 5), seed a realistic dataset via a `seed_demo_data` management command (Faker):
- 30 suppliers · 500 products · 200 customers
- 800 purchases (~4,000 purchase lines)
- 3,000 sales (~50,000 sale lines) spread across 18 months
- Matching stock movement history for all of the above

All work from Day 6 onward must be tested against this dataset, not hand-typed rows.

### 7.2 Performance gates (graded requirements)

| Gate | Target |
|---|---|
| Queries per page (via django-debug-toolbar) | ≤ 15 |
| Any report response time on seeded data | < 500 ms |
| Sales list page | Paginated, ≤ 15 queries |

- Fix N+1 query problems using `select_related()` / `prefetch_related()`.
- Run `EXPLAIN ANALYZE` on the three slowest report queries; add indexes; record before/after timings and query plans in `docs/PERFORMANCE.md`.

### 7.3 Security requirements
Server-side authorization enforcement everywhere permissions apply (see Section 3). A self-audit (Section 10) must be completed and documented before final demo.

### 7.4 Reliability & operations
- Staging environment (separate port + database) — nothing reaches production without passing through staging first
- Structured logging to file, with a request ID per line, and log rotation
- **Outbox pattern for emails:** if SES fails, the email intent is written to a DB table within the same transaction as the business record, and drained by a retrying worker — no request should be blocked or lose an email
- Backups: nightly `pg_dump` → S3, old backups cleaned up, and **restore must be tested live** (wipe DB, restore from S3, demonstrate it works)
- `docs/RUNBOOK.md`: deploy, restart, read logs, restore DB, diagnose slow reports — written so someone unfamiliar with the code could execute it, and it will be tested that way

---

## 8. Reports & SQL Requirements

Every report must be implemented **twice**: once via Django ORM, once via raw SQL (`connection.cursor()`). Compare the ORM-generated SQL (`str(queryset.query)` or debug toolbar) against the hand-written version. Record both in `docs/SQL.md` with a note on which you'd ship and why.

### Set 1 (foundational)
1. Daily sales totals for a date range, including zero-sales days
2. Top 10 products by revenue, and separately by quantity, for a period
3. Current stock valuation (qty × purchase price, total)
4. Products at or below reorder level
5. Customers with no purchase in the last 90 days
6. Supplier-wise purchase totals with distinct product count
7. Profit margin per product (handle divide-by-zero)
8. Dead stock — in inventory, zero movement in 60 days
9. **Data integrity audit** — invoices where line items don't sum to header total (not optional)

### Set 2 (window functions — attempt with subqueries first, then rewrite)
10. Running total of sales across a month, day by day
11. Rank of each product by revenue within its category
12. Month-on-month growth percentage
13. Each customer's most recent invoice, in one query

Techniques: `SUM() OVER`, `RANK() OVER (PARTITION BY ...)`, `LAG()`, `ROW_NUMBER()`.

---

## 9. Payment Collection (Module F) — Detailed Spec

- A sale can be created with `payment_status = pending`.
- From the invoice screen, "Send payment link" calls the **Razorpay Payment Links API (test mode only — live keys forbidden)** and stores the link against the invoice.
- Razorpay sends a **webhook** to `/webhooks/razorpay/` when the customer pays.
- The webhook handler must:
  - Verify the signature against the **raw request body**
  - Record the event
  - Mark the invoice paid
  - **Be idempotent** — Razorpay may send the same webhook twice; processing it twice must not double-record payment
- The webhook is the **source of truth** — not any browser redirect. If the customer closes the tab before returning to the app, the invoice must still get marked paid via the webhook.
- The webhook endpoint is public/unauthenticated — treat every incoming request as hostile until the signature verifies.
- **Reconciliation report:** lists every disagreement between what the gateway says was paid and what the invoices say. This is the actual point of the module — anyone can mark an invoice paid; knowing when your books disagree with the gateway is the skill being tested.

**Priority note:** This module is the first to be cut if the schedule slips. Sections 6–8 (core data model, correctness, scale/performance) are weighted more heavily.

---

## 10. Security Self-Audit Requirements

To be completed and documented in `docs/SECURITY.md` before the final demo:

| Test | What to do |
|---|---|
| **IDOR** | Log in as a cashier, change the invoice ID / product edit URL / report URL / PDF URL to one you don't own. Expect to find something. |
| **XSS** | Insert `<script>alert(1)</script>` into a product name and customer address; check every page (including PDF) that renders it. |
| **SQL injection** | Attempt to break out of raw SQL report queries via a date/search query parameter; fix with parameterized queries; confirm the fix. |
| **Rate limiting** | Determine how many login attempts per minute are currently allowed. |
| **Secrets in history** | `git log -p \| grep -i secret` — check for leaked keys/passwords. |
| **CSRF** | Remove the CSRF token from a form via devtools; confirm Django blocks the submission. |
| **File upload** | Try uploading a `.php` or `.html` file as a product image; observe what happens to it. |

For each test: document what was tried, what happened, and what was changed as a result.

---

## 11. Testing Requirements

Minimum **15 meaningful tests** (pytest-django), including at least:

1. Stock cannot go negative
2. Reported stock matches system history after a mixed sequence of transactions
3. A failed sale leaves no partial data
4. Concurrent sales for the last unit — one succeeds, one fails cleanly
5. Invoice line items sum to the header total
6. Invoice numbers are unique under concurrent creation
7. Cashier cannot open a margin report
8. Cashier cannot see purchase price in product list or HTML source
9. Manager cannot edit selling price
10. A user cannot view a record by guessing its ID if unauthorized
11. Discount cannot exceed line amount
12. Negative or zero quantity is rejected
13. Money arithmetic is exact to two decimals
14. Report totals match the sum of underlying rows
15. Deleting a product with movement history is prevented or soft-deleted

---

## 12. Infrastructure & Deployment (AWS)

### 12.1 Setup
- **Region:** `ap-south-1` only (Mumbai) — resources elsewhere are invisible and still bill
- **Compute:** EC2 `t3.micro`, Ubuntu 24.04, 20 GB gp3 + 2 GB swap (1 GB RAM won't survive a migration on 50k rows with Postgres + gunicorn running)
- **Database:** PostgreSQL 16 on the same instance — no RDS
- **Web server:** nginx → gunicorn over a unix socket, managed by systemd, enabled on boot
- **File storage:** S3 for product images + invoice PDFs (django-storages); IAM user scoped to one bucket only (not `AmazonS3FullAccess`)
- **Email:** SES (sandbox mode is fine — only sends to verified addresses)
- **HTTPS:** certbot on assigned subdomain
- **Health check:** `/health/` endpoint (app + DB status), monitored externally every 5 minutes

### 12.2 Cost controls
- Budget alerts at $5 and $10, set up **before** launching anything
- No RDS, no NAT Gateway, no load balancer — these are the account-killers
- Root account MFA on; all daily work via an IAM user, never root credentials
- Auto-stop schedule (EventBridge Scheduler → Lambda → `ec2:StopInstances`, IAM scoped to one instance ARN). Note: stopping releases the public IP — this must be handled, not ignored.
- **Target total spend:** $6–9 across three weeks. Cross $15 → stop and investigate.

### 12.3 Scheduled jobs (systemd timers / cron)
- Daily low-stock alert email
- Weekly dead-stock report
- Nightly `pg_dump` → S3, with old backup cleanup
- Stock reconciliation check, emailing on drift

---

## 13. Milestones & Timeline

### Week 1 — Model it properly
| Day | Work |
|---|---|
| 1 | Repo, virtualenv, settings split, `.env`, local Postgres, logging config, `.gitignore`, first PR |
| 2 | Models + migrations, DB-level constraints, admin registration |
| 3 | Auth, Groups, permission mixins, protected views, login/logout |
| 4 | Masters CRUD, forms, validation, messages framework, image upload |
| 5 | `seed_demo_data` with Faker — **Review 1** |

### Week 2 — Transactions, then speed
| Day | Work |
|---|---|
| 6 | Purchase entry (formsets), stock-in, atomic transactions |
| 7 | Sales/billing screen, stock-out, concurrency handling, invoice numbering, concurrency proof script |
| 8 | Invoice detail + PDF + S3 storage. (A requirement change is expected to land this day) |
| 9 | Adjustments, per-product stock history view, reconciliation command |
| 10 | Debug toolbar, N+1 hunt, indexes, `EXPLAIN ANALYZE`, `PERFORMANCE.md` — **Review 2** |

### Week 3 — Reports, deploy, operate
| Day | Work |
|---|---|
| 11 | Reports Set 1, date filters, CSV export, dashboard |
| 12 | Reports Set 2 + window functions, `SQL.md` |
| 13 | AWS: EC2, Postgres, gunicorn, nginx, systemd, `DEBUG=False`, static files, domain, HTTPS |
| 14 | S3, SES, outbox, scheduled jobs, backups + restore drill, staging |
| 15 | Module F (if on schedule), security audit, tests, docs, **final demo — Review 3** |

> Reviews on Days 5, 10, and 15 are checkpoints requiring you to defend design decisions — not status updates.

---

## 14. Deliverables Checklist

- [ ] Live HTTPS URL with seeded data and three logins (one per role)
- [ ] GitHub repo — PR-based history, README with local setup instructions, `.env.example`, pinned requirements, no secrets in history
- [ ] `docs/PERFORMANCE.md` — before/after query counts and timings, `EXPLAIN ANALYZE` plans, indexes added and why
- [ ] `docs/SQL.md` — all 13 reports, ORM vs. raw SQL, subquery vs. window-function versions
- [ ] `docs/SECURITY.md` — self-audit results, findings, fixes
- [ ] `docs/RUNBOOK.md` — operations guide, tested by someone else
- [ ] Concurrency proof — script + output
- [ ] Backup restore evidence — terminal log or recording of a real restore
- [ ] 15+ passing tests
- [ ] Cost report — actual spend + one paragraph on how to halve it
- [ ] `commands.md` — every Linux/Postgres/git command looked up during the project

---

## 15. Definition of Done

A business owner opens a link on his phone, logs in, sees today's sales, checks what's running low, and prints an invoice — on a system with 50,000 line items behind it, where every stock number can be traced back to the document that changed it, where the last unit cannot be sold twice, and where the whole system can be restored from a backup if the server dies.

Then, someone who has never seen the code deploys it using only the runbook.

---

## 16. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Concurrency bugs in stock/invoice numbering | Use `select_for_update()` + `transaction.atomic()`; prove correctness with a dedicated concurrency test script (Day 7) |
| N+1 queries tanking performance at scale | Seed realistic data early (Day 5); use debug toolbar continuously, not just at Day 10 |
| AWS cost overrun | Budget alerts set on Day 1; avoid RDS/NAT Gateway/load balancer entirely; auto-stop schedule |
| Running out of time for Module F (payments) | Explicitly deprioritized — cut first if behind schedule |
| Untested backups turning out to be broken when needed | Restore drill is a required, verified deliverable, not assumed to work |
| Permission bugs (cashier seeing restricted data) | Enforce at view + query layer; explicit tests for this (tests #7, #8, #9, #10) |
| Requirement changes mid-project | Anticipated on Day 8 by design — build with some flexibility in the sales/invoice module |

---

## 17. Support Process

One hour of independent troubleshooting on a blocker before escalating. When escalating, provide:
1. What you're trying to do
2. What you tried
3. What happened
4. What you think is going on

This format is the expected professional standard for the rest of your career — and writing it out often surfaces the fix before you even send it.
