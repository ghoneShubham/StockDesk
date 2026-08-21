#!/usr/bin/env bash
# StockDesk Day 14 — create staging DB + gunicorn on :8080
# Prerequisites: production bootstrap already done (/opt/stockdesk/venv exists).
#
#   sudo bash deploy/setup_staging.sh
#
set -euo pipefail

APP_ROOT=/opt/stockdesk/app
VENV=/opt/stockdesk/venv
APP_USER=stockdesk
ENV_FILE="$APP_ROOT/.env.staging"
PY="$VENV/bin/python"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: create $ENV_FILE from deploy/env.staging.example first"
  exit 1
fi
if [[ ! -x "$PY" ]]; then
  echo "ERROR: missing $PY — run deploy/setup_ec2.sh first"
  exit 1
fi

DB_PASSWORD="$(grep -E '^DB_PASSWORD=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r')"
DB_NAME="$(grep -E '^DB_NAME=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r')"
DB_USER="$(grep -E '^DB_USER=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r')"
DB_NAME="${DB_NAME:-stockdesk_staging}"
DB_USER="${DB_USER:-stockdesk}"
if [[ -z "$DB_PASSWORD" ]]; then
  echo "ERROR: DB_PASSWORD missing in .env.staging"
  exit 1
fi

echo "==> Staging Postgres database ${DB_NAME}"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

echo "==> Media/logs dirs"
mkdir -p "$APP_ROOT/media_staging" "$APP_ROOT/logs"
chown -R "$APP_USER":www-data "$APP_ROOT/media_staging" "$APP_ROOT/logs"

echo "==> Migrate + collectstatic (staging settings)"
cd "$APP_ROOT"
# Staging may share STATIC_ROOT with prod — collectstatic is idempotent.
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.staging \
  "$PY" manage.py migrate --noinput
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.staging \
  "$PY" manage.py collectstatic --noinput
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.staging \
  "$PY" manage.py bootstrap_roles || true

echo "==> systemd staging"
cp "$APP_ROOT/deploy/systemd/stockdesk-staging.service" /etc/systemd/system/stockdesk-staging.service
systemctl daemon-reload
systemctl enable stockdesk-staging.service
systemctl restart stockdesk-staging.service

echo "==> nginx staging (:8080)"
cp "$APP_ROOT/deploy/nginx/stockdesk-staging.conf" /etc/nginx/sites-available/stockdesk-staging
ln -sfn /etc/nginx/sites-available/stockdesk-staging /etc/nginx/sites-enabled/stockdesk-staging
nginx -t
systemctl reload nginx

echo "==> Open Security Group TCP 8080 from your IP if you need external access."
echo "Health: curl -fsS http://127.0.0.1:8080/health/ -H 'Host: localhost'"
curl -fsS http://127.0.0.1:8080/health/ -H "Host: localhost" || true
echo
echo "Day 14 staging bootstrap finished."
