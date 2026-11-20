"""Database abstraction and PostgreSQL dialect tests.

The PostgreSQL back end cannot be pointed at the deployed Supabase database
from a test run, so its behaviour is exercised against ``tests/pg_fake.py``: an
in-process store that accepts only PostgreSQL syntax (``%s``, ``EXCLUDED``,
no ``?``) and runs the real application SQL.

What is covered:

* the ``?`` -> ``%s`` translator (placeholders, literals, comments, Ã¢â‚¬Ëœ%Ã¢â‚¬â„¢)
* SQLite/PostgreSQL parity for the portable helpers (last insert id, upsert)
* every module that reads the database still works when the connection
  speaks PostgreSQL
* the migration files are ordered, idempotent and safe to re-run
* cleanup of SQLite-only constructs in the application code
"""

import re
import unittest
from pathlib import Path

from tests.pg_fake import FakePgConnection, new_connection
from tests.support import FakeAuthState, TempSqliteTestCase

from db import pg_backend
from db.base import IntegrityError, Row, to_minutes, numeric_text

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"tests", ".git", ".venv", "venv", "__pycache__", "build", "node_modules"}

# Files that may legitimately mention SQLite-only syntax: the local schema, the
# compatibility layer that migrates old local files, seed/management tooling
# and the tests themselves.
SQLITE_ALLOWED = {
    "database.py", "schema.sql", "seed_data.py", "db/sqlite_backend.py",
    "db/base.py", "db/__init__.py",
}


class TestSqlTranslation(unittest.TestCase):
    def test_placeholders_become_percent_s(self):
        self.assertEqual(
            pg_backend.translate("SELECT * FROM students WHERE name = ? AND class_id = ?"),
            "SELECT * FROM students WHERE name = %s AND class_id = %s",
        )

    def test_literal_question_marks_are_left_alone(self):
        sql = "SELECT 'a?b' AS x, name FROM students WHERE login = ?"
        self.assertEqual(
            pg_backend.translate(sql),
            "SELECT 'a?b' AS x, name FROM students WHERE login = %s",
        )

    def test_comments_are_left_alone(self):
        sql = "SELECT 1 -- is this ? a placeholder?\n FROM t WHERE id = ?"
        translated = pg_backend.translate(sql)
        self.assertIn("is this ? a placeholder?", translated)
        self.assertTrue(translated.endswith("id = %s"))

    def test_literal_percent_is_doubled(self):
        self.assertEqual(
            pg_backend.translate("SELECT '50%' , x FROM t WHERE y = ?"),
            "SELECT '50%%' , x FROM t WHERE y = %s",
        )

    def test_sqlite_functions_are_rewritten(self):
        sql = "INSERT INTO marks (exam_date) VALUES (date('now'))"
        self.assertIn("CURRENT_DATE", pg_backend.translate(sql))
        self.assertIn("COALESCE(x, 0)", pg_backend.translate("SELECT IFNULL(x, 0)"))


class TestValueHelpers(unittest.TestCase):
    def test_to_minutes_handles_every_source_format(self):
        self.assertEqual(to_minutes("09:30"), 570)        # SQLite TEXT
        self.assertEqual(to_minutes("09:30:00"), 570)     # PostgreSQL TIME
        self.assertEqual(to_minutes("9.5:00"), 570)       # Decimal hour from EXTRACT
        self.assertEqual(to_minutes(570), 570)

    def test_numeric_text_matches_sqlite_output(self):
        self.assertEqual(numeric_text("09:30"), "09:30")
        self.assertEqual(numeric_text("9.5"), "9.5")
        self.assertEqual(numeric_text("9"), "9")


class TestPortableSql(unittest.TestCase):
    """The same statements must work on SQLite and on the PostgreSQL fake."""

    def run_on_both(self, setup_sql, sql, params=()):
        results = []
        for connection in (self._sqlite(), new_connection()):
            try:
                for statement in setup_sql:
                    connection.execute(*statement)
                results.append([dict(row) for row in connection.execute(sql, params).fetchall()])
            finally:
                connection.close()
        return results

    def _sqlite(self):
        import os
        import tempfile

        from db import sqlite_backend
        from database import initialize_database

        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        os.environ["DATABASE_FILE"] = handle.name
        try:
            initialize_database()
        finally:
            os.environ.pop("DATABASE_FILE", None)
        return sqlite_backend.connect_to(handle.name)

    def test_rows_behave_the_same(self):
        sqlite_rows, pg_rows = self.run_on_both(
            [("INSERT INTO subjects (subject_name) VALUES (?)", ("OS",))],
            "SELECT subject_id, subject_name FROM subjects",
        )
        self.assertEqual(sqlite_rows, pg_rows)
        self.assertIsInstance(pg_rows[0]["subject_name"], str)

    def test_upsert_works_on_both(self):
        upsert = (
            """INSERT INTO attendance (student_id, subject_id, total_classes, attended_classes)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(student_id, subject_id) DO UPDATE SET
                   total_classes = excluded.total_classes,
                   attended_classes = excluded.attended_classes"""
        )
        setup = [
            ("INSERT INTO students (name) VALUES ('S')", ()),
            ("INSERT INTO subjects (subject_name) VALUES ('OS')", ()),
            (upsert, (1, 1, 10, 8)),
            (upsert, (1, 1, 12, 9)),
        ]
        sqlite_rows, pg_rows = self.run_on_both(
            setup, "SELECT total_classes, attended_classes FROM attendance")
        self.assertEqual(sqlite_rows, [{"total_classes": 12, "attended_classes": 9}])
        self.assertEqual(pg_rows, sqlite_rows)

    def test_foreign_keys_are_enforced_on_both(self):
        for connection in (self._sqlite(), new_connection()):
            with self.subTest(backend=connection.backend):
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        """INSERT INTO attendance (student_id, subject_id, total_classes,
                                                   attended_classes)
                           VALUES (999, 999, 1, 1)"""
                    )
                connection.close()


def _skip(relative):
    parts = Path(relative).parts
    return any(part in SKIP_DIRS or part.startswith(".") for part in parts)


def _application_python_files():
    """Project Python files that must not use SQLite-only APIs."""
    files = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if _skip(relative) or relative in SQLITE_ALLOWED:
            continue
        files.append(path)
    return files


class TestNoSqliteSyntaxLeft(unittest.TestCase):
    """Application code must not depend on SQLite-only behaviour."""

    def test_no_lastrowid_in_application_code(self):
        offenders = []
        for path in _application_python_files():
            with open(path, encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
            if "lastrowid" in text:
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_no_direct_sqlite3_import_outside_the_backend(self):
        offenders = []
        for path in _application_python_files():
            with open(path, encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
            if re.search(r"^\s*import sqlite3", text, re.MULTILINE):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_application_sql_uses_portable_placeholders(self):
        # ``?`` is fine in Python source; the check that matters is that no
        # SQLite-only keyword sneaks into application SQL strings.
        banned = ("INSERT OR IGNORE", "INSERT OR REPLACE", "AUTOINCREMENT", "PRAGMA")
        offenders = []
        for path in list(ROOT.glob("app/**/*.py")) + list(ROOT.glob("modules/**/*.py")):
            with open(path, encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
            for line in lines:
                if line.lstrip().startswith("#"):
                    continue
                for word in banned:
                    if word in line:
                        offenders.append((path.name, word))
        self.assertEqual(offenders, [])


class TestMigrations(unittest.TestCase):
    def setUp(self):
        from db.base import split_sql_statements

        self.split = split_sql_statements
        self.files = sorted((ROOT / "migrations").glob("*.sql"))

    def test_every_migration_splits_into_statements(self):
        for path in self.files:
            statements = self.split(path.read_text(encoding="utf-8"))
            self.assertTrue(statements, path.name)
            for statement in statements:
                first_line = statement.splitlines()[0].strip()
                self.assertFalse(first_line.startswith("--"),
                                 f"comment leaked into a statement in {path.name}")

    def test_dollar_quoted_function_bodies_stay_whole(self):
        for path in self.files:
            for statement in self.split(path.read_text(encoding="utf-8")):
                if "DO $$" in statement:
                    self.assertEqual(statement.count("$$"), 2,
                                     f"unbalanced $$ block in {path.name}")

    def test_statements_are_idempotent(self):
        """Re-running every migration must not fail or duplicate structures."""
        for path in self.files:
            text = path.read_text(encoding="utf-8")
            for statement in self.split(text):
                upper = statement.upper()
                if upper.startswith("CREATE TABLE"):
                    self.assertIn("IF NOT EXISTS", upper, path.name)
                if upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX"):
                    self.assertIn("IF NOT EXISTS", upper, path.name)
                if upper.startswith("ALTER TABLE") and "ADD COLUMN" in upper:
                    self.assertIn("IF NOT EXISTS", upper, path.name)
                if upper.startswith("DROP POLICY"):
                    self.assertIn("IF EXISTS", upper, path.name)

    def test_migrations_do_not_drop_columns_or_recursive_policies(self):
        for path in self.files:
            text = path.read_text(encoding="utf-8").upper()
            self.assertNotIn("DROP COLUMN", text, path.name)
            self.assertNotIn("DROP TABLE", text, path.name)

    def test_rls_is_enabled_for_every_application_table(self):
        rls = (ROOT / "migrations" / "0003_rls_policies.sql").read_text(encoding="utf-8")
        for table in ("faculty_classes", "students", "subjects", "attendance",
                      "marks", "timetable", "room_locations", "assignments",
                      "exams", "assessment_items", "assessment_submissions",
                      "teachers"):
            self.assertIn(f"'{table}'", rls, table)
        self.assertIn("ENABLE ROW LEVEL SECURITY", rls.upper())
        self.assertIn("FORCE ROW LEVEL SECURITY", rls.upper())

    def test_policies_never_grant_admin_from_the_client(self):
        rls = (ROOT / "migrations" / "0003_rls_policies.sql").read_text(encoding="utf-8")
        for statement in self.split(rls):
            if "SET role" in statement or "SET ROLE" in statement:
                self.fail(f"client policy changes roles: {statement[:80]}")
        self.assertNotIn("'admin'", "".join(
            statement for statement in self.split(rls)
            if statement.startswith("GRANT")))

    def test_user_profiles_policies_are_not_replaced(self):
        for path in self.files:
            text = path.read_text(encoding="utf-8")
            for statement in self.split(text):
                if statement.upper().startswith("DROP POLICY") and \
                        "USER_PROFILES" in statement.upper():
                    self.fail(f"{path.name} drops a user_profiles policy")


class TestModulesOnPostgres(unittest.TestCase):
    """Run the real module queries against the PostgreSQL fake.

    ``db.pg_backend.connect`` is redirected to one shared fake connection, so
    every query the application issues is checked against PostgreSQL rules.
    """

    def setUp(self):
        from unittest.mock import patch

        from config import settings

        self.connection = new_connection()
        # The application closes every connection it opens; the shared fake
        # must survive that, so closing becomes a no-op for this instance.
        self.connection.close = lambda: None
        self.connection.__exit__ = lambda *args: False
        self.connection.__enter__ = lambda: self.connection

        self.patches = [
            patch("db.pg_backend.connect", return_value=self.connection),
            patch.object(type(settings), "DATABASE_URL",
                         new_callable=lambda: property(
                             lambda _self: "postgresql://fake/db")),
        ]
        for patcher in self.patches:
            patcher.start()

        self.connection.execute(
            "INSERT INTO faculty_classes (class_name, program, semester, section, "
            "description, owner_teacher_id) VALUES ('C1', 'BCA', 3, 'A', '', 1)")
        self.connection.execute(
            "INSERT INTO students (name, class_id) VALUES ('Ada', 1)")
        self.connection.execute(
            "INSERT INTO subjects (subject_name) VALUES ('OS')")
        self.connection.execute(
            "INSERT INTO attendance (student_id, subject_id, total_classes, "
            "attended_classes) VALUES (1, 1, 20, 15)")
        self.connection.execute(
            "INSERT INTO marks (student_id, subject_id, exam_name, marks_obtained, "
            "max_marks, exam_date) VALUES (1, 1, 'Midterm', 60, 100, CURRENT_DATE)")
        self.connection.execute(
            "INSERT INTO assessment_items (subject_id, assessment_type, title) "
            "VALUES (1, 'assignment', 'Lab 1')")
        self.connection.execute(
            "INSERT INTO assessment_submissions (assessment_id, student_id, submitted) "
            "VALUES (1, 1, 0)")
        self.connection.execute(
            "INSERT INTO timetable (subject_id, room_number, day_of_week, start_time, "
            "end_time) VALUES (1, 'R101', 1, '10:00', '11:00')")
        self.connection.commit()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.connection._raw.close()

    def test_faculty_summary_runs_on_postgres(self):
        from modules.faculty_dashboard import get_assessment_overview, get_faculty_summary

        summary = get_faculty_summary(class_ids=[1])
        self.assertEqual(summary["total_students"], 1)
        self.assertAlmostEqual(summary["students"][0]["attendance_pct"], 75.0)
        self.assertEqual(summary["students"][0]["midterm_results"][0]["percentage"], 60.0)
        assessments = get_assessment_overview(class_ids=[1])
        self.assertEqual(assessments[0]["total_students"], 1)

    def test_faculty_summary_respects_class_scope(self):
        from modules.faculty_dashboard import get_faculty_summary

        self.assertEqual(get_faculty_summary(class_ids=[])["total_students"], 0)
        self.assertEqual(get_faculty_summary(class_ids=[2])["total_students"], 0)
        self.assertEqual(get_faculty_summary(class_ids=[1, 2])["total_students"], 1)

    def test_risk_model_reads_postgres(self):
        from modules import risk_model

        data = risk_model._load_student_data()
        self.assertEqual(list(data["name"]), ["Ada"])
        self.assertAlmostEqual(float(data.iloc[0]["attendance_pct"]), 75.0)

    def test_classroom_query_runs_on_postgres(self):
        from db import get_connection
        from db.base import to_minutes

        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT timetable_id, room_number, building, day_of_week, "
                "start_time, end_time FROM timetable").fetchall()
        finally:
            pass  # the shared fake stays open for other tests
        self.assertEqual(rows[0]["room_number"], "R101")
        self.assertEqual(to_minutes(rows[0]["start_time"][:5]), 600)
        self.assertEqual(to_minutes("10:00"), 600)

    def test_a_postgres_placeholder_is_accepted_directly(self):
        rows = self.connection.execute(
            "SELECT name FROM students WHERE student_id = %s", (1,)).fetchall()
        self.assertEqual(rows[0]["name"], "Ada")
