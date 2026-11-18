import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app as app_module
import database
from modules.faculty_dashboard import get_assessment_overview


class TestClassManagement(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "classes.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.database_patch.start()
        database.initialize_database()
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_new_student_is_assigned_to_matching_default_class(self):
        response = self.client.post("/faculty/manage", data={
            "action": "add_student",
            "name": "New Student",
            "semester": "3",
            "section": "A",
            "email": "new@example.edu",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """SELECT s.class_id, c.class_name
                   FROM students s LEFT JOIN faculty_classes c
                   ON c.class_id = s.class_id WHERE s.name = ?""",
                ("New Student",),
            ).fetchone()
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], "BCA AI & DS - Sem 3 - Section A")

    def test_editing_semester_and_section_reassigns_default_class(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO students (name, semester, section) VALUES ('Student', 3, 'A')"
            )
            conn.commit()
        database.initialize_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            old_class = conn.execute(
                "SELECT class_id FROM students WHERE student_id = 1"
            ).fetchone()[0]

        response = self.client.post("/faculty/manage", data={
            "action": "edit_student",
            "student_id": "1",
            "name": "Student",
            "semester": "4",
            "section": "B",
            "email": "",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT semester, section, class_id FROM students WHERE student_id = 1"
            ).fetchone()
            class_name = conn.execute(
                "SELECT class_name FROM faculty_classes WHERE class_id = ?",
                (row[2],),
            ).fetchone()[0]
        self.assertEqual(row[:2], (4, "B"))
        self.assertNotEqual(row[2], old_class)
        self.assertEqual(class_name, "BCA AI & DS - Sem 4 - Section B")

    def test_moving_student_changes_only_class_id(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO faculty_classes (class_name, program, semester, section) VALUES ('Target Class', 'Other Program', 5, 'C')"
            )
            conn.execute(
                "INSERT INTO students (name, semester, section) VALUES ('Student', 3, 'A')"
            )
            conn.commit()
        response = self.client.post("/faculty/classes", data={
            "action": "move_student",
            "student_id": "1",
            "class_id": "1",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT semester, section, class_id FROM students WHERE student_id = 1"
            ).fetchone()
        self.assertEqual(row, (3, "A", 1))

    def test_legacy_class_is_renamed_and_migration_is_idempotent(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO faculty_classes
                   (class_name, program, semester, section)
                   VALUES ('Existing Demo - Semester 3 - Section A',
                           'Existing Demo', 3, 'A')"""
            )
            conn.execute(
                "INSERT INTO students (name, semester, section, class_id) VALUES ('Student', 3, 'A', 1)"
            )
            conn.commit()
        database.initialize_database()
        database.initialize_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            classes = conn.execute(
                "SELECT class_name FROM faculty_classes"
            ).fetchall()
            student = conn.execute(
                "SELECT class_id FROM students WHERE student_id = 1"
            ).fetchone()
        self.assertEqual(classes, [("BCA AI & DS - Sem 3 - Section A",)])
        self.assertEqual(student, (1,))

    def test_assessment_overview_respects_class_filter(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO faculty_classes (class_name, program, semester, section) VALUES ('Class A', 'Program', 3, 'A')"
            )
            conn.execute(
                "INSERT INTO faculty_classes (class_name, program, semester, section) VALUES ('Class B', 'Program', 3, 'B')"
            )
            conn.execute(
                "INSERT INTO students (name, semester, section, class_id) VALUES ('A Student', 3, 'A', 1)"
            )
            conn.execute(
                "INSERT INTO students (name, semester, section, class_id) VALUES ('B Student', 3, 'B', 2)"
            )
            conn.execute(
                "INSERT INTO subjects (subject_name) VALUES ('Data Structures')"
            )
            conn.execute(
                """INSERT INTO assessment_items
                   (subject_id, assessment_type, title)
                   VALUES (1, 'assignment', 'Lab Work')"""
            )
            conn.execute(
                "INSERT INTO assessment_submissions (assessment_id, student_id, submitted) VALUES (1, 1, 1)"
            )
            conn.commit()
        overview = get_assessment_overview(class_id=1)
        self.assertEqual(len(overview), 1)
        self.assertEqual(overview[0]["total_students"], 1)
        self.assertEqual(overview[0]["submitted_count"], 1)

    def test_invalid_class_filter_does_not_crash_dashboard(self):
        response = self.client.get("/risk?class_id=not-a-number")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_class_name_shows_specific_message(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO faculty_classes (class_name, program, semester, section) VALUES ('Class A', 'Program', 3, 'A')"
            )
            conn.commit()
        response = self.client.post("/faculty/classes", data={
            "action": "create_class",
            "class_name": "Class A",
            "program": "Program",
            "semester": "3",
            "section": "A",
            "description": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"That class name already exists", response.data)


if __name__ == "__main__":
    unittest.main()
