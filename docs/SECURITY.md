# Security Self-Audit (PRD §10) — Day 15

Documented against the StockDesk codebase and local/manual checks before final demo.
For each test: what was tried, what happened, what changed.

---

## 1. IDOR (Insecure Direct Object Reference)

**Tried:** Log in as Cashier. Open a sale detail URL the cashier can see (`/sales/<id>/`). Change the ID to another sale. Attempt Owner-only URLs: financial reports (`/reports/stock-valuation/`), payment reconcile (`/payments/reconcile/`), product edit, purchase create.

**What happened:**
- Sales/invoices the cashier has `view_sale` for are readable by ID (all staff can view sales by design — not customer-scoped multi-tenant).
- Financial reports and payment reconcile return **HTTP 403** for Cashier/Manager (PermissionRequiredMixin).
- Purchase create / product edit return **403** for Cashier.
- PDF download requires `sales.view_sale` — anonymous users redirected to login.

**Changed:** No IDOR bug found for role boundaries. Multi-tenant “own records only” is out of scope (single-business app). Keep enforcing permissions on every view (never hide-only in templates).

---

## 2. XSS (Cross-Site Scripting)

**Tried:** Create/update a product name and customer address with  
`<script>alert(1)</script>` and `"><img src=x onerror=alert(1)>`.

**What happened:**
- Django templates auto-escape variables → script shown as text on list/detail pages, not executed.
- Invoice PDF path uses escaped/template context; dangerous markup does not run as HTML/JS in the browser PDF download flow.

**Changed:** None required. Do not mark user content `|safe` unless intentionally sanitized.

---

## 3. SQL injection (raw report SQL)

**Tried:** On report date filters and search-like params, attempt `' OR 1=1--` and similar breakouts. Inspect `apps/reports/sql_raw.py`.

**What happened:**
- Raw SQL uses parameterized queries (`cursor.execute(sql, params)`), not string concatenation of user input.
- ORM reports use Django lookups.

**Changed:** None required. Rule: never f-string user input into SQL.

---

## 4. Rate limiting (login)

**Tried initially:** Count unlimited POSTs to `/accounts/login/` with wrong passwords.

**What happened (before fix):** Django’s default `LoginView` had **no** attempt limit (effectively unlimited per IP).

**Changed (Day 15):** `apps.accounts.views.RateLimitedLoginView` — **10 failed attempts per IP per 60 seconds** (cache-backed). Further POSTs show an error and do not authenticate. Successful login clears the counter.

---

## 5. Secrets in history

**Tried:** `git log -p | findstr /i "secret password AKIA rzp_"` (and equivalent greps) on the repo.

**What happened:** `.env` is gitignored from early commits. Example files use placeholders only (`deploy/env.production.example`, `.env.example`). No live AWS/Razorpay secrets found in tracked history during this audit.

**Changed:** Process reminder — never commit `.env`; rotate immediately if a key leaks (including pasting credentials into chat).

---

## 6. CSRF

**Tried:** Remove CSRF token from a POST form (sale/purchase/login) via browser tools and resubmit.

**What happened:** Django middleware rejects with **403 CSRF verification failed**.

**Changed:** None. Webhook endpoint is intentionally `@csrf_exempt` but requires **Razorpay HMAC signature** on the raw body instead.

---

## 7. File upload

**Tried:** Upload `.php`, `.html`, and oversized/non-image files as product image.

**What happened:**
- `Product` form validates extension + content type (`jpeg/png/webp/gif`) and size (≤ 2MB) in `apps/masters/forms.py`.
- Non-image uploads are rejected with validation errors.
- Stored under `products/{sku}/…` via default storage (local or S3).

**Changed:** None beyond existing validation. Keep rejecting executable/HTML types.

---

## Summary

| Test | Result | Fix applied |
|---|---|---|
| IDOR / roles | 403 on unauthorized | Already enforced |
| XSS | Escaped | None |
| SQLi | Parameterized | None |
| Login rate limit | Was unlimited | **Added 10/min/IP** |
| Secrets in git | Clean in audit | Process only |
| CSRF | 403 | None (webhook = signature) |
| File upload | Rejected bad types | Existing validators |

**Demo note:** Re-run `bootstrap_roles` after pull so Cashier/Manager receive `add_paymentlink` for “Send payment link”.
