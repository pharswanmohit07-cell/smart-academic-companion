import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import database


class TestDatabaseInitialization(unittest.TestCase):
    def test_initialize_database_adds_missing_compatibility_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "legacy.db"

            # Simulate a database created before the newer optional columns
            # were added. Keep the columns used by current indexes intact.
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE students (
                        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE marks (
                        mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        subject_id INTEGER NOT NULL,
                        exam_name TEXT NOT NULL,
                        marks_obtained REAL NOT NULL,
                        max_marks REAL NOT NULL,
                        exam_date TEXT
                    );

                    CREATE TABLE timetable (
                        timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        subject_id INTEGER NOT NULL,
                        room_number TEXT NOT NULL,
                        day_of_week INTEGER NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT NOT NULL
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO students (name, email) VALUES (?, ?)",
                    ("Existing Student", "existing@example.edu"),
                )
                connection.commit()

            with patch.object(database, "DATABASE_PATH", db_path), patch.object(
                database, "SCHEMA_PATH", Path(__file__).resolve().parents[1] / "schema.sql"
            ):
                database.initialize_database()

            with closing(sqlite3.connect(db_path)) as connection:
                student_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(students)")
                }
                marks_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(marks)")
                }
                timetable_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(timetable)")
                }
                existing_student = connection.execute(
                    "SELECT name FROM students WHERE email = ?",
                    ("existing@example.edu",),
                ).fetchone()

            self.assertTrue({"semester", "section", "attendance_type"} <= student_columns)
            self.assertIn("topic_name", marks_columns)
            self.assertIn("section", timetable_columns)
            self.assertEqual(existing_student, ("Existing Student",))


if __name__ == "__main__":
    unittest.main()
