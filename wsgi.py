"""
Production and development entry point.

    Development:  python wsgi.py
    Render:       gunicorn -c gunicorn.conf.py wsgi:app
"""

import logging
import os
import sys
from logging.config import dictConfig

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config import settings

# --------------------------------------------------------------- logging
def configure_logging():
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "default",
            },
        },
        "root": {"level": settings.LOG_LEVEL, "handlers": ["console"]},
        # Request lines are already summarised by Gunicorn; keep them at INFO.
        "loggers": {
            "werkzeug": {"level": "WARNING"},
            "auth": {"level": settings.LOG_LEVEL},
        },
    })


configure_logging()
log = logging.getLogger("sac")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_c_modules():
    """Import the ctypes wrappers once; failures become user-facing messages."""
    bundle = {"classroom": None, "study_planner": None,
              "classroom_error": None, "study_planner_error": None}
    try:
        from modules import classroom
        bundle["classroom"] = classroom
    except (OSError, AttributeError) as exc:
        log.error("classroom C module unavailable: %s", exc)
        bundle["classroom_error"] = (
            "The C library for the classroom finder could not be loaded on this "
            "server. See the deployment notes (build libcore.so)."
        )
    try:
        from modules import study_planner
        bundle["study_planner"] = study_planner
    except (OSError, AttributeError) as exc:
        log.error("study planner C module unavailable: %s", exc)
        bundle["study_planner_error"] = (
            "The C library for the study planner could not be loaded on this "
            "server. See the deployment notes (build libcore.so)."
        )
    return bundle


def create_app():
    from app import auth
    from app.views import academic_views, auth_views, faculty_views, main_views, student_views

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=_secret_key(),
        SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.COOKIE_SECURE,
        SESSION_COOKIE_DOMAIN=settings.COOKIE_DOMAIN,
        PERMANENT_SESSION_LIFETIME=settings.SESSION_LIFETIME_MINUTES * 60,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        DEBUG=False,
        PREFERRED_URL_SCHEME="https" if settings.IS_PRODUCTION else "http",
        JSON_SORT_KEYS=False,
    )

    # Render terminates TLS in front of the app.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    app.extensions["sac"] = _load_c_modules()

    @app.template_filter("hhmm")
    def hhmm(value):
        from db.base import to_minutes

        try:
            minutes = to_minutes(value)
        except (TypeError, ValueError):
            return value
        return f"{minutes // 60:02d}:{minutes % 60:02d}" if minutes is not None else value

    auth.init_app(app)
    app.register_blueprint(main_views.bp)
    app.register_blueprint(auth_views.bp)
    app.register_blueprint(academic_views.bp)
    app.register_blueprint(student_views.bp)
    app.register_blueprint(faculty_views.bp)

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", message=getattr(error, "description", "")), 400

    log.info(
        "Smart Academic Companion started env=%s backend=%s c_core=%s",
        settings.APP_ENV,
        "postgresql" if settings.DATABASE_URL else "sqlite",
        "ok" if app.extensions["sac"]["classroom"] else "unavailable",
    )
    return app


def _secret_key():
    key = settings.SECRET_KEY
    if key:
        return key
    if settings.IS_PRODUCTION:
        # Refuse to run production with Flask's guessable development key.
        raise RuntimeError(
            "SECRET_KEY (or FLASK_SECRET_KEY) must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    log.warning("SECRET_KEY is not set; using a throw-away key for local development.")
    import secrets

    return secrets.token_hex(32)


app = create_app()


if __name__ == "__main__":
    if not settings.DATABASE_URL:
        try:
            from database import initialize_database

            initialize_database()
        except Exception as exc:  # noqa: BLE001 - local convenience only
            log.warning("could not initialize the local database: %s", exc)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=settings.DEBUG)
