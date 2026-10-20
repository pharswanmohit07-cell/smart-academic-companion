
import sqlite3
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


def initialize_database():
    """Create the tables defined in schema.sql."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with get_connection() as connection:
        connection.executescript(schema)


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DATABASE_PATH}")
