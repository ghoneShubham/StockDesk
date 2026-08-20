#!/usr/bin/env bash
# Install Day 14 systemd timers (outbox drain, alerts, reconcile, backup).
# Run once on the EC2 host after production is up:
#
#   sudo bash deploy/install_timers.sh
#
set -euo pipefail

APP_ROOT=/opt/stockdesk/app
SRC="$APP_ROOT/deploy/systemd"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: $SRC not found"
  exit 1
fi

echo "==> Installing oneshot services + timers"
for unit in \
  stockdesk-outbox.service stockdesk-outbox.timer \
  stockdesk-low-stock.service stockdesk-low-stock.timer \
  stockdesk-dead-stock.service stockdesk-dead-stock.timer \
  stockdesk-reconcile.service stockdesk-reconcile.timer \
  stockdesk-backup.service stockdesk-backup.timer
do
  cp "$SRC/$unit" "/etc/systemd/system/$unit"
done

systemctl daemon-reload

for timer in \
  stockdesk-outbox.timer \
  stockdesk-low-stock.timer \
  stockdesk-dead-stock.timer \
  stockdesk-reconcile.timer \
  stockdesk-backup.timer
do
  systemctl enable --now "$timer"
done

systemctl list-timers 'stockdesk-*' --no-pager
echo "Day 14 timers installed."
