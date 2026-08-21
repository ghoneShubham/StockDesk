# Day 13–14 deploy artifacts

| Path | Role |
|---|---|
| `deploy/setup_ec2.sh` | Bootstrap Ubuntu EC2 (Postgres, venv, migrate, collectstatic, systemd, nginx, certbot) |
| `deploy/setup_staging.sh` | Day 14 — separate DB + gunicorn + nginx `:8080` |
| `deploy/install_timers.sh` | Day 14 — enable outbox / alerts / reconcile / backup timers |
| `deploy/env.production.example` | Template for `/opt/stockdesk/app/.env` |
| `deploy/env.staging.example` | Template for `/opt/stockdesk/app/.env.staging` |
| `deploy/gunicorn.conf.py` | Gunicorn workers / Unix socket (production) |
| `deploy/systemd/stockdesk.service` | Production gunicorn |
| `deploy/systemd/stockdesk-staging.service` | Staging gunicorn |
| `deploy/systemd/stockdesk-*.timer` | Scheduled jobs |
| `deploy/nginx/stockdesk.conf` | Production nginx |
| `deploy/nginx/stockdesk-staging.conf` | Staging nginx on port 8080 |

Full operator steps: [`docs/RUNBOOK.md`](../docs/RUNBOOK.md).
