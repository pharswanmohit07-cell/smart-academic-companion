"""
Server-side Supabase Auth client.

Credentials come from the environment only (see :mod:`config`):

* ``SUPABASE_URL`` and ``SUPABASE_PUBLISHABLE_KEY`` (the anon key) are used for
  password sign-in, sign-up, password recovery and token refresh. The anon key
  is public by design and protected by Auth settings plus RLS.
* ``SUPABASE_SECRET_KEY`` (the service-role key) is read only here, only on the
  server, and only for the one operation that genuinely needs it. It is never
  written to a page, a cookie or a log line.

Requests go to the GoTrue REST API (``/auth/v1/...``) with the standard
library, so there is no dependency on a third-party client.

Session rule: a Supabase session is only ever taken from the response body of
a request that carried the password or token, never from cookies.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from config import settings

log = logging.getLogger(__name__)


class AuthError(Exception):
    """A Supabase Auth call failed. ``message`` is safe to show to the user."""

    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code

    def __str__(self):
        return self.message


class AuthNotConfigured(AuthError):
    """Supabase credentials are missing from the environment."""


@dataclass
class AuthResult:
    """Normalised result of a sign-in / refresh / verify call."""

    access_token: str = ""
    refresh_token: str = ""
    expires_in: int = 0
    user_id: str = ""
    email: str = ""
    user_metadata: dict = field(default_factory=dict)

    @property
    def display_name(self):
        metadata = self.user_metadata or {}
        for key in ("display_name", "full_name", "name"):
            if metadata.get(key):
                return str(metadata[key]).strip()[:120]
        return ""


# GoTrue error codes mapped to messages that reveal no more than Supabase does.
_ERROR_MESSAGES = {
    "invalid_credentials": "Incorrect email or password.",
    "invalid_grant": "Incorrect email or password.",
    "email_not_confirmed": "Confirm your email address before signing in.",
    "user_already_exists": "An account with this email already exists.",
    "email_exists": "An account with this email already exists.",
    "signup_disabled": "New sign-ups are disabled.",
    "over_email_send_rate_limit": "Too many emails were sent. Try again later.",
    "over_request_rate_limit": "Too many attempts. Try again in a few minutes.",
    "weak_password": "Choose a stronger password (at least 8 characters).",
    "same_password": "The new password must be different from the current one.",
    "otp_expired": "That link has expired. Request a new one.",
    "token_expired": "That link has expired. Request a new one.",
    "user_not_found": "That account could not be found.",
    "validation_failed": "Please check the details you entered.",
    "flow_state_not_found": "That link has expired. Request a new one.",
    "flow_state_expired": "That link has expired. Request a new one.",
    "bad_code_verifier": "That link was opened in a different browser. Request a new one.",
}

_GENERIC = "The authentication service rejected the request."


class SupabaseAuth:
    """Minimal GoTrue client with the endpoints this application needs."""

    def __init__(self, url=None, publishable_key=None, secret_key=None, timeout=10):
        self.url = (url if url is not None else settings.SUPABASE_URL).rstrip("/")
        self.publishable_key = (publishable_key if publishable_key is not None
                                else settings.SUPABASE_PUBLISHABLE_KEY)
        self.secret_key = (secret_key if secret_key is not None
                           else settings.SUPABASE_SECRET_KEY)
        self.timeout = timeout
        # A cookie jar is never used: state arrives in response bodies only.
        self._opener = urllib.request.build_opener()

    # -- configuration ---------------------------------------------------
    @property
    def is_configured(self):
        return bool(self.url and self.publishable_key)

    def _require_configuration(self):
        if not self.is_configured:
            raise AuthNotConfigured(
                "Authentication is not configured on this server. "
                "Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY."
            )

    def _key(self, service_role=False):
        if service_role:
            if not self.secret_key:
                raise AuthNotConfigured(
                    "This operation needs SUPABASE_SECRET_KEY (service role). "
                    "It is read on the server only."
                )
            return self.secret_key
        return self.publishable_key

    # -- transport -------------------------------------------------------
    def _request(self, method, path, body=None, service_role=False,
                 access_token=None, extra_headers=None):
        self._require_configuration()
        url = f"{self.url}/auth/v1{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "apikey": self._key(service_role),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        token = access_token or self._key(service_role)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.update(extra_headers or {})

        request = urllib.request.Request(url, data=data, headers=headers,
                                         method=method)
        # The URL is logged without credentials, headers or body.
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            log.info("supabase auth %s %s -> %s", method, path, exc.code)
            raise _http_error(exc.code, raw) from None
        except urllib.error.URLError as exc:
            log.warning("supabase auth unreachable: %s", exc.reason)
            raise AuthError(
                "The authentication service is unreachable. Try again shortly.",
                status=503,
            ) from exc
        except (ValueError, TimeoutError):
            log.warning("supabase auth returned an unreadable response")
            raise AuthError(
                "The authentication service did not answer correctly.",
                status=502,
            ) from None

    # -- endpoints -------------------------------------------------------
    def sign_in_with_password(self, email, password):
        self._require_configuration()
        payload = self._request(
            "POST", "/token?grant_type=password",
            {"email": email, "password": password},
        )
        return _to_result(payload)

    def sign_up(self, email, password, display_name=None, email_redirect_to=None):
        """Create an account. The role is never taken from the client.

        The trigger on ``auth.users`` creates the ``user_profiles`` row with the
        default ``student`` role. ``data`` is display-only metadata for Supabase
        and is never used for authorization.
        """
        self._require_configuration()
        body = {
            "email": email,
            "password": password,
            "data": {"display_name": (display_name or email.split("@")[0])[:120]},
        }
        if email_redirect_to:
            body["options"] = {"email_redirect_to": email_redirect_to}
        return self._request("POST", "/signup", body)

    def refresh(self, refresh_token):
        self._require_configuration()
        payload = self._request(
            "POST", "/token?grant_type=refresh_token",
            {"refresh_token": refresh_token},
        )
        result = _to_result(payload)
        if not result.refresh_token:
            result.refresh_token = refresh_token
        return result

    def sign_out(self, access_token):
        """Revoke the session server-side (best effort)."""
        if not access_token:
            return
        try:
            self._request("POST", "/logout", {}, access_token=access_token)
        except AuthError:
            # An expired or already revoked token is useless anyway; the
            # caller clears the local session regardless.
            return

    def get_user(self, access_token):
        """Validate an access token with Supabase (``GET /user``)."""
        payload = self._request("GET", "/user", access_token=access_token)
        user_id = payload.get("id")
        if not user_id:
            raise AuthError("That session is no longer valid.", status=401)
        return {
            "id": str(user_id),
            "email": payload.get("email", "") or "",
            "user_metadata": payload.get("user_metadata") or {},
        }

    def send_password_reset(self, email, redirect_to):
        """Email a recovery link. Never reveals whether the account exists.

        The redirect is sent both as the ``redirect_to`` query parameter (used
        by the implicit flow, where the link lands on ``/auth/confirm#...``)
        and as the ``Redirect-To`` header used by server-side flows.
        """
        self._require_configuration()
        path = f"/recover?redirect_to={urllib.parse.quote(redirect_to, safe='')}"
        try:
            self._request("POST", path, {"email": email},
                          extra_headers={"Redirect-To": redirect_to})
        except AuthError as exc:
            if exc.status and exc.status >= 500:
                raise
            return

    def update_password(self, access_token, password):
        """Set a new password for the signed-in (recovery) user."""
        self._request("PUT", "/user", {"password": password},
                      access_token=access_token)

    def verify_token_hash(self, token_hash, token_type):
        """Exchange an email token hash (server-side flow) for a session."""
        self._require_configuration()
        payload = self._request(
            "POST", "/verify", {"type": token_type, "token_hash": token_hash}
        )
        return _to_result(payload)

    def exchange_code(self, code, code_verifier=None):
        """Exchange a PKCE authorization code for a session."""
        self._require_configuration()
        body = {"auth_code": code}
        if code_verifier:
            body["code_verifier"] = code_verifier
        payload = self._request("POST", "/token?grant_type=pkce", body)
        return _to_result(payload)

    def admin_update_user(self, user_id, password=None):
        """Service-role password reset (server-side operator tooling only)."""
        body = {}
        if password is not None:
            body["password"] = password
            body["nonce"] = ""  # bypasses the reauthentication requirement
        return self._request("PUT", f"/admin/users/{user_id}", body,
                             service_role=True)


def _to_result(payload):
    user = payload.get("user") or {}
    result = AuthResult(
        access_token=payload.get("access_token", "") or "",
        refresh_token=payload.get("refresh_token", "") or "",
        expires_in=int(payload.get("expires_in") or 0),
        user_id=str(user.get("id") or ""),
        email=user.get("email", "") or "",
        user_metadata=user.get("user_metadata") or {},
    )
    if not result.user_id and payload.get("id"):
        # /verify answers with the user object itself.
        result.user_id = str(payload.get("id"))
        result.email = payload.get("email", "") or ""
        result.user_metadata = payload.get("user_metadata") or {}
    return result


def _http_error(status, raw_body):
    code, description = None, None
    try:
        payload = json.loads(raw_body) if raw_body else {}
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        code = payload.get("error_code") or payload.get("code")
        description = (payload.get("msg") or payload.get("error_description")
                       or payload.get("message") or payload.get("error"))
        if isinstance(description, dict):
            description = description.get("message")
    if code in _ERROR_MESSAGES:
        return AuthError(_ERROR_MESSAGES[code], status, code)
    if status == 429:
        return AuthError(_ERROR_MESSAGES["over_request_rate_limit"], status, code)
    if status in (400, 401, 403, 422):
        return AuthError(str(description or _GENERIC)[:200], status, code)
    return AuthError("The authentication service is unavailable.", status, code)


def get_auth() -> SupabaseAuth:
    """Return a client bound to the current settings."""
    return SupabaseAuth()
