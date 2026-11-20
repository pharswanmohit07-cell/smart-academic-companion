"""End-to-end proof of the data-isolation rules, across both enforcement layers.

Each test drives real HTTP requests through the app factory and then reads the
database directly, so it proves the *outcome* (no cross-class or cross-student
data reached, no foreign record changed) rather than the presence of a decorator.

Layer 1 (Python): route guards + ownership checks in ``app/auth.py``.
Layer 2 (RLS): the policies in ``migrations/0003`` restrict the same tables when
a client talks to the database directly. Those policies are reviewed statically
in ``tests/test_database_layer.py``; they cannot be executed without PostgreSQL.
"""

import unittest

from tests.support import FakeAuthState, TempDatabaseMixin


class IsolationBase(TempDatabaseMixin):
    def setUp(self):
        super().setUp()
        import wsgi

        self.fake = FakeAuthState.current
        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()
        self.csrf_token = "isolation-token"

        # Two faculty, each owning one class, each with one student.
        self.teacher_a, self.class_a = self._faculty_with_class("a@example.com", "Class A")
        self.teacher_b, self.class_b = self._faculty_with_class("b@example.com", "Class B")
        self.student_a = self._student("Alice", self.class_a, "alice@example.com")
        self.student_b = self._student("Bob", self.class_b, "bob@example.com")
        with self.connect() as connection:
            connection.execute("INSERT INTO subjects (subject_name) VALUES ('Networks')")
            connection.commit()

    def _faculty_with_class(self, email, class_name):
        user_id = self.fake.add_user(email, "secret-pass-1")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO user_profiles (user_id, email, display_name, role) "
                "VALUES (?, ?, 'Teacher', 'faculty')", (user_id, email))
            connection.execute(
                "INSERT INTO teachers (auth_user_id, name, email) VALUES (?, 'T', ?)",
                (user_id, email))
            connection.commit()
            teacher_id = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
            ).fetchone()["teacher_id"]
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section, description,
                        owner_teacher_id)
                   VALUES (?, 'P', 3, 'A', '', ?)""", (class_name, teacher_id))
            connection.commit()
            class_id = connection.execute(
                "SELECT class_id FROM faculty_classes WHERE class_name = ?", (class_name,)
            ).fetchone()["class_id"]
        return teacher_id, class_id

    def _student(self, name, class_id, email=None):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO students (name, email, class_id) VALUES (?, ?, ?)",
                (name, email, class_id))
            connection.commit()
            return connection.execute(
                "SELECT student_id FROM students WHERE name = ?", (name,)
            ).fetchone()["student_id"]

    def sign_in(self, email):
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["csrf_token"] = self.csrf_token
        response = self.client.post("/auth/login", data={
            "email": email, "password": "secret-pass-1",
            "csrf_token": self.csrf_token})
        self.assertIn(response.status_code, (301, 302, 303), f"sign-in failed for {email}")
        with self.client.session_transaction() as session:
            if not session.get("csrf_token"):
                session["csrf_token"] = self.csrf_token

    def post(self, path, data):
        return self.client.post(path, data={**data, "csrf_token": self.csrf_token})

    def attendance_rows(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT student_id, attended_classes FROM attendance").fetchall()]


class TestFacultyClassIsolation(IsolationBase, unittest.TestCase):
    def test_faculty_dashboard_lists_only_owned_students(self):
        self.sign_in("a@example.com")
        body = self.client.get("/faculty/dashboard").data
        self.assertIn(b"Alice", body)
        self.assertNotIn(b"Bob", body)

    def test_faculty_cannot_open_an_unassigned_class(self):
        self.sign_in("a@example.com")
        for path in (f"/faculty/dashboard?class_id={self.class_b}",
                     f"/faculty/classes?class_id={self.class_b}"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_faculty_can_open_their_own_class(self):
        self.sign_in("a@example.com")
        response = self.client.get(f"/faculty/dashboard?class_id={self.class_a}")
        self.assertEqual(response.status_code, 200)

    def test_faculty_cannot_write_marks_for_another_class(self):
        self.sign_in("a@example.com")
        response = self.post("/faculty/manage", {
            "action": "save_marks", "student_id": str(self.student_b),
            "subject_id": "1", "exam_name": "Midterm",
            "marks_obtained": "99", "max_marks": "100"})
        self.assertEqual(response.status_code, 403)
        with self.connect() as connection:
            self.assertIsNone(connection.execute("SELECT 1 AS found FROM marks").fetchone())

    def test_authorization_is_checked_before_field_validation(self):
        """A foreign student ID is refused even with a malformed body."""
        self.sign_in("a@example.com")
        response = self.post("/faculty/manage", {
            "action": "save_attendance", "student_id": str(self.student_b),
            "subject_id": "not-a-number", "total_classes": "",
            "attended_classes": ""})
        self.assertEqual(response.status_code, 403)

    def test_faculty_cannot_move_a_student_into_a_class_they_do_not_own(self):
        self.sign_in("a@example.com")
        response = self.post("/faculty/classes", {
            "action": "move_student", "student_id": str(self.student_a),
            "class_id": str(self.class_b)})
        self.assertEqual(response.status_code, 403)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT class_id FROM students WHERE student_id = ?",
                (self.student_a,)).fetchone()
        self.assertEqual(row["class_id"], self.class_a)

    def test_faculty_own_class_write_succeeds(self):
        self.sign_in("a@example.com")
        response = self.post("/faculty/manage", {
            "action": "save_attendance", "student_id": str(self.student_a),
            "subject_id": "1", "total_classes": "10", "attended_classes": "9"})
        self.assertIn(response.status_code, (200, 302))
        rows = self.attendance_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["student_id"], self.student_a)


class TestStudentIsolation(IsolationBase, unittest.TestCase):
    def _sign_in_student(self, email):
        user_id = self.fake.add_user(email, "secret-pass-1")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO user_profiles (user_id, email, display_name, role) "
                "VALUES (?, ?, 'Student', 'student')", (user_id, email))
            connection.execute(
                "UPDATE students SET auth_user_id = ? WHERE email = ?", (user_id, email))
            connection.commit()
        self.sign_in(email)

    def test_student_dashboard_shows_only_own_records(self):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO attendance (student_id, subject_id, total_classes, "
                "attended_classes) VALUES (?, 1, 10, 7)", (self.student_a,))
            connection.commit()
        self._sign_in_student("alice@example.com")
        body = self.client.get("/student/dashboard").data
        self.assertIn(b"Alice", body)
        self.assertNotIn(b"Bob", body)
        self.assertIn(b"70.0%", body)

    def test_student_cannot_reach_any_faculty_route(self):
        self._sign_in_student("alice@example.com")
        for path in ("/faculty/dashboard", "/faculty/manage", "/faculty/classes",
                     "/faculty/admin/users"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_student_cannot_write_attendance_even_for_themselves(self):
        self._sign_in_student("alice@example.com")
        response = self.post("/faculty/manage", {
            "action": "save_attendance", "student_id": str(self.student_a),
            "subject_id": "1", "total_classes": "10", "attended_classes": "10"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.attendance_rows(), [])

    def test_student_risk_scope_is_their_own_class_only(self):
        from modules import risk_model

        # Complete records so the loader has something to return for each scope.
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO assessment_items (subject_id, assessment_type, title) "
                "VALUES (1, 'assignment', 'A1')")
            assessment_id = connection.execute(
                "SELECT MAX(assessment_id) AS id FROM assessment_items"
            ).fetchone()["id"]
            for student_id in (self.student_a, self.student_b):
                connection.execute(
                    "INSERT INTO attendance (student_id, subject_id, total_classes, "
                    "attended_classes) VALUES (?, 1, 10, 8)", (student_id,))
                connection.execute(
                    "INSERT INTO marks (student_id, subject_id, exam_name, "
                    "marks_obtained, max_marks) VALUES (?, 1, 'Midterm', 70, 100)",
                    (student_id,))
                connection.execute(
                    "INSERT INTO assessment_submissions (assessment_id, student_id, "
                    "submitted) VALUES (?, ?, 1)", (assessment_id, student_id))
            connection.commit()

        self.assertEqual(risk_model._load_student_data([self.class_b])['name'].tolist(),
                         ['Bob'])
        self.assertEqual(risk_model._load_student_data([self.class_a])['name'].tolist(),
                         ['Alice'])
        self.assertEqual(len(risk_model._load_student_data()), 2)


if __name__ == "__main__":
    unittest.main()
