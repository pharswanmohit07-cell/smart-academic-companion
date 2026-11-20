"""
Application accounts and the trusted role.

Supabase Auth owns credentials; this module owns the trusted application
identity derived from them:

1. ``auth.users.id``      - who the browser proved they are (Supabase session)
2. ``public.user_profiles`` - the role, read here over the server's own database
   connection (never from JWT metadata, which the user can edit)
3. ``students`` / ``teachers`` - the academic record and class ownership

New accounts always receive the ``student`` role from the database trigger on
``auth.users``. Faculty and admin accounts are created by an operator with
``python manage.py provision-faculty|provision-admin``.
"""

from dataclasses import dataclass
from contextlib import closing

from db import get_connection, last_insert_id
from db.base import DatabaseError

ROLES = ("student", "faculty", "admin")
DEFAULT_ROLE = "student"


class AccountError(Exception):
    """A business-rule failure shown to the user."""


@dataclass
class Account:
    user_id: str
    email: str
    display_name: str
    role: str
    student_id: int = None
    teacher_id: int = None

    @property
    def is_student(self):
        return self.role == "student"

    @property
    def is_faculty(self):
        return self.role in ("faculty", "admin")

    @property
    def is_admin(self):
        return self.role == "admin"

    def to_session(self):
        """The subset stored in Flask's cookie session."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role,
            "student_id": self.student_id,
            "teacher_id": self.teacher_id,
        }

    @classmethod
    def from_session(cls, data):
        if not data:
            return None
        role = data.get("role")
        if role not in ROLES:
            # Anything unexpected is treated as the least privileged role.
            role = DEFAULT_ROLE
        return cls(
            user_id=str(data.get("user_id", "")),
            email=data.get("email", "") or "",
            display_name=data.get("display_name", "") or "",
            role=role,
            student_id=data.get("student_id"),
            teacher_id=data.get("teacher_id"),
        )


def safe_role(value):
    """Normalise a stored role; unknown values fall back to 'student'."""
    role = (value or "").strip().lower()
    return role if role in ROLES else DEFAULT_ROLE


def profiles_table(connection):
    """Schema-qualified name of the profiles table for this back end.

    Supabase keeps profiles in ``public.user_profiles``. SQLite has no schema
    namespace, so local development and the offline tests use
    ``user_profiles``.
    """
    if getattr(connection, "backend", "") == "postgresql":
        return "public.user_profiles"
    return "user_profiles"


def load_account(user_id, email="", display_name=""):
    """Read the trusted role and linked records for an authenticated user.

    The role always comes from ``user_profiles``. A missing row (only possible
    before the signup trigger commits) is treated as a student with no linked
    record, so a new account can never inherit a more privileged role.
    """
    with closing(get_connection()) as connection:
        table = profiles_table(connection)
        profile = connection.execute(
            f"SELECT user_id, email, display_name, role "
            f"FROM {table} WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        student = connection.execute(
            "SELECT student_id, name FROM students WHERE auth_user_id = ?",
            (user_id,),
        ).fetchone()

        teacher = connection.execute(
            "SELECT teacher_id, name FROM teachers WHERE auth_user_id = ?",
            (user_id,),
        ).fetchone()

    role = safe_role(profile["role"] if profile else DEFAULT_ROLE)
    resolved_email = (profile["email"] if profile and profile["email"] else email)
    resolved_name = (
        (profile["display_name"] if profile and profile["display_name"] else "")
        or display_name
        or (student["name"] if student else "")
        or (teacher["name"] if teacher else "")
    )
    return Account(
        user_id=str(user_id),
        email=resolved_email or "",
        display_name=resolved_name or (resolved_email.split("@")[0] if resolved_email else "User"),
        role=role,
        student_id=student["student_id"] if student else None,
        teacher_id=teacher["teacher_id"] if teacher else None,
    )


def email_domain_allowed(email):
    from config import settings

    allowed = settings.ALLOWED_EMAIL_DOMAINS
    if not allowed:
        return True
    domain = (email or "").rsplit("@", 1)[-1].lower()
    return domain in allowed


def ensure_student_record(account):
    """Create or link the academic record for a student account.

    A student record is matched on email first (so an operator can prepare
    rows before accounts exist) and then created. ``auth_user_id`` is the
    link every ownership check uses, so it is only written for a row that has
    no owner yet.
    """
    with closing(get_connection()) as connection:
        linked = connection.execute(
            "SELECT student_id FROM students WHERE auth_user_id = ?",
            (account.user_id,),
        ).fetchone()
        if linked:
            return linked["student_id"]

        if account.email:
            existing = connection.execute(
                "SELECT student_id, auth_user_id FROM students "
                "WHERE lower(email) = lower(?) ORDER BY auth_user_id NULLS LAST LIMIT 1",
                (account.email,),
            ).fetchone()
        else:
            existing = None

        if existing and not existing["auth_user_id"]:
            connection.execute(
                "UPDATE students SET auth_user_id = ? WHERE student_id = ?",
                (account.user_id, existing["student_id"]),
            )
            connection.commit()
            return existing["student_id"]

        if existing and existing["auth_user_id"] and existing["auth_user_id"] != account.user_id:
            raise AccountError(
                "This email is already linked to a different academic record. "
                "Ask your faculty or administrator to resolve it."
            )

        # A student record that is not linked to anyone is claimed by this login.
        connection.execute(
            """INSERT INTO students (name, email, auth_user_id)
               VALUES (?, ?, ?)""",
            ((account.display_name or account.email or "student")[0].lower() +
             (account.display_name or account.email or "student")[1:],
             account.email or None, account.user_id),
        )
        connection.commit()
        return last_insert_id(connection, "students", "student_id")


def ensure_profile(user_id, email, display_name=None):
    """Make sure the profile row exists, then return the trusted account.

    The deployed Supabase project creates this row from a trigger on
    ``auth.users``. Should that trigger be missing or still committing, the row
    is created here --- as a student, never with a role supplied by the client.
    """
    with closing(get_connection()) as connection:
        table = profiles_table(connection)
        existing = connection.execute(
            f"SELECT 1 AS found FROM {table} WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing is None:
            try:
                connection.execute(
                    f"""INSERT INTO {table} (user_id, email, display_name, role)
                        VALUES (?, ?, ?, 'student')""",
                    (user_id, email or None, display_name or None),
                )
                connection.commit()
            except IntegrityError:
                # A concurrent request (or the trigger) inserted it first.
                connection.rollback()
        else:
            # The Auth trigger creates a student profile before this request
            # completes. Fill display_name only when the trigger left it blank;
            # never change the role or overwrite a name already set by staff.
            connection.execute(
                f"""UPDATE {table}
                       SET email = COALESCE(?, email),
                           display_name = CASE
                               WHEN COALESCE(display_name, '') = ''
                               THEN COALESCE(?, display_name)
                               ELSE display_name
                           END
                     WHERE user_id = ?""",
                (email or None, display_name or None, user_id),
            )
            connection.commit()
    account = load_account(user_id, email, display_name)
    if account.student_id is None and account.is_student:
        account.student_id = ensure_student_record(account)
        account = load_account(user_id, email, display_name)
    return account


def ensure_teacher_record(account):
    """Return the teacher row for a faculty/admin account, creating it once.

    The row only records *who* owns classes. It never changes the role: roles
    live in ``user_profiles`` and are managed only by trusted actions.
    """
    if not account.is_faculty or not account.email:
        return account.teacher_id
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT teacher_id FROM teachers WHERE auth_user_id = ?",
            (account.user_id,),
        ).fetchone()
        if row:
            return row["teacher_id"]
        connection.execute(
            """INSERT INTO teachers (auth_user_id, name, email)
               VALUES (?, ?, ?) ON CONFLICT (auth_user_id) DO NOTHING""",
            (account.user_id, account.display_name or account.email, account.email),
        )
        connection.commit()
        row = connection.execute(
            "SELECT teacher_id FROM teachers WHERE auth_user_id = ?",
            (account.user_id,),
        ).fetchone()
    return row["teacher_id"] if row else None


def count_profiles():
    with closing(get_connection()) as connection:
        table = profiles_table(connection)
        row = connection.execute(
            f"SELECT COUNT(*) AS total FROM {table}"
        ).fetchone()
    return int(row["total"]) if row else 0


def set_role(email, role):
    """Trusted server-side role change (operator/ admin action only)."""
    role = safe_role(role)
    if role not in ROLES:
        raise AccountError("Unknown role.")
    with closing(get_connection()) as connection:
        table = profiles_table(connection)
        row = connection.execute(
            f"SELECT user_id FROM {table} WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()
        if row is None:
            raise AccountError(f"No profile found for {email}.")
        connection.execute(
            f"UPDATE {table} SET role = ? WHERE user_id = ?",
            (role, row["user_id"]),
        )
        connection.commit()
    return row["user_id"]


BOOTSTRAP_LOCK_ID = 918273645  # arbitrary; serialises the one-time claim


def _ensure_bootstrap_table(connection):
    """Create the one-time bootstrap-token table (PostgreSQL only).

    The table is created lazily so a deployment can be bootstrapped without
    re-running migrations. Nothing is ever deleted; the row records who claimed
    it and when, and a hash of the single-use code.
    """
    connection.execute(
        """CREATE TABLE IF NOT EXISTS admin_bootstrap (
               id            integer PRIMARY KEY CHECK (id = 1),
               code_hash     text NOT NULL,
               created_at    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
               claimed_at    timestamptz,
               claimed_by    uuid
           )"""
    )
    return "admin_bootstrap"


def issue_bootstrap_code():
    """Operator tooling: mint a single-use admin bootstrap code.

    Requires database access (``DATABASE_URL``), which is exactly the trust
    boundary: an anonymous visitor can never mint this. Returns the plaintext
    code once; only its hash is stored.
    """
    import hashlib
    import secrets

    code = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    with closing(get_connection()) as connection:
        if connection.backend != "postgresql":
            raise AccountError(
                "Admin bootstrap codes are issued on PostgreSQL only. "
                "Use `python manage.py provision-admin <email>` for local SQLite."
            )
        _ensure_bootstrap_table(connection)
        # Replacing the row invalidates any code that was issued but not used.
        connection.execute("DELETE FROM admin_bootstrap WHERE id = 1 AND claimed_at IS NULL")
        connection.execute(
            "INSERT INTO admin_bootstrap (id, code_hash) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET code_hash = excluded.code_hash, "
            "created_at = CURRENT_TIMESTAMP, claimed_at = NULL, claimed_by = NULL",
            (digest,),
        )
        connection.commit()
    return code


def bootstrap_open():
    """True while no profile exists AND an operator has issued a code."""
    try:
        with closing(get_connection()) as connection:
            if connection.backend != "postgresql":
                return False
            if count_profiles_connection(connection) != 0:
                return False
            _ensure_bootstrap_table(connection)
            connection.commit()
            row = connection.execute(
                "SELECT 1 AS found FROM admin_bootstrap "
                "WHERE id = 1 AND claimed_at IS NULL"
            ).fetchone()
            return row is not None
    except DatabaseError:
        return False


def count_profiles_connection(connection):
    row = connection.execute(
        f"SELECT COUNT(*) AS total FROM {profiles_table(connection)}"
    ).fetchone()
    return int(row["total"])


def claim_bootstrap(connection, user_id, code):
    """Promote ``user_id`` to admin only with the valid, unclaimed code.

    Runs in one transaction under an advisory lock: the token is compared by
    constant-time hash, marked claimed, and the role set. A wrong code, a used
    code, or an already-populated profile table all return False and change
    nothing.
    """
    import hashlib
    import hmac

    if not code:
        return False
    if connection.backend == "postgresql":
        connection.execute(
            "SELECT pg_advisory_xact_lock(?) AS locked", (BOOTSTRAP_LOCK_ID,)
        )
    if count_profiles_connection(connection) != 1:
        return False
    _ensure_bootstrap_table(connection)
    row = connection.execute(
        "SELECT code_hash FROM admin_bootstrap WHERE id = 1 AND claimed_at IS NULL"
    ).fetchone()
    if row is None:
        return False
    supplied = hashlib.sha256(code.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied, row["code_hash"]):
        return False
    connection.execute(
        "UPDATE admin_bootstrap SET claimed_at = CURRENT_TIMESTAMP, claimed_by = ? "
        "WHERE id = 1",
        (user_id,),
    )
    connection.execute(
        f"UPDATE {profiles_table(connection)} SET role = 'admin' WHERE user_id = ?",
        (user_id,),
    )
    return True


def bootstrap_signup(user_id, code=None):
    """Promote the account only when the operator's bootstrap code matches.

    Public registration alone can never grant a role: without a code this is a
    no-op that returns False.
    """
    if not code:
        return False
    try:
        with closing(get_connection()) as connection:
            promoted = claim_bootstrap(connection, user_id, code)
            connection.commit()
            return promoted
    except DatabaseError:
        return False
