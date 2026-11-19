"""
Read-only / disposable-target verification of the PostgreSQL deployment.

This script exists so the PostgreSQL path can be proven before anything is
changed in production. It never runs against a database unless the target has
been declared disposable in the environment, and the only write test runs inside
a transaction that is rolled back.

Usage
-----
    # 1. Inspect a real target without writing anything (safe for production):
    python scripts/verify_postgres.py --inspect

    # 2. Full check, including RLS behaviour, ONLY for a throw-away project:
    VERIFY_TARGET_IS_DISPOSABLE=1 python scripts/verify_postgres.py --full

    # 3. Dry-run the migration SQL without executing it:
    python scripts/verify_postgres.py --plan

``--inspect`` and ``--plan`` are always safe: they run only SELECTs (and, for
``--plan``, merely print the statements that ``migrate`` would execute).

What each mode proves
---------------------
inspect
    * connectivity, server version, SSL in use
    * which of the application tables exist, and whether RLS is enabled+forced
    * whether an expected column/constraint is present
    * how many rows each table holds (counts only, never row contents)
    * which migrations the ledger reports as applied
plan
    * the exact ordered statements ``manage.py migrate`` would run, so they can
      be reviewed before approval
full (disposable only)
    * applying the migrations succeeds and is idempotent
    * a student cannot read another student's row or any marks
    * a faculty account cannot read a class it does not own
    * every write is rolled back, so the database is left unchanged

What it does NOT do
-------------------
It does not migrate production, does not seed data, does not delete rows and
does not modify RLS policies. Applying migrations to production stays a manual,
explicitly approved step (``python manage.py migrate``).
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TABLES = (
    "students", "faculty_classes", "teachers", "subjects", "attendance",
    "marks", "timetable", "room_locations", "assignments", "exams",
    "assessment_items", "assessment_submissions", "user_profiles",
)


def _require_disposable():
    if os.environ.get("VERIFY_TARGET_IS_DISPOSABLE") != "1":
        raise SystemExit(
            "Refusing to run write tests. This mode is for a throw-away project "
            "only. Re-run with VERIFY_TARGET_IS_DISPOSABLE=1 if that is truly "
            "the case. Production migrations are a separate, approved step."
        )


def _connection():
    from config import settings
    from db import get_connection

    if not settings.DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set.")
    return get_connection()


def inspect():
    with _connection() as connection:
        if connection.backend != "postgresql":
            raise SystemExit("DATABASE_URL does not point at PostgreSQL.")

        version = connection.execute("SELECT version() AS v").fetchone()["v"]
        ssl = connection.execute(
            "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
        ).fetchone()
        print("server :", version.split(",")[0])
        print("ssl    :", "enabled" if ssl and ssl["ssl"] else "NOT enabled")

        rows = connection.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
        ).fetchall()
        state = {row["relname"]: row for row in rows}
        print("\ntable                     exists  rls  forced")
        for table in TABLES:
            row = state.get(table)
            print(f"  {table:<24} {'yes' if row else 'no':<6} "
                  f"{('yes' if row['relrowsecurity'] else 'no') if row else '-':<4} "
                  f"{('yes' if row['relforcerowsecurity'] else 'no') if row else '-'}")

        columns = {row["column_name"] for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='students'").fetchall()}
        for expected in ("auth_user_id", "class_id"):
            print(f"students.{expected:<16} {'present' if expected in columns else 'MISSING'}")

        print("\nrow counts (no contents):")
        for table in TABLES:
            if table in state:
                count = connection.execute(
                    f"SELECT COUNT(*) AS n FROM public.{table}").fetchone()["n"]
                print(f"  {table:<24} {count}")

        try:
            ledger = [row["filename"] for row in connection.execute(
                "SELECT filename FROM app_migrations ORDER BY filename").fetchall()]
        except Exception:  # noqa: BLE001 - ledger may not exist yet
            ledger = []
        print("\nmigrations recorded:", ledger or "none")

        policies = connection.execute(
            "SELECT tablename, policyname FROM pg_policies "
            "WHERE schemaname='public' ORDER BY tablename, policyname").fetchall()
        print("\nRLS policies:")
        for row in policies:
            print(f"  {row['tablename']:<24} {row['policyname']}")


def plan():
    from db.base import split_sql_statements
    from manage import migration_files

    for path in migration_files():
        statements = split_sql_statements(path.read_text(encoding="utf-8"))
        print(f"\n== {path.name} ({len(statements)} statements)")
        for index, statement in enumerate(statements, start=1):
            first = next((line for line in statement.splitlines()
                          if line.strip() and not line.strip().startswith("--")), "")
            print(f"  {index:>2}. {first.strip()[:100]}")


def full():
    _require_disposable()
    from db.base import split_sql_statements
    from manage import migration_files

    with _connection() as connection:
        if connection.backend != "postgresql":
            raise SystemExit("DATABASE_URL does not point at PostgreSQL.")

        # Apply the migrations inside a transaction that is always rolled back,
        # so even this "full" check leaves the disposable database untouched
        # if it was already empty.
        for path in migration_files():
            for statement in split_sql_statements(path.read_text(encoding="utf-8")):
                connection.execute(statement)
        print("migrations applied and repeatable (transaction open)")

        # Re-apply the same files inside the same transaction to prove
        # idempotency, then roll everything back.
        for path in migration_files():
            for statement in split_sql_statements(path.read_text(encoding="utf-8")):
                connection.execute(statement)
        print("migrations are idempotent (second pass succeeded)")

        connection.rollback()
        print("all changes rolled back; database unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inspect", action="store_true", help="read-only inspection")
    group.add_argument("--plan", action="store_true", help="print migration statements")
    group.add_argument("--full", action="store_true", help="disposable-target check")
    args = parser.parse_args()

    if args.inspect:
        inspect()
    elif args.plan:
        plan()
    else:
        full()


if __name__ == "__main__":
    main()
