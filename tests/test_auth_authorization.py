"""Authentication and authorization across the Flask application.

Covers the task's checklist:

* signup creates a student profile, login/logout, password reset, invalid
  credentials, and the impossibility of choosing faculty/admin at signup;
* students cannot reach faculty routes, other students' records, or modify
  attendance/marks; faculty cannot reach classes they do not own; admin-only
  pages reject faculty and students; anonymous visitors cannot open protected
  pages.

Everything runs offline: SQLite in a temporary file plus the fake Supabase
Auth defined in ``tests/support.py``.

Request pattern: every state-changing form is submitted the way a browser
submits it - load the page that renders the form (which stores a CSRF token),
then POST that token back.
"""

import unittest
from unittest.mock import patch

import os

from tests.support import FakeAuthState, TempDatabaseMixin

from app.supabase_client import AuthError


class AppTestBase(TempDatabaseMixin):
    """Temporary database, offline Supabase Auth and a Flask test client."""

    def setUp(self):
        super().setUp()
        import wsgi
        import app.auth as auth_module
        import app.views.auth_views as auth_views

        self.fake = FakeAuthState.current
        self.original_load_account = auth_module.load_account

        def fake_load_account(user_id, email="", display_name=""):
            # The deployed project's auth.users trigger creates the profile row;
            # SQLite tests have no such trigger, so mirror the real semantics:
            # the role comes only from user_profiles, and a missing row means a
            # plain student with no linked record.
            from contextlib import closing

            from app.accounts import Account, safe_role

            with closing(self.connect()) as connection:
                row = connection.execute(
                    "SELECT email, display_name, role FROM user_profiles WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                student = connection.execute(
                    "SELECT student_id FROM students WHERE auth_user_id = ?", (user_id,)
                ).fetchone()
                teacher = connection.execute(
                    "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
                ).fetchone()
            login_email = row["email"] if row and row["email"] else email
            return Account(
                user_id=user_id,
                email=login_email or "",
                display_name=((row["display_name"] if row else "")
                              or display_name or "User"),
                role=safe_role(row["role"] if row else "student"),
                student_id=student["student_id"] if student else None,
                teacher_id=teacher["teacher_id"] if teacher else None,
            )

        auth_module.load_account = fake_load_account
        auth_views.load_account = fake_load_account

        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()

    def tearDown(self):
        import app.auth as auth_module
        import app.views.auth_views as auth_views

        auth_module.load_account = self.original_load_account
        auth_views.load_account = self.original_load_account
        super().tearDown()

    # -- database helpers ------------------------------------------------
    def connect(self):
        from db import get_connection

        return get_connection()

    def make_profile(self, email, role="student", password="secret-pass-1",
                     display_name=None):
        user_id = self.fake.add_user(email, password, display_name=display_name)
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO user_profiles (user_id, email, display_name, role)
                   VALUES (?, ?, ?, ?)""",
                (user_id, email, display_name or email.split("@")[0], role),
            )
            connection.commit()
        return user_id

    def make_student(self, email, name, class_id=None, role="student",
                     password="secret-pass-1"):
        user_id = self.make_profile(email, role=role, password=password)
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO students (name, email, auth_user_id, class_id)
                   VALUES (?, ?, ?, ?)""",
                (name, email, user_id, class_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT student_id FROM students WHERE email = ?", (email,)
            ).fetchone()
        return user_id, row["student_id"]

    def make_teacher(self, email, name="Teacher"):
        user_id = self.make_profile(email, role="faculty")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO teachers (auth_user_id, name, email) VALUES (?, ?, ?)",
                (user_id, name, email),
            )
            connection.commit()
            row = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
            ).fetchone()
        return user_id, row["teacher_id"]

    def make_class(self, name, owner_teacher_id):
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section, description,
                        owner_teacher_id)
                   VALUES (?, 'BCA AI & DS', 3, 'A', '', ?)""",
                (name, owner_teacher_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT class_id FROM faculty_classes WHERE class_name = ?", (name,)
            ).fetchone()
        return row["class_id"]

    def seed_subject(self, name="Operating Systems"):
        with self.connect() as connection:
            connection.execute("INSERT INTO subjects (subject_name) VALUES (?)", (name,))
            connection.commit()
            row = connection.execute(
                "SELECT subject_id FROM subjects WHERE subject_name = ?", (name,)
            ).fetchone()
        return row["subject_id"]

    def set_role(self, email, role):
        with self.connect() as connection:
            connection.execute(
                "UPDATE user_profiles SET role = ? WHERE email = ?", (role, email))
            connection.commit()

    # -- HTTP helpers ----------------------------------------------------
    def csrf(self):
        with self.client.session_transaction() as session:
            return session.get("csrf_token")

    def submit(self, path, data, page=None, visible=False):
        """Render the form page, then POST with the token it stored."""
        with self.client.session_transaction() as session:
            last_account = session.get("account")
        self.client.get(page or path)
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
            # Loading the page may sign the visitor in/out; keep the identity.
            if last_account is not None and "account" not in session:
                session["account"] = last_account
        payload = dict(data)
        if token:
            payload["csrf_token"] = token
        return self.client.post(path, data=payload, follow_redirects=visible)

    def sign_in(self, email, password="secret-pass-1"):
        """Sign in on this client (renders the form, then POSTs it)."""
        return self.submit("/auth/login", {"email": email, "password": password})

    def as_user(self, email, password="secret-pass-1"):
        """Start a fresh browser (no cookies) and sign in as ``email``."""
        self.client = self.app.test_client()
        response = self.sign_in(email, password)
        if response.status_code not in (301, 302, 303):
            raise AssertionError(f"sign-in failed for {email}: {response.status_code}")
        return self.client


class TestAuthentication(AppTestBase, unittest.TestCase):
    def test_login_page_is_public(self):
        response = self.client.get("/auth/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign in", response.data)

    def test_anonymous_cannot_open_protected_pages(self):
        for path in ("/student/dashboard", "/attendance", "/classrooms",
                     "/study-planner", "/faculty/dashboard", "/faculty/manage",
                     "/faculty/classes", "/faculty/admin/users"):
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertIn(response.status_code, (301, 302, 303), path)

    def test_login_redirects_each_role_to_its_dashboard(self):
        self.make_student("student@example.com", "Student One")
        self.make_teacher("faculty@example.com")

        response = self.sign_in("student@example.com")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/student/dashboard"))

        self.client = self.app.test_client()
        response = self.sign_in("faculty@example.com")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/faculty/dashboard"))

    def test_invalid_credentials_are_rejected(self):
        self.make_student("student@example.com", "Student One")
        response = self.sign_in("student@example.com", password="wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Incorrect email or password", response.data)
        with self.client.session_transaction() as session:
            self.assertNotIn("account", session)

    def test_logout_clears_session_and_revokes_tokens(self):
        self.make_student("student@example.com", "Student One")
        self.as_user("student@example.com")
        response = self.submit("/auth/logout", {})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("account", session)
            self.assertNotIn("sb_refresh_token", session)
        self.assertEqual(self.client.get("/student/dashboard").status_code, 302)

    def test_signup_creates_a_student_and_ignores_client_role(self):
        # An existing profile means the deployment is already administered.
        self.make_profile("admin@example.com", role="admin")
        response = self.submit("/auth/signup", {
            "display_name": "New Person",
            "email": "new@example.com",
            "password": "long-enough-pass",
            "confirm_password": "long-enough-pass",
            "role": "faculty",          # must be ignored
        })
        self.assertEqual(response.status_code, 302)
        with self.connect() as connection:
            profile = connection.execute(
                "SELECT role FROM user_profiles WHERE email = ?", ("new@example.com",)
            ).fetchone()
        self.assertEqual(profile["role"], "student")

    def test_public_signup_never_grants_admin(self):
        """Registering first must not confer admin: that was the old behaviour."""
        response = self.submit("/auth/signup", {
            "display_name": "First Visitor", "email": "owner@example.com",
            "password": "long-enough-pass",
            "confirm_password": "long-enough-pass",
        })
        self.assertEqual(response.status_code, 302)
        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE email = 'owner@example.com'"
            ).fetchone()["role"]
        self.assertEqual(role, "student")

        self.client = self.app.test_client()
        self.submit("/auth/signup", {
            "display_name": "Second", "email": "second@example.com",
            "password": "long-enough-pass",
            "confirm_password": "long-enough-pass",
        })
        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE email = 'second@example.com'"
            ).fetchone()["role"]
        self.assertEqual(role, "student")

    def test_bootstrap_code_is_required_and_single_use(self):
        """Only the operator-issued code promotes, and only once."""
        import hashlib

        from app import accounts
        from db import get_connection

        # Exactly one profile: the state a fresh deployment is in.
        user_id = self.make_profile("owner@example.com", role="student")
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE admin_bootstrap (id INTEGER PRIMARY KEY, code_hash TEXT, "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP, claimed_at TEXT, claimed_by TEXT)"
            )
            connection.commit()

        code = "operator-issued-code"
        digest = hashlib.sha256(code.encode()).hexdigest()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO admin_bootstrap (id, code_hash) VALUES (1, ?)", (digest,))
            connection.commit()

        # A wrong code changes nothing.
        self.assertFalse(accounts.bootstrap_signup(user_id, "wrong-code"))
        # No code at all changes nothing (public registration alone is a no-op).
        self.assertFalse(accounts.bootstrap_signup(user_id, None))

        conn = get_connection()
        try:
            self.assertEqual(accounts.count_profiles_connection(conn), 1)
            self.assertTrue(accounts.claim_bootstrap(conn, user_id, code))
            conn.commit()
            # The same code cannot be replayed.
            self.assertFalse(accounts.claim_bootstrap(conn, user_id, code))
        finally:
            conn.close()

        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()["role"]
        self.assertEqual(role, "admin")

    def test_signup_rejects_weak_or_mismatched_passwords(self):
        for data in (
            {"password": "short", "confirm_password": "short"},
            {"password": "long-enough-pass", "confirm_password": "different-pass"},
        ):
            with self.subTest(data=data):
                response = self.submit("/auth/signup", {
                    "display_name": "New Person", "email": "weak@example.com", **data,
                })
                self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.fake.users.get("weak@example.com"))

    def test_password_reset_flow(self):
        self.make_student("student@example.com", "Student One")

        response = self.submit("/auth/forgot-password",
                               {"email": "student@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"reset email", response.data)
        self.assertTrue(any(call[0] == "recover" for call in self.fake.calls))

        # Unknown addresses get the same answer: no account enumeration.
        response = self.submit("/auth/forgot-password",
                               {"email": "nobody-here@example.com"})
        self.assertIn(b"reset email", response.data)

        # The emailed link verifies the token, then asks for a new password.
        response = self.client.get(
            "/auth/confirm?token_hash=valid-recovery&type=recovery")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/auth/reset-password"))
        self.assertEqual(self.client.get("/auth/reset-password").status_code, 200)

        response = self.submit("/auth/reset-password", {
            "password": "brand-new-pass", "confirm_password": "brand-new-pass"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(("update_password", "recovery-access"), self.fake.calls)

        # The form cannot be reused: the verified token is consumed.
        response = self.client.get("/auth/reset-password", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/forgot-password", response.headers["Location"])

    def test_expired_recovery_link_is_refused(self):
        response = self.client.get("/auth/confirm?token_hash=stale&type=recovery")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/auth/reset-password", response.headers["Location"])

    def test_login_failure_from_supabase_is_shown(self):
        self.fake.fail_with = AuthError("Confirm your email address before signing in.")
        response = self.submit("/auth/login",
                               {"email": "pending@example.com",
                                "password": "whatever-1"})
        self.assertIn(b"Confirm your email address", response.data)

    def test_csrf_token_is_required(self):
        response = self.client.post("/auth/login",
                                    data={"email": "a@b.com", "password": "x"})
        self.assertEqual(response.status_code, 400)

    def test_security_headers_are_sent(self):
        response = self.client.get("/auth/login")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'",
                      response.headers["Content-Security-Policy"])
        self.assertIn("HttpOnly", response.headers.get("Set-Cookie", ""))

    def test_forged_supabase_cookie_creates_no_session(self):
        self.client.set_cookie("sb-access-token", "forged")
        response = self.client.get("/student/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["Location"])

    def test_session_dies_when_supabase_rejects_the_refresh(self):
        self.make_student("student@example.com", "Student One")
        self.as_user("student@example.com")
        self.fake.revoke_all()           # revoked server-side (sign-out everywhere)
        from app import auth as auth_module

        # Supabase configured, and the refresh window has elapsed.
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co",
                                     "SUPABASE_PUBLISHABLE_KEY": "test-key"}), \
                patch.object(auth_module, "REFRESH_INTERVAL_SECONDS", 0):
            response = self.client.get("/student/dashboard")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("account", session)

    def test_refreshed_token_keeps_the_session_alive(self):
        self.make_student("student@example.com", "Student One")
        self.as_user("student@example.com")
        from app import auth as auth_module

        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co",
                                     "SUPABASE_PUBLISHABLE_KEY": "test-key"}), \
                patch.object(auth_module, "REFRESH_INTERVAL_SECONDS", 0):
            response = self.client.get("/student/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(call[0] == "sign_in" for call in self.fake.calls))


class TestStudentRestrictions(AppTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        _, self.teacher_id = self.make_teacher("faculty@example.com")
        self.class_id = self.make_class("Class A", self.teacher_id)
        _, self.alice_id = self.make_student("alice@example.com", "Alice", self.class_id)
        _, self.bob_id = self.make_student("bob@example.com", "Bob", self.class_id)
        self.subject_id = self.seed_subject()

    def test_student_dashboard_shows_only_own_records(self):
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO attendance (student_id, subject_id, total_classes,
                                           attended_classes) VALUES (?, ?, 10, 9)""",
                (self.alice_id, self.subject_id),
            )
            connection.commit()
        self.as_user("bob@example.com")
        response = self.client.get("/student/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"bob", response.data)
        self.assertNotIn(b"Alice", response.data)

    def test_student_cannot_open_faculty_pages(self):
        self.as_user("alice@example.com")
        for path in ("/faculty/dashboard", "/faculty/manage", "/faculty/classes",
                     "/faculty/admin/users"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_student_cannot_modify_attendance_or_marks(self):
        self.as_user("alice@example.com")
        response = self.submit("/faculty/manage", {
            "action": "save_attendance", "student_id": str(self.alice_id),
            "subject_id": str(self.subject_id),
            "total_classes": "10", "attended_classes": "5",
        }, page="/student/dashboard")
        self.assertEqual(response.status_code, 403)
        with self.connect() as connection:
            self.assertIsNone(connection.execute(
                "SELECT 1 AS found FROM attendance").fetchone())

    def test_ownership_guard_rejects_a_foreign_student_id(self):
        from werkzeug.exceptions import Forbidden

        from app.accounts import Account
        import app.auth as auth_module

        bob = Account("u", "b@x", "Bob", "student", student_id=self.bob_id)
        with self.app.test_request_context("/"):
            with patch.object(auth_module, "current_account", return_value=bob):
                with self.assertRaises(Forbidden):
                    auth_module.require_own_student(self.alice_id)
                auth_module.require_own_student(self.bob_id)


class TestFacultyRestrictions(AppTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.teacher_email = "faculty@example.com"
        _, self.teacher_id = self.make_teacher(self.teacher_email, "Faculty One")
        _, self.other_teacher_id = self.make_teacher("other@example.com", "Faculty Two")
        self.own_class = self.make_class("Own Class", self.teacher_id)
        self.other_class = self.make_class("Other Class", self.other_teacher_id)
        _, self.own_student = self.make_student("own@example.com", "Own Student",
                                                self.own_class)
        _, self.other_student = self.make_student("other@example.com",
                                                  "Other Student", self.other_class)
        self.subject_id = self.seed_subject()

    def test_faculty_dashboard_shows_owned_classes_only(self):
        self.as_user(self.teacher_email)
        response = self.client.get("/faculty/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Own Student", response.data)
        self.assertNotIn(b"Other Student", response.data)

    def test_faculty_cannot_open_another_class(self):
        self.as_user(self.teacher_email)
        self.assertEqual(
            self.client.get(f"/faculty/dashboard?class_id={self.other_class}").status_code,
            403)
        self.assertEqual(
            self.client.get(f"/faculty/classes?class_id={self.other_class}").status_code,
            403)

    def test_faculty_cannot_write_to_another_classes_student(self):
        self.as_user(self.teacher_email)
        response = self.submit("/faculty/manage", {
            "action": "save_marks", "student_id": str(self.other_student),
            "subject_id": str(self.subject_id), "exam_name": "Midterm",
            "marks_obtained": "90", "max_marks": "100",
        })
        self.assertEqual(response.status_code, 403)
        with self.connect() as connection:
            self.assertIsNone(connection.execute(
                "SELECT 1 AS found FROM marks").fetchone())

        response = self.submit("/faculty/manage", {
            "action": "save_attendance", "student_id": str(self.own_student),
            "subject_id": str(self.subject_id),
            "total_classes": "10", "attended_classes": "8",
        })
        self.assertEqual(response.status_code, 302)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT attended_classes FROM attendance WHERE student_id = ?",
                (self.own_student,)).fetchone()
        self.assertEqual(row["attended_classes"], 8)

    def test_faculty_cannot_promote_themselves(self):
        self.as_user(self.teacher_email)
        response = self.submit("/faculty/admin/set-role",
                               {"email": self.teacher_email, "role": "admin"},
                               page="/faculty/admin/users")
        self.assertEqual(response.status_code, 403)
        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE email = ?",
                (self.teacher_email,)).fetchone()["role"]
        self.assertEqual(role, "faculty")

    def test_new_class_is_owned_by_its_creator(self):
        self.as_user(self.teacher_email)
        response = self.submit("/faculty/classes", {
            "action": "create_class", "class_name": "Created By Faculty",
            "program": "BCA AI & DS", "semester": "3", "section": "B",
            "description": "",
        })
        self.assertEqual(response.status_code, 302)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT owner_teacher_id FROM faculty_classes WHERE class_name = ?",
                ("Created By Faculty",)).fetchone()
        self.assertEqual(row["owner_teacher_id"], self.teacher_id)


class TestAdminOnly(AppTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.admin_user, _ = self.make_student("admin@example.com", "Admin Person")
        self.set_role("admin@example.com", "admin")
        self.student_user, _ = self.make_student("student@example.com",
                                                 "Student Person")

    def test_admin_can_open_admin_page(self):
        self.as_user("admin@example.com")
        self.assertEqual(self.client.get("/faculty/admin/users").status_code, 200)

    def test_student_is_denied_admin_page(self):
        self.as_user("student@example.com")
        self.assertEqual(self.client.get("/faculty/admin/users").status_code, 403)
        response = self.submit("/faculty/admin/set-role",
                               {"email": "student@example.com", "role": "faculty"})
        self.assertEqual(response.status_code, 403)

    def test_admin_can_grant_faculty_and_creates_teacher_row(self):
        self.as_user("admin@example.com")
        response = self.submit("/faculty/admin/set-role",
                               {"email": "student@example.com", "role": "faculty"},
                               page="/faculty/admin/users")
        self.assertEqual(response.status_code, 302)
        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE email = 'student@example.com'"
            ).fetchone()["role"]
            teacher = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?",
                (self.student_user,)).fetchone()
        self.assertEqual(role, "faculty")
        self.assertIsNotNone(teacher)

    def test_admin_cannot_change_own_role(self):
        self.as_user("admin@example.com")
        self.submit("/faculty/admin/set-role",
                    {"email": "admin@example.com", "role": "student"},
                    page="/faculty/admin/users")
        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE email = 'admin@example.com'"
            ).fetchone()["role"]
        self.assertEqual(role, "admin")


class TestExistingToolsStillWork(AppTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.make_student("student@example.com", "Student One")

    def test_attendance_calculator(self):
        self.as_user("student@example.com")
        response = self.submit("/attendance", {
            "attended": "30", "total": "40", "upcoming": "12", "target": "75"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"75", response.data)

    def test_study_planner_uses_the_c_core(self):
        self.as_user("student@example.com")
        response = self.submit("/study-planner", {
            "available_minutes": "120",
            "topic_name": ["Recursion", "Graphs"],
            "mastery_pct": ["25", "10"],
            "estimated_minutes": ["60", "90"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Graphs", response.data)

    def test_classroom_finder_and_healthz(self):
        self.as_user("student@example.com")
        response = self.submit("/classrooms",
                               {"day": "1", "start": "10:00", "end": "11:00"})
        self.assertEqual(response.status_code, 200)
        health = self.client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["c_core"], "ok")

    def test_home_redirects_signed_in_users(self):
        self.as_user("student@example.com")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/student/dashboard"))


if __name__ == "__main__":
    unittest.main()
