# StockDesk Runbook

Someone unfamiliar with the code should be able to deploy and operate using
only this document. Day 13 covers live HTTPS app + Postgres on one EC2.
Day 14 will add S3, SES, backups, and staging.

**Region:** `ap-south-1` (Mumbai) only.  
**Instance:** `t3.micro`, Ubuntu 24.04, 20 GB gp3 + 2 GB swap.  
**Database:** PostgreSQL on the same instance — **no RDS**.  
**Cost:** set budget alerts at **$5** and **$10** before launching anything.

---

## 1. Before you launch (cost controls)

1. AWS root MFA on; daily work via IAM user (not root).
2. Billing → Budgets → alerts at $5 and $10.
3. Do **not** create RDS, NAT Gateway, or a load balancer.
4. Security group: SSH (22) from your IP; HTTP 80 + HTTPS 443 from needed clients.

---

## 2. Launch EC2

1. AMI: Ubuntu Server 24.04 LTS.
2. Type: `t3.micro`.
3. Storage: 20 GB gp3.
4. Key pair: download `.pem` and `chmod 400`.
5. Optional but recommended: allocate an **Elastic IP** and associate it (stopping the instance otherwise releases the public IP and breaks DNS).
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
git checkout day-13   # or main / the deploy branch you use
```

Copy env:

```bash
cp deploy/env.production.example .env
nano .env   # set SECRET_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, DB_PASSWORD
```

`DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` must match your hostname  
(e.g. `stockdesk.example.com` and `https://stockdesk.example.com`).

Use the **same** `DB_PASSWORD` you will set in Postgres (script default placeholder is `CHANGE_ME_DB_PASSWORD` — change both).

---

## 4. Bootstrap (Postgres, venv, gunicorn, nginx, HTTPS)

```bash
cd /opt/stockdesk/app
sudo bash deploy/setup_ec2.sh your.subdomain.example.com
```

What the script does:

- Installs Python 3.12, PostgreSQL, nginx, certbot
- Adds 2 GB swap
- Creates `stockdesk` OS user + Postgres DB/role
- Creates venv, installs `requirements/prod.txt`
- `migrate`, `collectstatic`, `bootstrap_roles`
- Enables `stockdesk.service` (gunicorn → Unix socket)
- Configures nginx to serve `/static/` and `/media/`, proxy everything else
- Runs certbot for HTTPS

If certbot fails, fix DNS, then:

```bash
sudo certbot --nginx -d your.subdomain.example.com
```

---

## 5. Verify

```bash
curl -fsS https://your.subdomain.example.com/health/
# expect: {"status":"ok","database":true}

sudo systemctl status stockdesk
sudo systemctl status nginx
sudo journalctl -u stockdesk -n 50 --no-pager
```

Create demo users (on the server):

```bash
cd /opt/stockdesk/app
sudo -u stockdesk /opt/stockdesk/venv/bin/python manage.py create_role_users
# or createsuperuser / seed_demo_data as needed
```

Open the site in a browser — login must work over **HTTPS**. Confirm Django admin static CSS loads (proves `collectstatic` + nginx `/static/`).

---

## 6. Day-to-day operations

| Task | Command |
|---|---|
| Restart app | `sudo systemctl restart stockdesk` |
| Reload nginx | `sudo systemctl reload nginx` |
| App logs | `sudo journalctl -u stockdesk -f` |
| App file log | `sudo tail -f /opt/stockdesk/app/logs/stockdesk.log` |
| Nginx error log | `sudo tail -f /var/log/nginx/error.log` |
| Django shell | `cd /opt/stockdesk/app && sudo -u stockdesk /opt/stockdesk/venv/bin/python manage.py shell` |

Deploy a new commit:

```bash
cd /opt/stockdesk/app
sudo -u stockdesk git pull
sudo -u stockdesk /opt/stockdesk/venv/bin/pip install -r requirements/prod.txt
sudo -u stockdesk /opt/stockdesk/venv/bin/python manage.py migrate --noinput
sudo -u stockdesk /opt/stockdesk/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart stockdesk
```

---

## 7. Production settings checklist (Day 13)

- [ ] `DEBUG = False` (`config.settings.prod` forces this)
- [ ] `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` set
- [ ] Gunicorn via systemd, enabled on boot
- [ ] nginx → gunicorn Unix socket
- [ ] Static files from `STATIC_ROOT` via nginx `/static/`
- [ ] HTTPS via certbot
- [ ] `/health/` returns OK with database true
- [ ] Postgres on-box (not RDS)

**Explicitly deferred to Day 14:** S3 media, SES email, outbox, cron/timers, nightly `pg_dump`, staging environment.

---

## 8. Common failures

| Symptom | Likely cause |
|---|---|
| 502 Bad Gateway | gunicorn down — `systemctl status stockdesk`, check socket `/run/stockdesk/gunicorn.sock` |
| CSS missing | forgot `collectstatic` or nginx `alias` path wrong |
| CSRF 403 on login | `CSRF_TRUSTED_ORIGINS` missing `https://…` |
| DisallowedHost | `DJANGO_ALLOWED_HOSTS` missing hostname |
| certbot fail | DNS A record not pointing at this instance yet |
| OOM during migrate | swap missing — re-run swap section of setup script |

---

## 9. Stopping the instance (cost)

Stopping EC2 saves money but **releases the public IP** unless you use an Elastic IP. After start, update DNS if the IP changed, then `systemctl status stockdesk nginx`.
