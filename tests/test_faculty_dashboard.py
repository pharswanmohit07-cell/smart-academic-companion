import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from modules.faculty_dashboard import get_faculty_summary


class TestFacultyDashboard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "dashboard.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.database_patch.start()
        database.initialize_database()

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO students (name, email) VALUES (?, ?)",
                ("Test Student", "test@example.edu"),
            )
            connection.executemany(
                "INSERT INTO subjects (subject_name, subject_code) VALUES (?, ?)",
                [("Data Structures", "DSA"), ("Python", "PY")],
            )
            student_id = connection.execute(
                "SELECT student_id FROM students"
            ).fetchone()[0]
            subject_ids = connection.execute(
                "SELECT subject_id FROM subjects ORDER BY subject_code"
            ).fetchall()
            dsa_id = next(
                subject_id for subject_id, in subject_ids
                if connection.execute(
                    "SELECT subject_code FROM subjects WHERE subject_id = ?",
                    (subject_id,),
                ).fetchone()[0] == "DSA"
            )
            python_id = next(
                subject_id for subject_id, in subject_ids
                if connection.execute(
                    "SELECT subject_code FROM subjects WHERE subject_id = ?",
                    (subject_id,),
                ).fetchone()[0] == "PY"
            )
            connection.executemany(
                """INSERT INTO attendance
                   (student_id, subject_id, total_classes, attended_classes)
                   VALUES (?, ?, 10, 9)""",
                [(student_id, dsa_id), (student_id, python_id)],
            )
            connection.executemany(
                """INSERT INTO marks
                   (student_id, subject_id, exam_name, marks_obtained, max_marks)
                   VALUES (?, ?, ?, ?, 100)""",
                [
                    (student_id, dsa_id, "Midterm", 80),
                    (student_id, python_id, "Midterm", 20),
                    (student_id, dsa_id, "End Term", 70),
                    (student_id, python_id, "End Term", 65),
                ],
            )
            connection.commit()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_flags_low_marks_in_any_subject_instead_of_hiding_them_in_total(self):
        summary = get_faculty_summary()
        student = summary["students"][0]

        self.assertIn("Midterm marks below 50%", student["rule_flags"])
        self.assertEqual(
            {
                result["subject_name"]: result["percentage"]
                for result in student["midterm_results"]
            },
            {"Data Structures": 80.0, "Python": 20.0},
        )
        self.assertEqual(summary["low_marks"], 1)


if __name__ == "__main__":
    unittest.main()
