"""
Authentication state, session handling and route authorization.

Security model
--------------
* The browser holds only an opaque Flask cookie (``HttpOnly``, ``SameSite=Lax``,
  ``Secure`` in production) that stores the account summary and the Supabase
  refresh token. Passwords and access tokens are never stored in the cookie
  session and never rendered into HTML.
* Every request re-validates the Supabase session against the sign-in time and
  refreshes the access token before it expires. If the refresh is rejected the
  session is cleared, so a revoked or expired login stops working.
* The role used for authorization always comes from ``public.user_profiles``
  through the server's database connection. Nothing in the cookie, the URL or
  Supabase user metadata can choose it.
* ``@login_required`` protects "you must be signed in"; ``@role_required``
  protects faculty/admin areas; ownership is checked in the views with the
  helpers below (``require_class_owner``, ``require_student_access``).
"""

import functools
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone

from flask import (
    abort, current_app, flash, g, redirect, request, session, url_for,
)

from app.accounts import Account, load_account
from app.supabase_client import AuthError, get_auth
from config import settings

log = logging.getLogger(__name__)

SESSION_ACCOUNT = "account"
SESSION_REFRESH = "sb_refresh_token"
SESSION_SIGNED_IN_AT = "signed_in_at"
SESSION_REFRESHED_AT = "refreshed_at"

# Access tokens are refreshed once they are this close to expiry.
REFRESH_MARGIN_SECONDS = 120
# Minimum age before a session's Supabase token is refreshed again (avoids one
# network call per request while staying well inside the token lifetime).
REFRESH_INTERVAL_SECONDS = int(os.environ.get("SESSION_REFRESH_INTERVAL_SECONDS", "60"))
# The application session is dropped after this long even if Supabase keeps it.
MAX_SESSION_SECONDS = settings.SESSION_LIFETIME_MINUTES * 60


# ---------------------------------------------------------------- session
def dashboard_endpoint(account):
    """Where an account belongs after sign-in (trusted role decides)."""
    if account is None:
        return "auth.login"
    if account.is_faculty:
        return "faculty.dashboard"
    if account.student_id is not None:
        return "student.dashboard"
    return "auth.no_account"


def redirect_to_dashboard(account=None):
    """303 redirect to the caller's dashboard."""
    return redirect(url_for(dashboard_endpoint(account or current_account())))


def sign_in(account: Account, supabase_refresh_token: str) -> None:
    """Start a clean session for ``account`` (prevents session fixation)."""
    # Only application state is discarded. The CSRF token is deliberately kept:
    # a second tab or a back button still holds a form carrying it, and the
    # token is not derived from the identity, so it cannot leak privileges.
    csrf_token = session.get("csrf_token")
    session.clear()
    if csrf_token:
        session["csrf_token"] = csrf_token
    now = int(time.time())
    session[SESSION_ACCOUNT] = account.to_session()
    session[SESSION_REFRESH] = supabase_refresh_token
    session[SESSION_SIGNED_IN_AT] = now
    session[SESSION_REFRESHED_AT] = now
    session.permanent = True


def sign_out() -> None:
    session.clear()


def current_account() -> Account | None:
    """Return the signed-in account, validating the session on every request.

    The result is read from the signed cookie on each call (a handful of dict
    lookups) rather than cached in ``g``: keeping a cache that was filled while
    a stale request context was active would make the next request look
    anonymous.
    """
    account = Account.from_session(session.get(SESSION_ACCOUNT))
    if account is None:
        return None

    signed_in_at = session.get(SESSION_SIGNED_IN_AT, 0)
    age = time.time() - signed_in_at if signed_in_at else None
    if age is None or age < 0 or age > MAX_SESSION_SECONDS:
        log.info("session expired for user %s", account.user_id)
        sign_out()
        return None

    # Re-read the trusted role from the database so a revoke or a promotion
    # takes effect on the next request. The cookie itself never grants access.
    fresh = load_account(account.user_id, account.email, account.display_name)
    if fresh.user_id != account.user_id:
        sign_out()
        return None
    account = fresh
    session[SESSION_ACCOUNT] = account.to_session()

    if not _refresh_if_needed():
        sign_out()
        return None

    g.account = account
    return account


def _refresh_if_needed() -> bool:
    refreshed_at = session.get(SESSION_REFRESHED_AT, 0)
    age = time.time() - refreshed_at
    # Signed in recently (or just refreshed): nothing to do yet.
    if 0 <= age < REFRESH_INTERVAL_SECONDS:
        return True
    if not settings.SUPABASE_AUTH_ENABLED:
        # Local development without Supabase keeps the session for its lifetime.
        return True
    refresh_token = session.get(SESSION_REFRESH)
    if not refresh_token:
        return False
    try:
        result = get_auth().refresh(refresh_token)
    except AuthError as exc:
        log.info("session refresh rejected: %s", exc)
        return False
    if not result.access_token or not result.refresh_token:
        return False
    session[SESSION_REFRESH] = result.refresh_token
    session[SESSION_REFRESHED_AT] = int(time.time())
    return True


def reload_account():
    """Re-read the trusted role after a change (e.g. first-run bootstrap)."""
    account = current_account()
    if account is None:
        return None
    fresh = load_account(account.user_id, account.email, account.display_name)
    session[SESSION_ACCOUNT] = fresh.to_session()
    g.account = fresh
    return fresh


def access_token_for_supabase():
    """Return a short-lived Supabase access token, or None.

    Only needed by code that calls Supabase as the signed-in user (for
    example password changes). It is never stored in the session.
    """
    refresh_token = session.get(SESSION_REFRESH)
    if not refresh_token or not settings.SUPABASE_AUTH_ENABLED:
        return None
    try:
        return get_auth().refresh(refresh_token).access_token
    except AuthError:
        return None


# ----------------------------------------------------------- decorators
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if current_account() is None:
            if request.accept_mimetypes.best == "application/json":
                return {"error": "authentication required"}, 401
            flash("Please sign in to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    """Allow only the given trusted roles (``student``/``faculty``/``admin``)."""
    allowed = set(roles)

    def decorator(view):
        @functools.wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            account = current_account()
            if account.role not in allowed:
                log.warning(
                    "blocked %s %s for role=%s user=%s",
                    request.method, request.path, account.role, account.user_id,
                )
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def faculty_required(view):
    return role_required("faculty", "admin")(view)


def admin_required(view):
    return role_required("admin")(view)


# ------------------------------------------------------------ ownership
def owned_class_ids(account=None):
    """Class ids the signed-in faculty account may manage (None = all)."""
    account = account or current_account()
    if account is None:
        return []
    if account.is_admin:
        return None
    if not account.teacher_id:
        return []
    from contextlib import closing

    from db import get_connection

    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT class_id FROM faculty_classes WHERE owner_teacher_id = ?",
            (account.teacher_id,),
        ).fetchall()
    return [row["class_id"] for row in rows]


def require_class_owner(class_id):
    """Abort unless the current faculty/admin account owns ``class_id``."""
    account = current_account()
    if account is None or not account.is_faculty:
        abort(403)
    if account.is_admin:
        return
    from contextlib import closing

    from db import get_connection

    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT 1 AS ok FROM faculty_classes "
            "WHERE class_id = ? AND owner_teacher_id = ?",
            (class_id, account.teacher_id),
        ).fetchone()
    if row is None:
        log.warning("user %s requested class %s they do not own",
                    account.user_id, class_id)
        abort(403)


def require_student_ids(student_ids):
    """Abort unless every student belongs to a class the faculty owns.

    Students (role student) never reach this path: their views only ever read
    their own ``student_id``.
    """
    ids = sorted({int(value) for value in student_ids})
    if not ids:
        return
    account = current_account()
    if account is None or not account.is_faculty:
        abort(403)
    if account.is_admin:
        return
    from contextlib import closing

    from db import get_connection

    placeholders = ", ".join("?" for _ in ids)
    with closing(get_connection()) as connection:
        rows = connection.execute(
            f"""SELECT s.student_id
                  FROM students AS s
                  JOIN faculty_classes AS c ON c.class_id = s.class_id
                 WHERE s.student_id IN ({placeholders})
                   AND c.owner_teacher_id = ?""",
            (*ids, account.teacher_id),
        ).fetchall()
    allowed = {row["student_id"] for row in rows}
    if set(ids) - allowed:
        log.warning("user %s blocked from students %s",
                    account.user_id, sorted(set(ids) - allowed))
        abort(403)


def require_own_student(student_id):
    """Abort unless ``student_id`` is the signed-in student's own record."""
    account = current_account()
    if account is None:
        abort(403)
    if account.is_admin:
        return
    if account.student_id != int(student_id):
        log.warning("user %s requested student %s (own=%s)",
                    account.user_id, student_id, account.student_id)
        abort(403)


# -------------------------------------------------------------- helpers
def new_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def verify_csrf_token():
    """Reject a POST whose hidden token does not match the session token."""
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    # The token is minted when the form page renders and stored in the signed
    # session cookie; a POST without it did not come from this application.
    if not expected:
        log.warning("CSRF token missing for %s %s", request.method, request.path)
        abort(400, "The form expired or was not submitted from this site. Please try again.")
    if not supplied or not secrets.compare_digest(str(expected), str(supplied)):
        log.warning("CSRF check failed for %s %s", request.method, request.path)
        abort(400, "The form expired or was not submitted from this site. Please try again.")


def init_app(app):
    """Register request hooks and template helpers."""

    @app.before_request
    def _load_account():
        g.account = None
        current_account()

    @app.before_request
    def _csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            verify_csrf_token()

    @app.context_processor
    def _inject_account():
        account = getattr(g, "account", None)
        return {
            "current_user": account,
            "csrf_token": new_csrf_token,
            "display_name": account.display_name if account else "",
            "today": datetime.now(timezone.utc),
        }

    @app.before_request
    def _start_session():
        session.permanent = True

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        return response

    @app.teardown_request
    def _log_error(exception):
        if exception is not None:
            log.exception("unhandled error on %s %s", request.method, request.path)


def new_auth_nonce():
    """Random nonce stored before a recovery round-trip."""
    return uuid.uuid4().hex
