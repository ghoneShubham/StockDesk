#!/usr/bin/env bash
# StockDesk Day 13 — Ubuntu 22.04/24.04 EC2 bootstrap (ap-south-1, t3.micro)
# Run as root AFTER the repo is at /opt/stockdesk/app and .env exists.
#
#   sudo bash deploy/setup_ec2.sh your.subdomain.example.com
#
set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: sudo bash deploy/setup_ec2.sh <hostname>"
  exit 1
fi

APP_ROOT=/opt/stockdesk/app
VENV=/opt/stockdesk/venv
APP_USER=stockdesk
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

export DEBIAN_FRONTEND=noninteractive

echo "==> OS info"
. /etc/os-release
echo "Running on ${PRETTY_NAME:-unknown}"

echo "==> Packages"
apt-get update -y
# Use distro python3 (3.10 on 22.04, 3.12 on 24.04) — do not hardcode 3.12
apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  postgresql postgresql-contrib libpq-dev \
  nginx certbot python3-certbot-nginx \
  git curl build-essential libjpeg-dev zlib1g-dev \
  pkg-config

python3 --version

echo "==> 2 GB swap (t3.micro)"
if [[ ! -f /swapfile ]]; then
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> App user"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home /opt/stockdesk --shell /usr/sbin/nologin "$APP_USER"
mkdir -p /opt/stockdesk
chown -R "$APP_USER":www-data /opt/stockdesk

if [[ ! -f "$APP_ROOT/.env" ]]; then
  echo "ERROR: create $APP_ROOT/.env from deploy/env.production.example first"
  exit 1
fi

# Read DB_PASSWORD from .env for role creation (simple KEY=VAL lines only)
DB_PASSWORD="$(grep -E '^DB_PASSWORD=' "$APP_ROOT/.env" | tail -n1 | cut -d= -f2- | tr -d '\r')"
DB_NAME="$(grep -E '^DB_NAME=' "$APP_ROOT/.env" | tail -n1 | cut -d= -f2- | tr -d '\r')"
DB_USER="$(grep -E '^DB_USER=' "$APP_ROOT/.env" | tail -n1 | cut -d= -f2- | tr -d '\r')"
DB_NAME="${DB_NAME:-stockdesk}"
DB_USER="${DB_USER:-stockdesk}"
if [[ -z "$DB_PASSWORD" ]]; then
  echo "ERROR: DB_PASSWORD missing in .env"
  exit 1
fi

echo "==> PostgreSQL role + database"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
  END IF;
END\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

echo "==> Python venv + deps"
# Recreate venv if a previous failed run left a broken one
rm -rf "$VENV"
python3 -m venv "$VENV"
"$PIP" install --upgrade pip
"$PIP" install -r "$APP_ROOT/requirements/prod.txt"
chown -R "$APP_USER":www-data /opt/stockdesk

echo "==> Django migrate + static + roles"
cd "$APP_ROOT"
mkdir -p "$APP_ROOT/media" "$APP_ROOT/logs"
chown -R "$APP_USER":www-data "$APP_ROOT"
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
  "$PY" manage.py migrate --noinput
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
  "$PY" manage.py collectstatic --noinput
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
  "$PY" manage.py bootstrap_roles || true

echo "==> systemd"
cp "$APP_ROOT/deploy/systemd/stockdesk.service" /etc/systemd/system/stockdesk.service
systemctl daemon-reload
systemctl enable stockdesk.service
systemctl restart stockdesk.service

echo "==> nginx"
sed "s/STOCKDESK_DOMAIN/${DOMAIN}/g" "$APP_ROOT/deploy/nginx/stockdesk.conf" \
  > /etc/nginx/sites-available/stockdesk
ln -sfn /etc/nginx/sites-available/stockdesk /etc/nginx/sites-enabled/stockdesk
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

echo "==> TLS (certbot)"
if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
  -m "admin@${DOMAIN}" --redirect; then
  echo "HTTPS OK"
else
  echo "WARN: certbot failed — fix DNS A record, then re-run:"
  echo "  sudo certbot --nginx -d ${DOMAIN}"
fi

echo "==> Health check"
sleep 2
curl -fsS "https://${DOMAIN}/health/" || curl -fsS "http://127.0.0.1/health/" -H "Host: ${DOMAIN}" || true

echo "Day 13/14 bootstrap finished. See docs/RUNBOOK.md"
echo "Next (Day 14): configure S3+SES in .env, then:"
echo "  sudo bash deploy/install_timers.sh"
echo "  sudo bash deploy/setup_staging.sh   # after .env.staging exists"
