import sqlite3
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "academic_companion.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_connection():
    """Open a database connection with foreign-key checks enabled."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _add_column_if_missing(connection, table, column, definition):
    """Add a known compatibility column only when it is absent."""
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if column not in existing:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def _apply_compatibility_migrations(connection):
    """Bring older project databases up to the current required columns."""
    migrations = (
        ("students", "semester", "INTEGER NOT NULL DEFAULT 3"),
        ("students", "section", "TEXT NOT NULL DEFAULT 'A'"),
        ("students", "attendance_type", "TEXT NOT NULL DEFAULT 'regular'"),
        ("students", "class_id", "INTEGER REFERENCES faculty_classes(class_id) ON DELETE SET NULL"),
        ("marks", "topic_name", "TEXT"),
        ("timetable", "section", "TEXT NOT NULL DEFAULT 'A'"),
    )

    for table, column, definition in migrations:
        _add_column_if_missing(connection, table, column, definition)


def _assign_legacy_students_to_classes(connection):
    """Group existing unassigned students into classes without changing their records."""
    groups = connection.execute(
        """SELECT DISTINCT semester, section FROM students
           WHERE class_id IS NULL ORDER BY semester, section"""
    ).fetchall()
    for row in groups:
        semester = int(row["semester"])
        section = (row["section"] or "A").strip().upper() or "A"
        class_name = f"Existing Demo - Semester {semester} - Section {section}"
        connection.execute(
            """INSERT OR IGNORE INTO faculty_classes
               (class_name, program, semester, section, description)
               VALUES (?, ?, ?, ?, ?)""",
            (class_name, "Existing / Demo", semester, section,
             "Automatically grouped from students already in the database."),
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
    """Create tables and safely add compatibility columns without deleting data."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with closing(get_connection()) as connection:
        with connection:
            connection.executescript(schema)
            _apply_compatibility_migrations(connection)
            _assign_legacy_students_to_classes(connection)


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DATABASE_PATH}")
