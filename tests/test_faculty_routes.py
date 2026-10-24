import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import database
import app as app_module


class TestFacultyRoutes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "faculty_routes.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.database_patch.start()
        database.initialize_database()

        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO students (name, email) VALUES (?, ?)",
                ("Existing Student", "existing@example.edu"),
            )
            connection.execute(
                "INSERT INTO subjects (subject_name, subject_code) VALUES (?, ?)",
                ("Data Structures", "DSA"),
            )
            connection.execute(
                """INSERT INTO assessment_items
                   (subject_id, assessment_type, title)
                   VALUES (1, 'assignment', 'Existing Assignment')"""
            )
            connection.execute(
                """INSERT INTO assessment_submissions
                   (assessment_id, student_id, submitted)
                   VALUES (1, 1, 0)"""
            )
            connection.commit()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_new_student_gets_pending_rows_for_existing_assessments(self):
        response = self.client.post("/faculty/manage", data={
            "action": "add_student",
            "name": "New Student",
            "semester": "3",
            "section": "A",
            "email": "new@example.edu",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Student added successfully.", response.data)

        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """SELECT submitted FROM assessment_submissions
                   WHERE assessment_id = 1 AND student_id = 2"""
            ).fetchone()
        self.assertEqual(row, (0,))

    def test_invalid_attendance_is_not_saved(self):
        response = self.client.post("/faculty/manage", data={
            "action": "save_attendance",
            "student_id": "1",
            "subject_id": "1",
            "total_classes": "0",
            "attended_classes": "0",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        self.assertEqual(count, 0)

    def test_saving_same_exam_again_updates_existing_marks(self):
        form = {
            "action": "save_marks",
            "student_id": "1",
            "subject_id": "1",
            "exam_name": "Midterm",
            "max_marks": "100",
        }
        self.client.post("/faculty/manage", data={**form, "marks_obtained": "45"})
        response = self.client.post(
            "/faculty/manage", data={**form, "marks_obtained": "72"}
        )
        self.assertEqual(response.status_code, 200)

        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """SELECT marks_obtained FROM marks
                   WHERE student_id = 1 AND subject_id = 1 AND exam_name = 'Midterm'"""
            ).fetchall()
        self.assertEqual(rows, [(72.0,)])

    def test_new_assessment_creates_pending_rows_for_all_students(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO students (name, email) VALUES (?, ?)",
                ("Second Student", "second@example.edu"),
            )
            connection.commit()

        response = self.client.post("/faculty/manage", data={
            "action": "create_assessment",
            "subject_id": "1",
            "assessment_type": "term_work",
            "title": "Lab Record",
            "due_date": "",
        })
        self.assertEqual(response.status_code, 200)

        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """SELECT student_id, submitted FROM assessment_submissions
                   WHERE assessment_id = 2 ORDER BY student_id"""
            ).fetchall()
        self.assertEqual(rows, [(1, 0), (2, 0)])


    def test_edit_student_updates_existing_record(self):
        response = self.client.post("/faculty/manage", data={
            "action": "edit_student",
            "student_id": "1",
            "name": "Updated Student",
            "semester": "4",
            "section": "B",
            "email": "updated@example.edu",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT name, semester, section FROM students WHERE student_id = 1"
            ).fetchone()
        self.assertEqual(row, ("Updated Student", 4, "B"))

    def test_subject_can_be_added(self):
        response = self.client.post("/faculty/manage", data={
            "action": "create_subject",
            "subject_name": "Database Systems",
            "subject_code": "DBMS",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT subject_name FROM subjects WHERE subject_code = 'DBMS'"
            ).fetchone()
        self.assertEqual(row, ("Database Systems",))

    def test_submission_status_can_be_updated(self):
        response = self.client.post("/faculty/manage", data={
            "action": "save_submission",
            "assessment_id": "1",
            "student_id": "1",
            "submitted": "1",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """SELECT submitted FROM assessment_submissions
                   WHERE assessment_id = 1 AND student_id = 1"""
            ).fetchone()
        self.assertEqual(row, (1,))


if __name__ == "__main__":
    unittest.main()
