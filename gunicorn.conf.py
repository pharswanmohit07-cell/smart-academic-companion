"""Gunicorn configuration for Render.

Start command (exactly what Render should run):

    gunicorn -c gunicorn.conf.py wsgi:app

Render sets ``$PORT``; the bind address and worker count are tuned for its
smallest paid instance and can be overridden with environment variables.
"""

import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Each worker loads pandas and scikit-learn, so keep the count modest.
#
# Connection budget: every request opens its own PostgreSQL connection and
# closes it before the response returns (see db.get_connection usage), so the
# live connections are bounded by workers x threads. With points below
# (2 x 4 = 8) plus Supabase's own sessions, a Session-pooler DATABASE_URL is
# required; the direct database port allows far fewer connections. Increase
# WEB_CONCURRENCY only together with the Supabase connection limit.
workers = int(os.environ.get("WEB_CONCURRENCY", min(2, multiprocessing.cpu_count())))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100

# Render terminates TLS; the app trusts one proxy hop (see wsgi.ProxyFix).
forwarded_allow_ips = "*"

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(L)ss'

# Fail fast instead of leaving a half-ready instance in rotation.
preload_app = False


def on_starting(server):
    """Refuse to boot in production without its required configuration.

    A worker that starts without ``SECRET_KEY`` or a database URL would serve
    pages that cannot authenticate anyone, so the process exits instead.
    """
    from config import settings

    if not settings.IS_PRODUCTION:
        return
    missing = settings.missing_for_production()
    if missing:
        raise SystemExit(
            "Refusing to start: missing required environment variables: "
            + ", ".join(missing)
        )
