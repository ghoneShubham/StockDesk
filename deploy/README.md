# Day 13 deploy artifacts

| Path | Role |
|---|---|
| `deploy/setup_ec2.sh` | Bootstrap Ubuntu 24.04 EC2 (Postgres, venv, migrate, collectstatic, systemd, nginx, certbot) |
| `deploy/env.production.example` | Template for `/opt/stockdesk/app/.env` |
| `deploy/gunicorn.conf.py` | Gunicorn workers / Unix socket |
| `deploy/systemd/stockdesk.service` | systemd unit for gunicorn |
| `deploy/nginx/stockdesk.conf` | nginx site (static + media + proxy) |

Full operator steps: [`docs/RUNBOOK.md`](../docs/RUNBOOK.md).

Day 14 will add S3, SES, backups, and staging — do not invent those here.
