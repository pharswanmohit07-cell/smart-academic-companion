import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import database

from tests.support import FakeAuthState


class TestFacultyRoutes(unittest.TestCase):
    """Record management through the faculty blueprint, as a signed-in owner.

    Every request is made the way a browser makes it: the page is rendered
    first (which stores the CSRF token in the session) and the POST carries
    that token. Classroom ownership is what authorizes the writes.
    """

    FACULTY_EMAIL = "faculty@example.edu"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "faculty_routes.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        database.initialize_database()

        import wsgi

        self.fake = FakeAuthState.current
        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)

        self.user_id = self.fake.add_user(self.FACULTY_EMAIL, "secret-pass-1")
        self.model_patch = None
        self._register_faculty()
        self.client = self.app.test_client()
        self._sign_in()

    def _register_faculty(self):
        """A profile, a teacher row and a class owned by that teacher."""
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            # The local SQLite build has no auth.users trigger; create the
            # profile table it would populate (same columns as Supabase).
            from tests.support import USER_PROFILES_DDL

            connection.executescript(USER_PROFILES_DDL)
            connection.execute(
                "INSERT INTO teachers (auth_user_id, name, email) VALUES (?, ?, ?)",
                (self.user_id, "Faculty Owner", self.FACULTY_EMAIL),
            )
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section, description, owner_teacher_id)
                   VALUES ('Owned Class', 'BCA AI & DS', 3, 'A', '', 1)"""
            )
            connection.execute(
                "INSERT INTO students (name, email, class_id) VALUES (?, ?, 1)",
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

        # The deployed profile row is created by the auth trigger; here the
        # app's own accessor is given the equivalent row.
        self._profile_patch = patch(
            "app.auth.load_account",
            side_effect=self._load_account,
        )
        self._profile_patch.start()
        self.addCleanup(self._profile_patch.stop)

    def _load_account(self, user_id, email="", display_name=""):
        from app.accounts import Account

        with closing(sqlite3.connect(self.db_path)) as connection:
            teacher = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
            ).fetchone()
        return Account(
            user_id=user_id,
            email=self.FACULTY_EMAIL,
            display_name="Faculty Owner",
            role="faculty",
            teacher_id=teacher[0] if teacher else None,
        )

    def _sign_in(self):
        self.client.get("/auth/login")
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
        response = self.client.post("/auth/login", data={
            "email": self.FACULTY_EMAIL,
            "password": "secret-pass-1",
            "csrf_token": token,
        })
        self.assertIn(response.status_code, (301, 302, 303))

    def post(self, path, data, page=None):
        self.client.get(page or path)
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
        return self.client.post(path, data={**data, "csrf_token": token})

    def tearDown(self):
        pass  # cleanup is registered with addCleanup in setUp

    def test_new_student_gets_pending_rows_for_existing_assessments(self):
        response = self.post("/faculty/manage", {
            "action": "add_student",
            "class_id": "1",
            "name": "New Student",
            "semester": "3",
            "section": "A",
            "email": "new@example.edu",
        })
        self.assertEqual(response.status_code, 302)

        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """SELECT ss.submitted
                     FROM assessment_submissions AS ss
                     JOIN students AS s ON s.student_id = ss.student_id
                    WHERE ss.assessment_id = 1 AND s.email = 'new@example.edu'"""
            ).fetchone()
        self.assertEqual(row, (0,))

    def test_invalid_attendance_is_not_saved(self):
        response = self.post("/faculty/manage", {
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
        self.client.get("/faculty/manage")
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
        self.client.post("/faculty/manage", data={**form, "marks_obtained": "45",
                                                   "csrf_token": token})
        response = self.client.post(
            "/faculty/manage", data={**form, "marks_obtained": "72", "csrf_token": token}
        )
        self.assertEqual(response.status_code, 302)

        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """SELECT marks_obtained FROM marks
                   WHERE student_id = 1 AND subject_id = 1 AND exam_name = 'Midterm'"""
            ).fetchall()
        self.assertEqual(rows, [(72.0,)])


    def test_marks_above_maximum_are_not_saved(self):
        response = self.post("/faculty/manage", {
            "action": "save_marks",
            "student_id": "1",
            "subject_id": "1",
            "exam_name": "Midterm",
            "marks_obtained": "101",
            "max_marks": "100",
        })
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM marks WHERE student_id = 1"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_duplicate_assessment_is_rejected_without_duplicate_rows(self):
        response = self.post("/faculty/manage", {
            "action": "create_assessment",
            "subject_id": "1",
            "assessment_type": "assignment",
            "title": "Existing Assignment",
            "due_date": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"That assessment title already exists", response.data)
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM assessment_items WHERE title = 'Existing Assignment'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_new_assessment_creates_pending_rows_for_all_students(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO students (name, email, class_id) VALUES (?, ?, 1)",
                ("Second Student", "second@example.edu"),
            )
            connection.commit()

        response = self.post("/faculty/manage", {
            "action": "create_assessment",
            "subject_id": "1",
            "assessment_type": "term_work",
            "title": "Lab Record",
            "due_date": "",
        })
        self.assertEqual(response.status_code, 302)

        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """SELECT student_id, submitted FROM assessment_submissions
                   WHERE assessment_id = (
                       SELECT assessment_id FROM assessment_items
                        WHERE title = 'Lab Record')
                   ORDER BY student_id"""
            ).fetchall()
        # One pending row per existing student (the student added earlier in
        # this test included).
        self.assertEqual([student_id for student_id, _ in rows], [1, 2, 3])
        self.assertEqual({submitted for _, submitted in rows}, {0})


    def test_edit_student_updates_existing_record(self):
        response = self.post("/faculty/manage", {
            "action": "edit_student",
            "student_id": "1",
            "name": "Updated Student",
            "semester": "4",
            "section": "B",
            "email": "updated@example.edu",
        })
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT name, semester, section FROM students WHERE student_id = 1"
            ).fetchone()
        self.assertEqual(row, ("Updated Student", 4, "B"))

    def test_subject_can_be_added(self):
        response = self.post("/faculty/manage", {
            "action": "create_subject",
            "subject_name": "Database Systems",
            "subject_code": "DBMS",
        })
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT subject_name FROM subjects WHERE subject_code = 'DBMS'"
            ).fetchone()
        self.assertEqual(row, ("Database Systems",))

    def test_submission_status_can_be_updated(self):
        response = self.post("/faculty/manage", {
            "action": "save_submission",
            "assessment_id": "1",
            "student_id": "1",
            "submitted": "1",
        })
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """SELECT submitted FROM assessment_submissions
                   WHERE assessment_id = 1 AND student_id = 1"""
            ).fetchone()
        self.assertEqual(row, (1,))


if __name__ == "__main__":
    unittest.main()
