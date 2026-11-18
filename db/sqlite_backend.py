"""SQLite back end used for local development and the offline test suite.

Behaviour is exactly what the project had before the PostgreSQL migration:
``sqlite3`` with ``Row`` results, foreign keys enabled and ``?`` placeholders.
Production (Render) uses :mod:`db.pg_backend` instead.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from .base import DatabaseError, IntegrityError, Row, coerce_bool_params

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = BASE_DIR / "academic_companion.db"


def database_path():
    """Resolve the SQLite file path from configuration."""
    from config import settings

    if settings.DATABASE_FILE:
        return Path(settings.DATABASE_FILE)
    return DEFAULT_DATABASE_PATH


class Cursor:
    """Wrap ``sqlite3.Cursor`` so it matches the PostgreSQL cursor contract."""

    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def _rows(self, rows):
        return [Row(row) for row in rows]

    def fetchone(self):
        row = self._cursor.fetchone()
        return None if row is None else Row(row)

    def fetchall(self):
        return self._rows(self._cursor.fetchall())

    def fetchmany(self, size=None):
        rows = (self._cursor.fetchmany(size) if size
                else self._cursor.fetchmany())
        return self._rows(rows)

    def __iter__(self):
        return (Row(row) for row in self._cursor)

    def close(self):
        self._cursor.close()


class Connection:
    """Thin wrapper adding the shared helpers used by ``db``."""

    def __init__(self, connection, path):
        self._connection = connection
        self.path = path
        self.backend = "sqlite"

    def execute(self, sql, params=()):
        try:
            return Cursor(self._connection.execute(sql, coerce_bool_params(params)))
        except sqlite3.IntegrityError as exc:
            raise IntegrityError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def executescript(self, sql):
        try:
            self._connection.executescript(sql)
        except sqlite3.IntegrityError as exc:
            raise IntegrityError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def table_columns(self, table):
        rows = self._connection.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    def table_exists(self, table):
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None


def connect():
    """Open a configured SQLite connection."""
    return connect_to(database_path())


def connect_to(path):
    """Open a SQLite connection to an explicit file (used by tests)."""
    path = Path(path)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return Connection(connection, path)


def is_available():
    """SQLite is always available in the standard library."""
    return True


def initialize_from_schema(schema_path, database_file=None):
    """Create tables from a SQLite schema file (``schema.sql``).

    ``database_file`` overrides the configured path; the test suite uses it
    to build throw-away databases.
    """
    path = Path(database_file) if database_file else database_path()
    schema = Path(schema_path).read_text(encoding="utf-8")
    with closing(sqlite3.connect(path)) as raw:
        raw.executescript(schema)
        raw.commit()
    return path
