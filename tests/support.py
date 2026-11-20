"""
Shared helpers for the PostgreSQL-era test suite.

The suite never touches the deployed Supabase database and never touches the
developer's ``academic_companion.db``. Each test gets a throw-away SQLite file
(``DATABASE_FILE``), and Supabase Auth is replaced by :class:`FakeAuth`.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FLASK_ENV", "testing")
# The suite never talks to the real Supabase project.
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_PUBLISHABLE_KEY"] = ""
os.environ["SUPABASE_SECRET_KEY"] = ""
os.environ["DATABASE_URL"] = ""

from app.supabase_client import AuthError, AuthResult  # noqa: E402

# ``public.user_profiles`` exists in the deployed Supabase project; the local
# SQLite schema does not create it, so tests create the same shape here.
USER_PROFILES_DDL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id      TEXT PRIMARY KEY,
    email        TEXT,
    display_name TEXT,
    role         TEXT NOT NULL DEFAULT 'student'
                 CHECK (role IN ('student', 'faculty', 'admin')),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class FakeAuth:
    """Stand-in for :class:`app.supabase_client.SupabaseAuth`."""

    def __init__(self):
        self.users = {}          # email -> {"id", "password", "display_name"}
        self.sessions = {}       # refresh token -> user id
        self.revoked = set()     # tokens Supabase has revoked
        self.unavailable = False  # treat every refresh as rejected
        self.calls = []
        self.fail_with = None    # AuthError raised by the next relevant call
        self.issued = 0

    def add_user(self, email, password, user_id=None, display_name=None):
        user_id = user_id or f"00000000-0000-4000-8000-{len(self.users) + 1:012d}"
        self.users[email.lower()] = {
            "id": user_id,
            "password": password,
            "display_name": display_name or email.split("@")[0],
        }
        return user_id

    def _session(self, email):
        user = self.users[email.lower()]
        self.issued += 1
        refresh = f"refresh-{self.issued}"
        self.sessions[refresh] = user["id"]
        return AuthResult(
            access_token=f"access-{self.issued}",
            refresh_token=refresh,
            expires_in=3600,
            user_id=user["id"],
            email=email,
            user_metadata={"display_name": user["display_name"]},
        )

    # -- SupabaseAuth API -----------------------------------------------
    @property
    def is_configured(self):
        return True

    def sign_in_with_password(self, email, password):
        self.calls.append(("sign_in", email))
        if self.fail_with:
            error, self.fail_with = self.fail_with, None
            raise error
        user = self.users.get(email.lower())
        if user is None or user["password"] != password:
            raise AuthError("Incorrect email or password.", 400, "invalid_credentials")
        return self._session(email)

    def sign_up(self, email, password, display_name=None, email_redirect_to=None):
        self.calls.append(("sign_up", email))
        if email.lower() in self.users:
            raise AuthError("An account with this email already exists.", 422,
                            "user_already_exists")
        self.add_user(email, password, display_name=display_name)
        return {"user": {"id": self.users[email.lower()]["id"], "email": email}}

    def refresh(self, refresh_token):
        user_id = self.sessions.get(refresh_token)
        if user_id is None or refresh_token in self.revoked or self.unavailable:
            raise AuthError("Your session has expired.", 401,
                            "refresh_token_not_found")
        for email, user in self.users.items():
            if user["id"] == user_id:
                return AuthResult(access_token="access-refreshed",
                                  refresh_token=refresh_token, user_id=user_id,
                                  email=email)
        raise AuthError("unknown session", 401)

    def revoke_all(self):
        """Simulate a server-side revoke (sign-out everywhere / ban)."""
        self.revoked.update(self.sessions)
        self.sessions.clear()

    def sign_out(self, access_token):
        self.calls.append(("sign_out", access_token))
        self.sessions.clear()

    def get_user(self, access_token):
        raise AuthError("not used in tests", 400)

    def send_password_reset(self, email, redirect_to):
        self.calls.append(("recover", email, redirect_to))

    def update_password(self, access_token, password):
        self.calls.append(("update_password", access_token))

    def verify_token_hash(self, token_hash, token_type):
        self.calls.append(("verify", token_hash, token_type))
        if token_hash == "valid-recovery":
            return AuthResult(access_token="recovery-access",
                              refresh_token="recovery-refresh")
        raise AuthError("That link has expired.", 403, "otp_expired")

    def exchange_code(self, code, code_verifier=None):
        raise AuthError("code flow not used in tests", 400)

    def admin_update_user(self, user_id, password=None):
        self.calls.append(("admin_update_user", user_id))


class FakeAuthState:
    current = None


def install_fake_auth():
    fake = FakeAuth()
    FakeAuthState.current = fake
    return fake


def patch_auth_modules():
    """Route ``get_auth()`` in every application module to the fake.

    ``from ... import get_auth`` creates a module-level name in each importer,
    so each of them is patched (``wsgi`` imports the modules under test, so it
    must be reloaded after this call for the patch to be visible there).
    """
    import app.auth as auth_module
    import app.views.auth_views as auth_views

    def fake_get_auth():
        if FakeAuthState.current is None:
            return install_fake_auth()
        return FakeAuthState.current

    auth_module.get_auth = fake_get_auth
    auth_views.get_auth = fake_get_auth


class TempDatabaseMixin:
    """Point SQLite at a temporary file, create the schema, clean up."""

    def setUp(self):
        super().setUp()
        install_fake_auth()
        patch_auth_modules()

        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        self._old_file = os.environ.get("DATABASE_FILE")
        os.environ["DATABASE_FILE"] = str(self.db_path)

        from database import initialize_database

        initialize_database()
        with self.connect() as connection:
            connection.executescript(USER_PROFILES_DDL)
            connection.commit()

    def tearDown(self):
        if self._old_file is None:
            os.environ.pop("DATABASE_FILE", None)
        else:
            os.environ["DATABASE_FILE"] = self._old_file
        import gc

        # Windows keeps the file open until every connection is collected.
        gc.collect()
        for attempt in range(5):
            try:
                self._tmpdir.cleanup()
                break
            except PermissionError:
                if attempt == 4:
                    break
                gc.collect()
        super().tearDown()

    def connect(self):
        from db import get_connection

        return get_connection()


class TempSqliteTestCase(TempDatabaseMixin, unittest.TestCase):
    """Base class for tests that use the real SQLite schema."""
