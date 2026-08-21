# StockDesk Runbook

Someone unfamiliar with the code should be able to deploy and operate using
only this document.

**Region:** `ap-south-1` (Mumbai) only.  
**Instance:** `t3.micro`, Ubuntu 24.04 (or similar), 20 GB gp3 + 2 GB swap.  
**Database:** PostgreSQL on the same instance — **no RDS**.  
**Cost:** set budget alerts at **$5** and **$10** before launching anything.

**Python:** use **3.12 or 3.13** for the venv — not 3.14+ (wheels for pinned deps may be missing).

---

## 1. Before you launch (cost controls)

1. AWS root MFA on; daily work via IAM user (not root).
2. Billing → Budgets → alerts at $5 and $10.
3. Do **not** create RDS, NAT Gateway, or a load balancer.
4. Security group: SSH (22) from your IP; HTTP 80 + HTTPS 443 from needed clients; TCP **8080** from your IP if you use staging.

---

## 2. Launch EC2

1. AMI: Ubuntu Server 24.04 LTS (prefer LTS — avoid bleeding-edge images that only ship Python 3.14+).
2. Type: `t3.micro`.
3. Storage: 20 GB gp3.
4. Key pair: download `.pem` and `chmod 400`.
5. Optional but recommended: allocate an **Elastic IP** and associate it.
6. Create/update a DNS **A record** for your subdomain → Elastic IP / public IP.

SSH:

```bash
ssh -i your-key.pem ubuntu@YOUR_PUBLIC_IP
```

---

## 3. Place the application code

```bash
sudo mkdir -p /opt/stockdesk
sudo chown ubuntu:ubuntu /opt/stockdesk
cd /opt/stockdesk
git clone YOUR_REPO_URL app
cd app
git checkout day-14   # or main / the deploy branch you use
```

Copy env:

```bash
cp deploy/env.production.example .env
nano .env   # SECRET_KEY, ALLOWED_HOSTS, CSRF, DB_PASSWORD, S3, SES, alert recipients
```

`DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` must match your hostname.

---

## 4. Bootstrap production (Postgres, venv, gunicorn, nginx, HTTPS)

```bash
cd /opt/stockdesk/app
sudo bash deploy/setup_ec2.sh your.subdomain.example.com
```

If the AMI’s default `python3` is 3.14+, install 3.13 and recreate the venv **before** relying on the script:

```bash
sudo apt-get install -y python3.13 python3.13-venv python3.13-dev
# then edit setup or manually: python3.13 -m venv /opt/stockdesk/venv
```

Verify:

```bash
curl -fsS https://your.subdomain.example.com/health/
sudo systemctl status stockdesk nginx
```

Create demo users:

```bash
cd /opt/stockdesk/app
sudo -u stockdesk /opt/stockdesk/venv/bin/python manage.py create_role_users
```

---

## 5. Day 14 — S3 media

1. Create one S3 bucket in `ap-south-1` (e.g. `stockdesk-media-<unique>`). Block public access ON.
2. Create an IAM user with a **bucket-scoped** policy only (list/get/put/delete on that bucket) — **not** `AmazonS3FullAccess`.
3. Put keys in `.env`:

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=stockdesk-media-<unique>
AWS_S3_REGION_NAME=ap-south-1
```

4. Restart app: `sudo systemctl restart stockdesk`
5. Upload a product image and generate an invoice PDF — both should land under `media/` in the bucket.

When the bucket name is empty, media stays on local disk (`MEDIA_ROOT`) as on Day 13.

---

## 6. Day 14 — SES email + outbox

1. SES (ap-south-1): verify the domain or the `DEFAULT_FROM_EMAIL` address. Sandbox is fine — verify recipient addresses too.
2. Create SMTP credentials in SES → put `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` in `.env`.
3. Set `LOW_STOCK_ALERT_RECIPIENTS=you@verified.example.com` (comma-separated OK).
4. Restart `stockdesk`.

Ops emails **never** send during the HTTP request. Commands enqueue rows into `EmailOutbox`; a timer drains them:

```bash
# manual smoke
sudo -u stockdesk env DJANGO_SETTINGS_MODULE=config.settings.prod \
  /opt/stockdesk/venv/bin/python manage.py alert_low_stock --force
sudo -u stockdesk env DJANGO_SETTINGS_MODULE=config.settings.prod \
  /opt/stockdesk/venv/bin/python manage.py drain_email_outbox
```

Install timers:

```bash
sudo bash deploy/install_timers.sh
systemctl list-timers 'stockdesk-*' --no-pager
```

| Timer | Job |
|---|---|
| `stockdesk-outbox.timer` | every ~1 min — `drain_email_outbox` |
| `stockdesk-low-stock.timer` | daily 07:00 — `alert_low_stock` |
| `stockdesk-dead-stock.timer` | Mondays 07:30 — `alert_dead_stock` |
| `stockdesk-reconcile.timer` | daily 02:30 — `reconcile_stock --email-on-drift` |
| `stockdesk-backup.timer` | daily 03:15 — `backup_database` |

---

## 7. Day 14 — backups + restore drill

### Nightly backup

Requires `AWS_STORAGE_BUCKET_NAME` set. Dumps Postgres, gzips, uploads to `s3://$BUCKET/backups/YYYY-MM-DD/...`, deletes objects older than `BACKUP_RETENTION_DAYS` (default 7).

```bash
sudo -u stockdesk env DJANGO_SETTINGS_MODULE=config.settings.prod \
  /opt/stockdesk/venv/bin/python manage.py backup_database
# or: sudo systemctl start stockdesk-backup.service
```

### Restore drill (required — do this once on staging or a throwaway DB)

**Do not wipe production until you have practiced on staging.**

```bash
# 1) Download a backup object from S3 to /tmp/stockdesk-restore.sql.gz
aws s3 cp s3://YOUR_BUCKET/backups/DATE/FILE.sql.gz /tmp/stockdesk-restore.sql.gz

# 2) Stop writers
sudo systemctl stop stockdesk stockdesk-staging || true

# 3) Restore into a scratch DB (example: stockdesk_staging)
gunzip -c /tmp/stockdesk-restore.sql.gz | sudo -u postgres psql stockdesk_staging

# 4) Start staging and verify
sudo systemctl start stockdesk-staging
curl -fsS http://127.0.0.1:8080/health/
# Log in, open dashboard / a known invoice — confirm data present.

# 5) Record date + backup key used in your ops notes.
sudo systemctl start stockdesk
```

If you must restore **production**, take a final `backup_database` first, then restore into `DB_NAME` the same way, and only after `/health/` + login checks pass.

---

## 8. Day 14 — staging environment

Staging = **separate database** + **gunicorn** + nginx on **port 8080**. Promote to production only after staging looks good.

```bash
cp deploy/env.staging.example .env.staging
nano .env.staging   # different SECRET_KEY, DB_NAME=stockdesk_staging, ALLOWED_HOSTS, CSRF for :8080

sudo bash deploy/setup_staging.sh
```

Open security group **8080** from your IP. Check:

```bash
curl -fsS http://YOUR_PUBLIC_IP:8080/health/
```

Deploy flow: pull → migrate/collectstatic on **staging** → smoke test → then restart **production**.

---

## 9. Day-to-day operations

| Task | Command |
|---|---|
| Restart prod app | `sudo systemctl restart stockdesk` |
| Restart staging | `sudo systemctl restart stockdesk-staging` |
| App logs | `sudo journalctl -u stockdesk -f` |
| Timer logs | `sudo journalctl -u stockdesk-backup -u stockdesk-outbox -n 100 --no-pager` |
| File log | `sudo tail -f /opt/stockdesk/app/logs/stockdesk.log` |

Deploy a new commit (production):

```bash
cd /opt/stockdesk/app
sudo -u stockdesk git pull
sudo -u stockdesk /opt/stockdesk/venv/bin/pip install -r requirements/prod.txt
sudo -u stockdesk env DJANGO_SETTINGS_MODULE=config.settings.prod \
  /opt/stockdesk/venv/bin/python manage.py migrate --noinput
sudo -u stockdesk env DJANGO_SETTINGS_MODULE=config.settings.prod \
  /opt/stockdesk/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart stockdesk
```

---

## 10. Settings checklist

### Production (Day 13+)

- [ ] `DEBUG = False`
- [ ] `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`
- [ ] Gunicorn + nginx + HTTPS
- [ ] `/health/` OK
- [ ] Postgres on-box (not RDS)

### Day 14 extras

- [ ] S3 bucket + scoped IAM; `AWS_STORAGE_BUCKET_NAME` set
- [ ] SES SMTP + verified from/to; `LOW_STOCK_ALERT_RECIPIENTS` set
- [ ] `install_timers.sh` enabled; outbox drains
- [ ] `backup_database` succeeded at least once
- [ ] Restore drill documented (staging DB)
- [ ] Staging on `:8080` with `stockdesk_staging` DB

---

## 11. Common failures

| Symptom | Likely cause |
|---|---|
| 502 Bad Gateway | gunicorn down — `systemctl status stockdesk` |
| CSS missing | forgot `collectstatic` |
| CSRF 403 | `CSRF_TRUSTED_ORIGINS` missing scheme/host/port |
| DisallowedHost | `DJANGO_ALLOWED_HOSTS` |
| pip / psycopg fails | Python 3.14+ — use 3.12/3.13 |
| Backup command errors | empty `AWS_STORAGE_BUCKET_NAME` or IAM missing `s3:PutObject` |
| Emails never arrive | SES sandbox + unverified recipient; or outbox timer not installed |
| Staging 502 | `stockdesk-staging` down or SG missing 8080 |
| Payment link fails | Missing `RAZORPAY_KEY_ID/SECRET` (test keys) or live key rejected |
| Webhook 403 | Wrong `RAZORPAY_WEBHOOK_SECRET` or not using raw body signature |

---

## 12. Day 15 — Razorpay (Module F)

1. Razorpay Dashboard → **Test mode** → API Keys → put `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in `.env` (never `rzp_live_…`).
2. Webhooks → add URL `https://YOUR_DOMAIN/webhooks/razorpay/` → secret → `RAZORPAY_WEBHOOK_SECRET`.
3. Subscribe at least to `payment_link.paid` (and optionally `payment.captured`).
4. Restart app. On an unpaid invoice → **Send payment link** → pay with Razorpay test cards → sale should become **Paid** via webhook (not the browser redirect).
5. Owner → Financial reports → **Payment reconciliation** for gateway vs books mismatches.
6. Re-run roles after deploy: `python manage.py bootstrap_roles`

---

## 13. Stopping the instance (cost)

Stopping EC2 saves money but **releases the public IP** unless you use an Elastic IP. After start, update DNS if needed, then `systemctl status stockdesk nginx`.

Cost notes: [`docs/COST.md`](COST.md). Security audit: [`docs/SECURITY.md`](SECURITY.md).
