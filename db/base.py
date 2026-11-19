"""
Database access layer shared by the SQLite (local development) and PostgreSQL
(Supabase, production) back ends.

Application code never imports ``sqlite3`` or ``psycopg`` directly. It asks
:mod:`db` for a connection and uses the small, portable API defined here:

* ``conn.execute(sql, params)`` returns a cursor whose rows are mappings that
  support both ``row["column"]`` and ``dict(row)``.
* Placeholders are always ``?`` and are translated to ``%s`` for PostgreSQL,
  so the existing SQL in the project keeps working unchanged.
* Booleans may be passed as Python ``True``/``False`` to either engine.
* ``last_insert_id(conn, table, column)`` replaces SQLite's ``cursor.lastrowid``.

Each back end implements the cursor/connection contract; :mod:`db` chooses
the back end from configuration.
"""

import re

# Marker line that starts every statement in a migration file. A ``$$``
# function body contains semicolons, so splitting on ";" alone is unsafe.
STATEMENT_MARKER = "-- app-migration:"


class DatabaseError(Exception):
    """Base class for database failures raised through the abstraction."""


class IntegrityError(DatabaseError):
    """A constraint (unique, foreign key, check) was violated."""


class SchemaMismatchError(DatabaseError):
    """The SQL names a column or table that the schema does not have."""


_INTEGER_STRING = re.compile(r"^-?\d+$")
_FLOAT_STRING = re.compile(r"^-?\d+\.\d+$")


class Row(dict):
    """A result row that works as a dict and accepts a zero-based index."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def coerce_bool_params(params):
    """SQLite has no boolean type, so bind 0/1 instead of True/False."""
    if not isinstance(params, (tuple, list)):
        return params
    changed = False
    values = []
    for value in params:
        if isinstance(value, bool):
            values.append(1 if value else 0)
            changed = True
        else:
            values.append(value)
    return tuple(values) if changed else params


def numeric_text(value):
    """Render a number the way SQLite returned it.

    PostgreSQL returns integers for ``EXTRACT(HOUR FROM ...)`` and ``int``
    columns; the templates and ``to_minutes()`` previously received the text
    values stored in SQLite.
    """
    text = str(value)
    if _INTEGER_STRING.match(text):
        return text
    if _FLOAT_STRING.match(text):
        whole, _, fraction = text.partition(".")
        return f"{int(whole)}.{fraction}"
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


def to_minutes(value):
    """Convert a time value to minutes after midnight.

    Accepts ``'HH:MM'`` (SQLite TEXT), ``'HH:MM:SS'`` (PostgreSQL TIME),
    ``Decimal('9.5')`` from ``EXTRACT(HOUR FROM ...)`` and plain numbers.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value) * 60)) if float(value) < 24 else int(value)
    text = str(value).strip()
    if ":" in text:
        hour_text, minute_text = text.split(":")[:2]
        if "." in hour_text:
            # PostgreSQL EXTRACT(HOUR) can return Decimal('9.5'): 9:30.
            hours = float(hour_text)
            whole = int(hours)
            return whole * 60 + int(round((hours - whole) * 60)) + int(float(minute_text))
        return int(hour_text) * 60 + int(minute_text)
    number = float(text)
    return int(round(number * 60)) if number < 24 else int(number)


def split_sql_statements(sql_text):
    """Split a migration file into statements at the marker line.

    Lines before the first marker are only comments; a statement is complete
    at the next marker, so ``DO $$ ... $$`` bodies keep their semicolons.
    """
    statements = []
    current = []

    def flush():
        lines = list(current)
        current.clear()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        while lines and lines[-1].strip() == "":
            lines.pop()
        text = "\n".join(lines).strip()
        if text:
            statements.append(text)

    for line in sql_text.splitlines():
        if line.startswith(STATEMENT_MARKER):
            flush()
            continue
        current.append(line)
    flush()
    return statements
