"""Public pages: landing page, health check and error pages."""

import logging
from contextlib import closing

from flask import (
    Blueprint, Response, current_app, jsonify, render_template, request,
)

from app import auth as auth_module
from app.accounts import profiles_table
from config import settings
from db import DatabaseError, backend_name, get_connection, migrations_required

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


@bp.route("/favicon.ico")
def favicon():
    """Silence the browser's automatic favicon request; the app has no icon."""
    return Response(status=204)


@bp.route("/")
def home():
    account = auth_module.current_account()
    if account is not None:
        return auth_module.redirect_to_dashboard(account)
    return render_template("home.html")


@bp.route("/dashboard")
def dashboard():
    """Single dashboard URL: sends each role to its own dashboard."""
    if auth_module.current_account() is None:
        from flask import redirect, url_for

        return redirect(url_for("auth.login"))
    return auth_module.redirect_to_dashboard(auth_module.current_account())


@bp.route("/healthz")
def healthz():
    """Health check for Render: no login, no secrets, no writes."""
    status = {"status": "ok", "backend": backend_name()}

    core = current_app.extensions.get("sac", {})
    status["c_core"] = "ok" if (
        core.get("classroom") is not None and core.get("study_planner") is not None
    ) else "unavailable"

    try:
        with closing(get_connection()) as connection:
            connection.execute("SELECT 1 AS ok").fetchone()
        status["database"] = "ok"
        try:
            pending = migrations_required()
            status["pending_migrations"] = pending
            if pending:
                status["status"] = "degraded"
        except Exception:  # noqa: BLE001 - status only; never fail the probe
            status["pending_migrations"] = "unknown"
    except DatabaseError as exc:
        log.warning("health check database failure: %s", exc)
        status["database"] = "unavailable"
        status["status"] = "degraded"

    if settings.IS_PRODUCTION and not settings.SECRET_KEY:
        status["status"] = "misconfigured"
        status["error"] = "SECRET_KEY is not set"

    code = 200 if status["status"] == "ok" else 503
    return jsonify(status), code


@bp.errorhandler(403)
def forbidden(error):
    log.warning("403 for %s %s", request.method, request.path)
    if auth_module.current_account() is None:
        return auth_module.redirect_to_dashboard(None)
    return render_template("errors/403.html"), 403


@bp.errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404


@bp.errorhandler(500)
def server_error(error):
    log.exception("server error on %s %s", request.method, request.path)
    return render_template("errors/500.html"), 500
