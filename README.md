# StockDesk — Inventory & Billing System

A web-based inventory and billing system for a small retail/distribution business:
purchases, sales/billing with PDF invoices, stock movement tracking, adjustments,
reports, and (optionally) online payment collection via Razorpay.

Built with Python 3.12, Django 5.x, PostgreSQL 16, and deployed on a single AWS
EC2 instance. See [`StockDesk_PRD.md`](./StockDesk_PRD.md) for the full product
requirements document and [`docs/`](./docs) for engineering documentation.

## Stack

- Python 3.12, Django 5.1
- PostgreSQL 16 (required in every environment — never SQLite)
- Django templates + Bootstrap 5 (no SPA framework)
- WeasyPrint for invoice PDFs
- django-storages + boto3 for S3 (product images, invoice PDFs) in production
- gunicorn + nginx + systemd in production

## Local setup

### 1. Prerequisites

- Python 3.12
- PostgreSQL 16, running locally
- git

### 2. Clone and create a virtual environment

```bash
git clone <repo-url> stockdesk
cd stockdesk
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements/dev.txt
```

### 4. Create the database

```sql
CREATE USER stockdesk WITH PASSWORD 'stockdesk_dev_pw';
CREATE DATABASE stockdesk_dev OWNER stockdesk;
-- Needed so `pytest` can create/drop its own test database:
ALTER USER stockdesk CREATEDB;
```

### 5. Configure environment variables

```bash
cp .env.example .env
# edit .env — at minimum set DJANGO_SECRET_KEY and the DB_* values
```

### 6. Migrate and create an admin user

```bash
python manage.py migrate
python manage.py bootstrap_roles      # creates Owner / Store Manager / Cashier groups
python manage.py createsuperuser
```

### 7. (Optional) Seed realistic demo data

```bash
python manage.py seed_demo_data
```

This creates ~30 suppliers, 500 products, 200 customers, 800 purchases, and
3,000 sales (~50,000 sale lines) spread across 18 months — the dataset all
performance and report work is tested against (see Section 7.1 of the PRD).

### 8. Run the dev server

```bash
python manage.py runserver
```

Visit http://127.0.0.1:8000/ and log in. Visit `/health/` to confirm the app
and database are both reachable.

## Running tests

```bash
pytest
```

## Project structure

```
stockdesk/
├── config/            # settings (base/dev/prod), urls, wsgi/asgi
├── apps/
│   ├── core/          # middleware, mixins, audit log, health check, dashboard
│   ├── accounts/      # login/logout, role bootstrap command
│   ├── masters/       # Category, Product, Supplier, Customer
│   ├── inventory/     # StockMovement, Adjustment, reconciliation command
│   ├── purchases/     # Purchase, PurchaseItem
│   ├── sales/         # Sale, SaleItem, invoice + PDF
│   ├── payments/      # PaymentLink, PaymentEvent, Razorpay webhook
│   └── reports/       # all reports (ORM + raw SQL), CSV export
├── templates/
├── static/
├── requirements/      # base.txt, dev.txt, prod.txt
└── docs/              # PERFORMANCE.md, RUNBOOK.md, SQL.md, SECURITY.md
```

## Documentation

- [`docs/RUNBOOK.md`](./docs/RUNBOOK.md) — deploy, restart, logs, restore, diagnose
- [`docs/PERFORMANCE.md`](./docs/PERFORMANCE.md) — query counts, timings, indexes
- [`docs/SQL.md`](./docs/SQL.md) — every report, ORM vs raw SQL
- [`docs/SECURITY.md`](./docs/SECURITY.md) — self-audit results
- [`commands.md`](./commands.md) — every Linux/Postgres/git command looked up

## Contributing / workflow

No direct pushes to `main`. All changes go through a pull request, reviewed
before merge — see [`StockDesk_PRD.md`](./StockDesk_PRD.md) Section 4.2.
