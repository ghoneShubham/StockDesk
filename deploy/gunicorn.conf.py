# Gunicorn config for StockDesk (Day 13).
# Bind is a Unix socket; nginx proxies to it.
# Override workers via environment if needed: WEB_CONCURRENCY=2

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "unix:/run/stockdesk/gunicorn.sock")
workers = int(os.environ.get("WEB_CONCURRENCY", max(2, min(4, multiprocessing.cpu_count()))))
worker_class = "sync"
threads = 1
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True
# t3.micro is memory-tight — recycle workers periodically
max_requests = 500
max_requests_jitter = 50
preload_app = False
