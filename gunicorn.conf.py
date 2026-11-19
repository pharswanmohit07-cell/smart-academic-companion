"""Gunicorn configuration for Render.

Start command:

    gunicorn -c gunicorn.conf.py wsgi:app

The default is intentionally one worker with two request threads. The app
imports pandas/scikit-learn, so multiple workers would duplicate their memory
footprint on a small Render instance. Override only after measuring memory.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100

forwarded_allow_ips = "*"

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(L)ss'

# Share imported read-only modules such as numpy/scipy/sklearn via copy-on-write.
preload_app = True


def on_starting(server):
    """Refuse to boot in production without its required configuration."""
    from config import settings

    if not settings.IS_PRODUCTION:
        return
    missing = settings.missing_for_production()
    if missing:
        raise SystemExit(
            "Refusing to start: missing required environment variables: "
            + ", ".join(missing)
        )
