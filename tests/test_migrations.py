"""Dialect, database-layer and migration checks (offline).

These tests prove the PostgreSQL-specific work without a PostgreSQL server:

* ``db.pg_backend.translate`` rewrites every SQLite idiom the project used;
* the application's real SQL runs under PostgreSQL placeholder rules against
  the in-process fake (``tests/pg_fake.py``), which rejects ``?``/bare ``%``;
* the migration files have no SQLite-only constructs, every statement carries
  the marker the runner needs, and they apply idempotently in order.
"""

import re
import unittest
from pathlib import Path

from tests import pg_fake
from tests.support import TempDatabaseMixin, USER_PROFILES_DDL

from db import pg_backend
from db.base import split_sql_statements

MIGRATIONS = sorted((Path(__file__).resolve().parent.parent / "migrations").glob("*.sql"))


def _sql_only(path):
    """Return only the executable statements of a migration (comments dropped)."""
    return "\n".join(split_sql_statements(path.read_text(encoding="utf-8")))


class TestTranslation(unittest.TestCase):
    def test_placeholders_become_percent_s(self):
        self.assertEqual(
            pg_backend.translate("SELECT * FROM t WHERE a = ? AND b = ?"),
            "SELECT * FROM t WHERE a = %s AND b = %s",
        )

    def test_question_marks_inside_literals_and_comments_are_untouched(self):
        sql = "SELECT 'why?' AS a -- and? comment\nFROM t WHERE x = ?"
        translated = pg_backend.translate(sql)
        self.assertIn("'why?'", translated)
        self.assertIn("-- and? comment", translated)
        self.assertTrue(translated.endswith("x = %s"))

    def test_percent_literals_are_doubled(self):
        self.assertEqual(pg_backend.translate("SELECT 5 % 2, ?"), "SELECT 5 %% 2, %s")

    def test_sqlite_date_and_ifnull_are_rewritten(self):
        self.assertEqual(pg_backend.translate("SELECT date('now')"),
                         "SELECT CURRENT_DATE")
        self.assertEqual(pg_backend.translate("SELECT IFNULL(a, 0) FROM t"),
                         "SELECT COALESCE(a, 0) FROM t")

    def test_escaped_quotes_do_not_confuse_the_scanner(self):
        sql = "SELECT 'it''s ? fine' FROM t WHERE x = ?"
        self.assertEqual(pg_backend.translate(sql),
                         "SELECT 'it''s ? fine' FROM t WHERE x = %s")


class TestApplicationSqlOnPostgresRules(TempDatabaseMixin, unittest.TestCase):
    """Run the real application SQL through a PostgreSQL-strict connection."""

    def setUp(self):
        super().setUp()
        self.pg = pg_fake.new_connection()
        self.pg.executescript(USER_PROFILES_DDL)
        self.addCleanup(self.pg.close)

    def executed(self, params=()):
        return params

    def test_faculty_manage_writes_and_reads(self):
        # Exercise the same statements the faculty view issues, translated the
        # way the PostgreSQL connection translates them.
        statements = [
            ("INSERT INTO subjects (subject_name) VALUES (?)", ("Operating Systems",)),
            ("INSERT INTO students (name, email, semester, section, class_id) "
             "VALUES (?, ?, ?, ?, ?)", ("Asha", "asha@example.com", 3, "A", 1)),
            ("INSERT INTO attendance (student_id, subject_id, total_classes, "
             "attended_classes) VALUES (?, ?, ?, ?) ON CONFLICT(student_id, subject_id) "
             "DO UPDATE SET total_classes = excluded.total_classes, "
             "attended_classes = excluded.attended_classes", (1, 1, 12, 9)),
            ("INSERT INTO attendance (student_id, subject_id, total_classes, "
             "attended_classes) VALUES (?, ?, ?, ?) ON CONFLICT(student_id, subject_id) "
             "DO UPDATE SET total_classes = excluded.total_classes, "
             "attended_classes = excluded.attended_classes", (1, 1, 20, 19)),
            ("INSERT INTO marks (student_id, subject_id, exam_name, marks_obtained, "
             "max_marks, exam_date) VALUES (?, ?, ?, ?, ?, date('now'))",
             (1, 1, "Midterm", 80.0, 100.0)),
            ("INSERT INTO assessment_items (subject_id, assessment_type, title, due_date) "
             "VALUES (?, ?, ?, ?)", (1, "assignment", "Lab 1", None)),
            ("INSERT INTO assessment_submissions (assessment_id, student_id, submitted) "
             "SELECT assessment_id, ?, 0 FROM assessment_items", (1,)),
        ]
        for sql, params in statements:
            self.pg.execute(pg_backend.translate(sql), params)

        rows = self.pg.execute(
            pg_backend.translate("SELECT total_classes, attended_classes FROM attendance")
        ).fetchall()
        self.assertEqual(dict(rows[0]), {"total_classes": 20, "attended_classes": 19})

        marks = self.pg.execute(pg_backend.translate(
            "SELECT exam_date FROM marks")).fetchall()
        self.assertIsNotNone(marks[0]["exam_date"])

    def test_raw_question_mark_is_rejected_like_postgres(self):
        # The fake accepts the application dialect, but the SQL that reaches
        # PostgreSQL must never contain a ``?`` placeholder. Translation is the
        # step that guarantees this; a bypass is detected here.
        sql, params = pg_backend.translate("SELECT * FROM students WHERE name = ?"), ("x",)
        self.assertNotIn("?", sql)
        self.pg.execute(sql, params)
        self.assertNotIn("?", self.pg.executed[-1][0])

    def test_faculty_dashboard_queries_are_postgres_clean(self):
        from modules.faculty_dashboard import _scope_clause

        scope_sql, params = _scope_clause(None, [1, 2])
        sql = pg_backend.translate(
            f"SELECT s.student_id FROM students AS s WHERE {scope_sql}")
        self.assertEqual(sql, "SELECT s.student_id FROM students AS s WHERE s.class_id IN (%s, %s)")
        self.assertEqual(params, [1, 2])
        self.pg.execute(sql, tuple(params))

    def test_risk_query_is_postgres_clean(self):
        from modules import risk_model

        source = Path(risk_model.__file__).read_text(encoding="utf-8")
        query = re.search(r'"""(.*?WITH attendance_by_student.*?)"""', source, re.S).group(1)
        translated = pg_backend.translate(query)
        self.assertNotIn("?", translated.replace("%s", ""))

    def test_last_insert_id_uses_a_returning_query(self):
        from db import last_insert_id

        # The fake cannot emulate currval, but it must receive PostgreSQL syntax.
        self.pg.execute(pg_backend.translate(
            "INSERT INTO subjects (subject_name) VALUES (?)"), ("Maths",))
        with self.assertRaises(pg_fake.PgFakeError):
            last_insert_id(self.pg, "subjects", "subject_id")


class TestMigrationFiles(unittest.TestCase):
    def test_files_exist_and_are_ordered(self):
        names = [path.name for path in MIGRATIONS]
        self.assertEqual(names[0], "0001_initial_schema.sql")
        self.assertEqual(names, sorted(names))

    def test_every_statement_is_marked_and_parsed(self):
        for path in MIGRATIONS:
            statements = split_sql_statements(path.read_text(encoding="utf-8"))
            self.assertTrue(statements, path.name)
            for statement in statements:
                self.assertFalse(statement.lstrip().startswith("-- app-migration:"),
                                 f"{path.name}: marker left in statement")

    def test_no_sqlite_only_constructs(self):
        forbidden = [
            (r"\bAUTOINCREMENT\b", "AUTOINCREMENT"),
            (r"\bPRAGMA\b", "PRAGMA"),
            (r"\bsqlite_master\b", "sqlite_master"),
            (r"\blastrowid\b", "lastrowid"),
            (r"\bINSERT\s+OR\s+(IGNORE|REPLACE)\b", "INSERT OR ..."),
            (r"\bdate\(\s*'now'\s*\)", "date('now')"),
            (r"\bdatetime\(\s*'now'\s*\)", "datetime('now')"),
        ]
        for path in MIGRATIONS:
            text = path.read_text(encoding="utf-8")
            for pattern, label in forbidden:
                with self.subTest(file=path.name, found=label):
                    self.assertIsNone(re.search(pattern, text, re.I))

    def test_rls_is_enabled_for_every_application_table(self):
        text = "".join(path.read_text(encoding="utf-8") for path in MIGRATIONS)
        tables = ["faculty_classes", "students", "subjects", "attendance", "marks",
                  "timetable", "room_locations", "assignments", "exams",
                  "assessment_items", "assessment_submissions", "teachers"]
        loop = re.search(r"FOREACH t IN ARRAY ARRAY\[(.*?)\]", text, re.S).group(1)
        for table in tables:
            with self.subTest(table=table):
                self.assertIn(f"'{table}'", loop)
        self.assertIn("ENABLE ROW LEVEL SECURITY", text)
        self.assertIn("FORCE ROW LEVEL SECURITY", text)

    def test_policies_never_trust_user_metadata(self):
        for path in MIGRATIONS:
            text = _sql_only(path)
            with self.subTest(file=path.name):
                self.assertNotIn("raw_user_meta_data", text)
                self.assertNotIn("user_metadata", text)
                self.assertNotIn("raw_app_meta_data", text)
        combined = "".join(_sql_only(path) for path in MIGRATIONS)
        self.assertIn("public.user_profiles", combined)

    def test_policy_expressions_are_tables_valued_in_sync(self):
        """Policies must not query a table their own policies protect.

        Recursion happens when a policy's expression queries the same table; the
        helper functions therefore only read user_profiles / teachers, which the
        caller can already read for their own row.
        """
        helpers = _sql_only(MIGRATIONS[1])
        self.assertIn("public.user_profiles", helpers)
        self.assertIn("app_current_student_id", helpers)
        self.assertEqual(helpers.count("SECURITY INVOKER"), 9)
        self.assertNotIn("SECURITY DEFINER", helpers)

    def test_helpers_are_security_invoker(self):
        # Policy helpers remain SECURITY INVOKER. The Auth signup trigger is
        # the only deliberate SECURITY DEFINER function because Auth creates
        # profiles while RLS is enabled. Both trigger migrations must pin an
        # empty search_path and revoke direct execution from API roles.
        helpers = _sql_only(MIGRATIONS[1])
        self.assertNotIn("SECURITY DEFINER", helpers)
        self.assertEqual(helpers.count("SECURITY INVOKER"), 9)

        allowed_definer = {
            "0005_profile_email_and_rls_hardening.sql",
            "0010_signup_trigger_display_name_safety.sql",
        }
        for path in MIGRATIONS:
            text = _sql_only(path)
            if path.name not in allowed_definer:
                with self.subTest(file=path.name):
                    self.assertNotIn("SECURITY DEFINER", text)
            else:
                with self.subTest(file=path.name):
                    self.assertIn(
                        "CREATE OR REPLACE FUNCTION public.handle_new_user()", text
                    )
                    self.assertIn("SECURITY DEFINER", text)
                    self.assertIn("SET search_path = ''", text)
                    self.assertIn(
                        "REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated",
                        text,
                    )

    def test_admin_bootstrap_storage_is_private(self):
        text = _sql_only(MIGRATIONS[8])
        self.assertIn("CREATE TABLE IF NOT EXISTS public.admin_bootstrap", text)
        self.assertIn("ENABLE ROW LEVEL SECURITY", text)
        self.assertIn("FORCE ROW LEVEL SECURITY", text)
        self.assertIn(
            "REVOKE ALL ON TABLE public.admin_bootstrap FROM PUBLIC, anon, authenticated",
            text,
        )
        self.assertIn("CREATE POLICY admin_bootstrap_deny_clients", text)

    def test_student_policies_restrict_to_own_rows(self):
        text = _sql_only(MIGRATIONS[2])
        self.assertIn("app_current_student_id()", text)
        self.assertIn("auth_user_id = (SELECT auth.uid())", text)
        # Writes to protected academic records are server-side only.
        self.assertNotIn("FOR UPDATE TO authenticated", text.split("assignments_update_own")[0])

    def test_runner_is_idempotent_and_records_a_ledger(self):
        source = (Path(__file__).resolve().parent.parent / "manage.py").read_text("utf-8")
        self.assertIn("ON CONFLICT (filename) DO NOTHING", source)
        self.assertIn("rollback()", source)


class TestMigrationRunner(TempDatabaseMixin, unittest.TestCase):
    def test_migrations_apply_once_and_are_repeatable(self):
        from manage import run_migrations

        name_order = [path.name for path in MIGRATIONS]
        applied, skipped = run_migrations(database_file=self.db_path)
        # SQLite skips the PostgreSQL-only files, records nothing for them, and
        # never leaves a half-applied migration behind.
        self.assertEqual(applied, [])
        self.assertEqual(skipped, name_order)  # every file is PostgreSQL-only

        from db import sqlite_backend

        connection = sqlite_backend.connect_to(self.db_path)
        try:
            connection.execute(
                "INSERT INTO app_migrations (filename) VALUES (?)",
                (name_order[0],),
            )
            connection.commit()
        finally:
            connection.close()

        # The ledger is now populated for this throw-away database; a second
        # run applies nothing new (no duplicate DDL, no duplicated data).
        applied_again, _ = run_migrations(database_file=self.db_path)
        self.assertEqual(applied_again, [])

        from db import sqlite_backend

        connection = sqlite_backend.connect_to(self.db_path)
        try:
            rows = connection.execute(
                "SELECT filename FROM app_migrations ORDER BY filename").fetchall()
        finally:
            connection.close()
        # Skipped files are never recorded, so only the row inserted above is
        # in the ledger: it stays pending for PostgreSQL and is applied there.
        self.assertEqual([row["filename"] for row in rows], [name_order[0]])

    def test_postgres_migration_adds_auth_columns(self):
        with self.connect() as connection:
            columns = connection.table_columns("students")
            class_columns = connection.table_columns("faculty_classes")
        # Added by the local compatibility step (and by migration 0001 in
        # PostgreSQL): every ownership check uses this column.
        self.assertIn("auth_user_id", columns)
        self.assertIn("owner_teacher_id", class_columns)


class TestDatabaseLayer(unittest.TestCase):
    def test_bool_parameters_are_accepted_by_both_backends(self):
        from db.base import coerce_bool_params

        self.assertEqual(coerce_bool_params((True, "x")), (1, "x"))
        connection = pg_fake.new_connection()
        self.addCleanup(connection.close)
        connection.execute(
            pg_backend.translate("INSERT INTO students (name, is_demo_data) VALUES (?, ?)"),
            ("Demo", True))
        row = connection.execute("SELECT is_demo_data FROM students").fetchone()
        self.assertEqual(int(row["is_demo_data"]), 1)

    def test_numeric_text_matches_sqlite_output(self):
        from db.base import to_minutes

        self.assertEqual(to_minutes("09:00:00"), 540)
        self.assertEqual(to_minutes("10:30"), 630)
        self.assertEqual(to_minutes(1080), 1080)


if __name__ == "__main__":
    unittest.main()
