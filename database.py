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
        ("marks", "topic_name", "TEXT"),
        ("timetable", "section", "TEXT NOT NULL DEFAULT 'A'"),
    )

    for table, column, definition in migrations:
        _add_column_if_missing(connection, table, column, definition)


def initialize_database():
    """Create tables and safely add compatibility columns without deleting data."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with closing(get_connection()) as connection:
        with connection:
            connection.executescript(schema)
            _apply_compatibility_migrations(connection)


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DATABASE_PATH}")
