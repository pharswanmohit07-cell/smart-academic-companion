"""
SQLite schema bootstrap and compatibility migrations for local development.

All connections go through :func:`db.get_connection`, so the same code runs on
SQLite locally and on Supabase PostgreSQL in production. ``schema.sql`` (and
the ``PRAGMA``/``ALTER TABLE`` statements below) only ever run against SQLite:
the PostgreSQL schema is created and upgraded by the SQL migrations in
``migrations/``, which are applied with ``python manage.py migrate``.

The local SQLite file is never dropped or recreated by this module; missing
tables and columns are added without touching existing rows.
"""

from contextlib import closing
from pathlib import Path

from db import DatabaseError, get_connection

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "academic_companion.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

__all__ = [
    "BASE_DIR",
    "DATABASE_PATH",
    "SCHEMA_PATH",
    "get_connection",
    "initialize_database",
]


def _add_column_if_missing(connection, table, column, definition):
    """Add a known compatibility column only when it is absent."""
    existing = connection._connection.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()
    if column not in {row["name"] for row in existing}:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def _apply_compatibility_migrations(connection):
    """Bring older project databases up to the current required columns.

    Every column added here must also be optional (nullable, or with a
    DEFAULT) in PostgreSQL, because the deployed schema is upgraded by the
    migrations in ``migrations/`` instead of this function.
    """
    migrations = (
        ("students", "semester", "INTEGER NOT NULL DEFAULT 3"),
        ("students", "section", "TEXT NOT NULL DEFAULT 'A'"),
        ("students", "attendance_type", "TEXT NOT NULL DEFAULT 'regular'"),
        ("students", "class_id", "INTEGER REFERENCES faculty_classes(class_id) ON DELETE SET NULL"),
        ("students", "auth_user_id", "TEXT"),
        ("marks", "topic_name", "TEXT"),
        ("timetable", "section", "TEXT NOT NULL DEFAULT 'A'"),
        ("timetable", "building", "TEXT NOT NULL DEFAULT 'Main'"),
    )

    for table, column, definition in migrations:
        _add_column_if_missing(connection, table, column, definition)


def _assign_legacy_students_to_classes(connection):
    """Give existing students clear class labels and group unassigned students safely."""
    # Rename the automatically generated placeholder classes from the first migration.
    # Existing students stay linked to the same class IDs, so their academic records remain intact.
    legacy_classes = connection.execute(
        """SELECT class_id, class_name, semester, section
           FROM faculty_classes
           WHERE class_name LIKE 'Existing Demo - Semester %'"""
    ).fetchall()

    for row in legacy_classes:
        semester = int(row["semester"])
        section = (row["section"] or "A").strip().upper() or "A"
        class_name = f"BCA AI & DS - Sem {semester} - Section {section}"
        existing = connection.execute(
            "SELECT class_id FROM faculty_classes WHERE class_name = ?",
            (class_name,),
        ).fetchone()

        if existing and existing["class_id"] != row["class_id"]:
            # If the clean label already exists, move students to it before removing
            # the duplicate placeholder class.
            connection.execute(
                "UPDATE students SET class_id = ? WHERE class_id = ?",
                (existing["class_id"], row["class_id"]),
            )
            connection.execute(
                "DELETE FROM faculty_classes WHERE class_id = ?",
                (row["class_id"],),
            )
        else:
            connection.execute(
                """UPDATE faculty_classes
                   SET class_name = ?, program = ?, description = ?
                   WHERE class_id = ?""",
                (
                    class_name,
                    "BCA AI & Data Science",
                    "Existing students grouped by semester and section.",
                    row["class_id"],
                ),
            )

    # Any students not yet assigned get a clean class label instead of "Existing Demo".
    groups = connection.execute(
        """SELECT DISTINCT semester, section FROM students
           WHERE class_id IS NULL ORDER BY semester, section"""
    ).fetchall()
    for row in groups:
        semester = int(row["semester"])
        section = (row["section"] or "A").strip().upper() or "A"
        class_name = f"BCA AI & DS - Sem {semester} - Section {section}"
        connection.execute(
            """INSERT INTO faculty_classes
               (class_name, program, semester, section, description)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (class_name) DO NOTHING""",
            (
                class_name,
                "BCA AI & Data Science",
                semester,
                section,
                "Existing students grouped by semester and section.",
            ),
        )
        class_row = connection.execute(
            "SELECT class_id FROM faculty_classes WHERE class_name = ?",
            (class_name,),
        ).fetchone()
        connection.execute(
            """UPDATE students SET class_id = ?
               WHERE class_id IS NULL AND semester = ? AND upper(section) = ?""",
            (class_row["class_id"], semester, section),
        )


def initialize_database():
    """Create the SQLite schema and safely add compatibility columns."""
    from db import is_postgres

    if is_postgres():
        raise DatabaseError(
            "initialize_database() only manages the local SQLite file. "
            "Apply the PostgreSQL schema with: python manage.py migrate"
        )

    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with closing(get_connection()) as connection:
        try:
            connection.executescript(schema)
            _apply_compatibility_migrations(connection)
            _assign_legacy_students_to_classes(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return connection.path


if __name__ == "__main__":
    print(f"Database initialized: {initialize_database()}")
