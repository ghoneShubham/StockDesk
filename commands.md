# Commands Log

Every non-obvious Linux / PostgreSQL / git / Windows command looked up while
building StockDesk, with a one-line note on why. Appended to throughout the
project (Section 14 deliverable).

## Day 1 — Environment setup

| Command | Why |
|---|---|
| `winget search PostgreSQL.PostgreSQL --source winget --accept-source-agreements` | List exact installable PostgreSQL versions via winget (needed the `--accept-source-agreements` flag to avoid an interactive msstore prompt hanging the shell) |
| `winget install --id PostgreSQL.PostgreSQL.16 -e --accept-source-agreements --accept-package-agreements` | Unattended install of PostgreSQL 16 on the dev machine |
| `psql -U postgres -h localhost -c "CREATE USER stockdesk WITH PASSWORD '...';"` | Create the app's own least-privilege DB role instead of using the postgres superuser |
| `ALTER SCHEMA public OWNER TO stockdesk;` | On PostgreSQL 15+, the `public` schema is no longer owned by every DB owner by default — needed to explicitly grant/own it so migrations can create tables |
| `django-admin startapp <name> apps/<name>` | Scaffold an app into a subdirectory (`apps/`) instead of the project root; must run via `django-admin` directly (not `manage.py`) before the app is registered, since `manage.py` calls `django.setup()` and fails if `INSTALLED_APPS` references a module that doesn't exist yet |
| `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` | Generate a proper random `SECRET_KEY` for `.env` instead of using the placeholder from `startproject` |

## Day 3 — Auth & roles

| Command | Why |
|---|---|
| `ALTER USER stockdesk CREATEDB;` | pytest-django needs to create/drop its own `test_stockdesk_dev` database on each run; the app's least-privilege role didn't have that by default |
