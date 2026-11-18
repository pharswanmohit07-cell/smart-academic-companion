"""PostgreSQL back end for the Supabase database used in production.

The SQL written for the project uses ``?`` placeholders and a few SQLite
idioms. This module translates them for PostgreSQL so routes and helpers did
not have to be rewritten:

* ``?`` -> ``%s`` (quoted literals and ``--`` comments are skipped)
* ``date('now')`` -> ``CURRENT_DATE``
* ``IFNULL(`` -> ``COALESCE(``
"""

import re

from .base import DatabaseError, IntegrityError, Row

try:  # imported lazily so SQLite-only setups do not need psycopg
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_ERROR = psycopg.Error
except ImportError:  # pragma: no cover - only when psycopg is not installed
    psycopg = None
    dict_row = None
    PSYCOPG_ERROR = Exception


_DATE_NOW = re.compile(r"date\(\s*'now'\s*\)", re.IGNORECASE)
_IFNULL = re.compile(r"\bIFNULL\s*\(", re.IGNORECASE)


def translate(sql):
    """Translate SQLite-flavoured SQL into PostgreSQL SQL."""
    sql = _DATE_NOW.sub("CURRENT_DATE", sql)
    sql = _IFNULL.sub("COALESCE(", sql)

    output = []
    index = 0
    in_string = False
    length = len(sql)
    while index < length:
        char = sql[index]
        if in_string:
            output.append(char)
            if char == "'":
                # A doubled quote is an escaped quote, not the end of string.
                if index + 1 < length and sql[index + 1] == "'":
                    output.append("'")
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if char == "'":
            in_string = True
            output.append(char)
        elif char == "-" and sql.startswith("--", index):
            end = sql.find("\n", index)
            if end == -1:
                output.append(sql[index:])
                break
            output.append(sql[index:end])
            index = end
            continue
        elif char == "?":
            output.append("%s")
        elif char == "%":
            # psycopg uses %s placeholders, so a literal percent must be doubled.
            output.append("%%")
        else:
            output.append(char)
        index += 1
    return "".join(output)


class Cursor:
    """``psycopg`` cursor returning :class:`db.base.Row` mappings."""

    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return None if row is None else Row(row)

    def fetchall(self):
        return [Row(row) for row in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        rows = (self._cursor.fetchmany(size) if size
                else self._cursor.fetchmany())
        return [Row(row) for row in rows]

    def __iter__(self):
        return (Row(row) for row in self._cursor)

    def close(self):
        self._cursor.close()


class Connection:
    """``psycopg`` connection with the portable helpers from :mod:`db`."""

    def __init__(self, connection):
        self._connection = connection
        self.backend = "postgresql"

    def execute(self, sql, params=()):
        try:
            cursor = self._connection.cursor(row_factory=dict_row)
            cursor.execute(translate(sql), params)
            return Cursor(cursor)
        except PSYCOPG_ERROR as exc:
            raise _as_database_error(exc) from exc

    def executescript(self, sql):
        for statement in _split_statements(sql):
            self.execute(statement)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def table_columns(self, table):
        rows = self._connection.cursor().execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
        return {row[0] for row in rows}

    def table_exists(self, table):
        row = self._connection.cursor().execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchone()
        return row is not None


def _split_statements(sql):
    from .base import split_sql_statements

    return split_sql_statements(sql)


def _as_database_error(exc):
    sqlstate = getattr(exc, "sqlstate", None) or ""
    message = str(exc).strip()
    # Class 23: integrity constraint violation (unique, FK, check, not-null).
    if sqlstate.startswith("23") or "violates" in message:
        return IntegrityError(message)
    return DatabaseError(message)


def is_available():
    return psycopg is not None


def connect(dsn):
    if psycopg is None:  # pragma: no cover - configuration error
        raise DatabaseError(
            "The PostgreSQL driver (psycopg) is not installed. "
            "Install it with: pip install 'psycopg[binary]'"
        )
    connection = psycopg.connect(dsn, autocommit=False, connect_timeout=10)
    return Connection(connection)
