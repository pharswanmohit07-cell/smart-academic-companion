"""
One sign-in page for every role.

Flow
----
* ``GET  /auth/login``   credentials form (email, password). There is no role
  selector: after sign-in the trusted role in ``public.user_profiles`` decides
  whether the student or the faculty dashboard opens.
* ``POST /auth/login``   Supabase Auth password grant. On success the role is
  read from the database and the user is redirected.
* ``POST /auth/signup``  Creates the account with the default ``student``
  role (assigned by the database trigger). Faculty and admin accounts cannot be
  created from this form.
* ``POST /auth/logout``  Revokes the Supabase refresh token and clears the
  cookie session.
* ``POST /auth/forgot-password`` / ``GET,POST /auth/reset-password``
  Supabase recovery emails. The link comes back to ``/auth/confirm`` which
  exchanges the token for a session and then asks for a new password.
"""

import logging
import re
import time

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for,
)

from app import auth
from app.accounts import (
    DEFAULT_ROLE, Account, AccountError, bootstrap_signup, email_domain_allowed,
    ensure_profile, ensure_student_record, ensure_teacher_record, load_account,
    safe_role,
)
from app.supabase_client import AuthError, get_auth
from config import settings

log = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
# A verified recovery link may be used to set a password within this window.
RECOVERY_WINDOW_SECONDS = 15 * 60

# Where each role lands after signing in.
def dashboard_for(account):
    return url_for(auth.dashboard_endpoint(account))


def _app_url(path):
    """Absolute URL for email links (falls back to the request host)."""
    base = settings.APP_BASE_URL or request.url_root.rstrip("/")
    return f"{base}{path}"


def _safe_next(target):
    """Only allow same-site relative redirects."""
    if not target:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


def _finish_sign_in(result):
    """Load the trusted account, prepare its records, and start the session."""
    account = load_account(result.user_id, result.email, result.display_name)

    if account.is_admin or account.is_faculty:
        # Faculty own classes; an admin may own classes too. The row is created
        # once and never grants a role by itself.
        ensure_teacher_record(account)
        account = load_account(result.user_id, result.email, result.display_name)

    if account.is_student:
        try:
            student_id = ensure_student_record(account)
        except AccountError as exc:
            flash(str(exc), "danger")
            return None
        account = load_account(result.user_id, result.email, result.display_name)
        account.student_id = student_id

    auth.sign_in(account, result.refresh_token)
    log.info("sign-in user=%s role=%s", account.user_id, account.role)
    return account


@bp.route("/login", methods=["GET", "POST"])
def login():
    if auth.current_account() is not None:
        return redirect(dashboard_for(auth.current_account()))

    next_url = _safe_next(request.values.get("next"))
    error = None
    email = ""

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not EMAIL_RE.match(email) or not password:
            error = "Enter your email address and password."
        else:
            try:
                result = get_auth().sign_in_with_password(email, password)
            except AuthError as exc:
                error = exc.message
            else:
                account = _finish_sign_in(result)
                if account is not None:
                    flash(f"Signed in as {account.display_name}.", "success")
                    return redirect(next_url or dashboard_for(account))

    return render_template(
        "auth/login.html", error=error, email=email, next_url=next_url or "",
        auth_configured=settings.SUPABASE_AUTH_ENABLED,
    )


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if auth.current_account() is not None:
        return redirect(dashboard_for(auth.current_account()))

    error = None
    values = {"display_name": "", "email": ""}

    if request.method == "POST":
        values["display_name"] = (request.form.get("display_name") or "").strip()[:120]
        values["email"] = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        # Any role field a client tries to send is ignored on purpose.
        if request.form.get("role"):
            log.warning("ignored client-supplied role on signup: %r", request.form.get("role"))

        if not values["display_name"]:
            error = "Enter your full name."
        elif not EMAIL_RE.match(values["email"]):
            error = "Enter a valid email address."
        elif not email_domain_allowed(values["email"]):
            error = "Sign up with your college email address."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"Use a password of at least {MIN_PASSWORD_LENGTH} characters."
        elif password != confirm:
            error = "The two passwords do not match."
        else:
            try:
                payload = get_auth().sign_up(
                    values["email"], password, values["display_name"],
                    email_redirect_to=_app_url("/auth/confirm"),
                )
            except AuthError as exc:
                error = exc.message
            else:
                user = (payload or {}).get("user") or {}
                if payload.get("session") and user.get("id"):
                    # Email confirmation is disabled: the session is already usable.
                    result = get_auth().sign_in_with_password(values["email"], password)
                    account = ensure_profile(result.user_id, result.email,
                                             values["display_name"])
                    auth.sign_in(account, result.refresh_token)
                    bootstrap_signup(account.user_id)
                    account = auth.reload_account()
                    flash("Your account is ready.", "success")
                    return redirect(dashboard_for(account))
                elif user.get("id"):
                    # Create the profile now (the auth trigger normally does it)
                    # and promote the very first account so the deployment can
                    # be administered. Later signups always stay students.
                    new_user = ensure_profile(
                        str(user["id"]), values["email"], values["display_name"])
                    bootstrap_signup(new_user.user_id)
                    flash(
                        "Check your email for the confirmation link, then sign in.",
                        "success",
                    )
                    return redirect(url_for("auth.login"))
                else:
                    error = (
                        "If this email can be used, a confirmation message has "
                        "been sent. Check your inbox and sign in."
                    )
                    flash(error, "info")
                    return redirect(url_for("auth.login"))

    return render_template(
        "auth/signup.html", error=error, values=values,
        auth_configured=settings.SUPABASE_AUTH_ENABLED,
        min_password=MIN_PASSWORD_LENGTH,
    )


@bp.route("/logout", methods=["POST"])
@auth.login_required
def logout():
    token = auth.access_token_for_supabase()
    if token:
        get_auth().sign_out(token)
    user_id = g.account.user_id if g.account else ""
    auth.sign_out()
    log.info("sign-out user=%s", user_id)
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    sent = False
    error = None
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not EMAIL_RE.match(email):
            error = "Enter a valid email address."
        else:
            try:
                get_auth().send_password_reset(email, _app_url("/auth/confirm"))
            except AuthError as exc:
                error = exc.message
            else:
                sent = True
    return render_template("auth/forgot_password.html", sent=sent, error=error,
                           email=email, auth_configured=settings.SUPABASE_AUTH_ENABLED)


@bp.route("/confirm", methods=["GET"])
def confirm():
    """Handle Supabase email links (confirmation, recovery, invite).

    Supports both link styles that can be configured in Supabase's email
    templates:

    * ``?token_hash=...&type=recovery|email|invite`` (server-side PKCE flow)
    * ``?code=...`` (authorization-code flow)
    """
    auth.sign_out()
    token_hash = request.args.get("token_hash")
    code = request.args.get("code")
    token_type = request.args.get("type", "email")
    error = request.args.get("error_description")

    if error:
        flash("That link is no longer valid. Request a new one.", "danger")
        return redirect(url_for("auth.login"))

    if token_hash:
        try:
            result = get_auth().verify_token_hash(token_hash, token_type)
        except AuthError as exc:
            flash(exc.message, "danger")
            return redirect(url_for("auth.forgot_password"))
    elif code:
        try:
            result = get_auth().exchange_code(code)
        except AuthError as exc:
            flash(exc.message, "danger")
            return redirect(url_for("auth.login"))
    else:
        flash("This link is incomplete or has expired. Request a new one.", "danger")
        return redirect(url_for("auth.login"))

    if token_type == "recovery":
        if not result.access_token:
            flash("That reset link has expired. Request a new one.", "danger")
            return redirect(url_for("auth.forgot_password"))
        # The recovery token travels in the query string for exactly one hop,
        # then the reset page stores it in the session and redirects to a URL
        # without it, so it never lands in a history entry or a Referer header.
        session["recovery_token"] = result.access_token
        session["recovery_started_at"] = int(time.time())
        return redirect(url_for("auth.reset_password"))

    account = _finish_sign_in(result)
    if account is None:
        return redirect(url_for("auth.login"))
    flash("Your email address is confirmed.", "success")
    return redirect(dashboard_for(account))


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Choose a new password after the recovery link was verified."""
    token = session.get("recovery_token", "")
    started = session.get("recovery_started_at", 0)
    if (not token or time.time() - started > RECOVERY_WINDOW_SECONDS):
        session.pop("recovery_token", None)
        session.pop("recovery_started_at", None)
        flash("Open the reset link from your email again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    error = None
    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        if len(password) < MIN_PASSWORD_LENGTH:
            error = f"Use a password of at least {MIN_PASSWORD_LENGTH} characters."
        elif password != confirm:
            error = "The two passwords do not match."
        else:
            try:
                get_auth().update_password(token, password)
            except AuthError as exc:
                error = exc.message
            else:
                session.pop("recovery_token", None)
                session.pop("recovery_started_at", None)
                flash("Your password has been changed. Sign in with the new password.", "success")
                return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", error=error,
                           min_password=MIN_PASSWORD_LENGTH)


@bp.route("/no-account")
@auth.login_required
def no_account():
    """Signed in, but no academic record is linked to this login yet."""
    return render_template("auth/no_account.html")
