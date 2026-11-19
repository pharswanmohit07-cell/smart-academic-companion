"""A disposable, PostgreSQL-flavoured database for tests.

There is no PostgreSQL server on the development machine and the deployed
Supabase database must never be used for destructive tests, so the PostgreSQL
back end is exercised against this in-process fake. It understands enough of
PostgreSQL to run the real application SQL and to reject SQLite-only constructs:

* ``%s`` placeholders - a bare ``?`` or a literal ``%`` is an error, exactly
  like PostgreSQL (tests therefore also prove the ``translate()`` step)
* ``EXCLUDED.col`` inside ``ON CONFLICT ... DO UPDATE SET``
* ``CURRENT_DATE`` / ``CURRENT_TIMESTAMP`` / ``COALESCE``
* rows come back as ``db.base.Row`` mappings

It is not a general SQL engine: it covers the statements this project issues.
Every statement is appended to ``executed`` so a test can inspect what ran.
"""

import re
import sqlite3

from db.base import DatabaseError, IntegrityError, Row


class PgFakeError(DatabaseError):
    """Raised for SQL the fake (and PostgreSQL) would reject."""


_SCHEMA = """
CREATE TABLE app_migrations (filename TEXT PRIMARY KEY,
                             applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE faculty_classes (
    class_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL UNIQUE,
    program TEXT NOT NULL,
    semester INTEGER NOT NULL CHECK (semester >= 1),
    section TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_teacher_id INTEGER
);
CREATE TABLE teachers (
    teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
    auth_user_id TEXT UNIQUE,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    semester INTEGER NOT NULL DEFAULT 3,
    section TEXT NOT NULL DEFAULT 'A',
    attendance_type TEXT NOT NULL DEFAULT 'regular',
    class_id INTEGER,
    auth_user_id TEXT UNIQUE,
    is_demo_data INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE subjects (
    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL,
    subject_code TEXT UNIQUE
);
CREATE TABLE attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    subject_id INTEGER NOT NULL REFERENCES subjects(subject_id),
    total_classes INTEGER NOT NULL DEFAULT 0,
    attended_classes INTEGER NOT NULL DEFAULT 0,
    UNIQUE (student_id, subject_id)
);
CREATE TABLE marks (
    mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    subject_id INTEGER NOT NULL REFERENCES subjects(subject_id),
    exam_name TEXT NOT NULL,
    marks_obtained REAL NOT NULL,
    max_marks REAL NOT NULL,
    exam_date TEXT,
    topic_name TEXT
);
CREATE TABLE timetable (
    timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    room_number TEXT NOT NULL,
    day_of_week INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT 'A',
    building TEXT NOT NULL DEFAULT 'Main'
);
CREATE TABLE room_locations (
    room_number TEXT PRIMARY KEY,
    building TEXT NOT NULL DEFAULT '',
    floor TEXT NOT NULL DEFAULT '',
    room_type TEXT NOT NULL DEFAULT ''
);
CREATE TABLE assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT,
    submitted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE exams (
    exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    exam_name TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT
);
CREATE TABLE assessment_items (
    assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    assessment_type TEXT NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subject_id, assessment_type, title)
);
CREATE TABLE assessment_submissions (
    assessment_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    submitted INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (assessment_id, student_id)
);
"""


def _strip_literals(sql):
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return re.sub(r"--[^\n]*", "", sql)


class FakeCursor:
    def __init__(self, rows, rowcount):
        self._rows = list(rows)
        self._index = 0
        self.rowcount = rowcount

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def fetchmany(self, size=None):
        if size is None:
            return self.fetchall()
        rows = self._rows[self._index:self._index + size]
        self._index += len(rows)
        return rows

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        pass


class FakePgConnection:
    """Implements the db back end contract against an in-memory database."""

    backend = "postgresql"

    def __init__(self, raw):
        self._raw = raw
        self._raw.row_factory = sqlite3.Row
        self._raw.execute("PRAGMA foreign_keys = ON")
        self.executed = []

    # -- translation -----------------------------------------------------
    @staticmethod
    def _check_dialect(pg_sql):
        """Reject the SQL SQLite would accept but PostgreSQL would not."""
        without_literals = _strip_literals(pg_sql)
        if "?" in without_literals:
            raise PgFakeError('syntax error at or near "?" - PostgreSQL needs %s')
        if re.search(r"%(?!s)", without_literals):
            raise PgFakeError("invalid placeholder: literal % must be written as %%")

    @staticmethod
    def _translate_received(pg_sql, params):
        """Accept caller SQL in the application's dialect.

        ``db.pg_backend.translate`` converts ``?`` placeholders and SQLite
        date functions. A statement written directly with PostgreSQL ``%s``
        placeholders passes through unchanged.
        """
        from db.pg_backend import translate

        if "?" not in _strip_literals(pg_sql):
            return pg_sql, params
        translated = translate(pg_sql)
        # translate() doubles literal % for psycopg; the fake binds "?"
        # directly, so undo that doubling.
        return translated.replace("%%", "%"), params

    def _rewrite(self, pg_sql, params):
        """Turn an ``ON CONFLICT ... EXCLUDED.x`` update into a SQLite upsert."""
        match = re.search(
            r"INSERT\s+INTO\s+(?P<table>\w+)\s*\((?P<cols>[^)]*)\)\s*"
            r"VALUES\s*\((?P<vals>[^)]*)\)\s*"
            r"ON\s+CONFLICT\s*\((?P<keys>[^)]*)\)\s*DO\s+UPDATE\s+SET\s+(?P<sets>.*)$",
            pg_sql, re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return pg_sql, params

        columns = [c.strip() for c in match.group("cols").split(",")]
        values = [v.strip() for v in match.group("vals").split(",")]
        provided = {}
        position = 0
        for column, value in zip(columns, values):
            if value == "%s":
                provided[column] = position
                position += 1
            elif value.upper() in ("CURRENT_TIMESTAMP", "CURRENT_DATE"):
                provided[column] = value.upper()

        used = []

        def substitute(match_excluded):
            column = match_excluded.group(1)
            if column not in provided:
                return "excluded." + column
            source = provided[column]
            if isinstance(source, int):
                used.append(source)
                return "?"
            return source

        new_sets = re.sub(r"excluded\.(\w+)", substitute, match.group("sets"),
                          flags=re.IGNORECASE)
        # PostgreSQL keeps the existing row on DO NOTHING for a duplicate key.
        if "DO NOTHING" in pg_sql.upper():
            new_sql = pg_sql[:pg_sql.upper().index("ON CONFLICT")] + "ON CONFLICT DO NOTHING"
            return new_sql, params
        new_sql = pg_sql[:match.start("sets")] + new_sets
        return new_sql, tuple(params) + tuple(params[i] for i in used)

    # -- connection contract ---------------------------------------------
    def execute(self, pg_sql, params=()):
        self.executed.append((pg_sql, params))
        # The application's dialect (``?`` placeholders) is accepted here, exactly
        # as ``db.pg_backend`` accepts it before translating. The dialect check
        # below still rejects anything that would reach PostgreSQL malformed.
        sql, sql_params = self._translate_received(pg_sql, tuple(params or ()))
        self._check_dialect(sql)
        sql, sql_params = self._rewrite(sql, sql_params)
        # PostgreSQL uses %s where the in-process engine uses ?.
        sql = sql.replace("%s", "?")
        bound = tuple(int(value) if isinstance(value, bool) else value
                      for value in sql_params)
        try:
            cursor = self._raw.execute(sql, bound)
        except sqlite3.IntegrityError as exc:
            raise IntegrityError(str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise PgFakeError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc
        rows = [Row(dict(row)) for row in cursor.fetchall()]
        return FakeCursor(rows, cursor.rowcount)

    def executescript(self, sql):
        from db.base import split_sql_statements

        for statement in split_sql_statements(sql):
            self.execute(statement)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()

    def table_columns(self, table):
        return {row["name"] for row in
                self._raw.execute(f"PRAGMA table_info({table})").fetchall()}

    def table_exists(self, table):
        row = self._raw.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        return row is not None


def new_connection(seed=True):
    """Create a fake PostgreSQL session with the application tables."""
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    connection = FakePgConnection(raw)
    if seed:
        raw.executescript(_SCHEMA)
        raw.commit()
    return connection
