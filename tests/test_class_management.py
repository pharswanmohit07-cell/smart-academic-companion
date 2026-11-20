"""Class management behaviour, ported to the app factory and class ownership.

Coverage preserved from the original file:

* legacy placeholder classes are renamed once and the migration is idempotent
* the assessment overview honours a class filter
* moving a student between owned classes changes only ``class_id``
* a duplicate class name shows a specific message
* an invalid class filter does not crash the dashboard

Two original tests asserted behaviour the authorization model deliberately
removed: adding or editing a student used to auto-create/auto-assign the
matching "BCA AI & DS - Sem N - Section X" class. Faculty may now only add
students to a class they own, so those tests are expressed as their real
invariants instead (see the two ``*_requires_owned_class`` tests).
"""

import unittest

from tests.support import FakeAuthState, TempDatabaseMixin

import database


class ClassManagementBase(TempDatabaseMixin):
    def setUp(self):
        super().setUp()
        import wsgi

        self.fake = FakeAuthState.current
        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()
        self.csrf_token = "class-management-token"

    # -- fixtures --------------------------------------------------------
    def make_faculty(self, email="faculty@example.com", password="secret-pass-1"):
        """Create a faculty login with a teacher row and sign the client in."""
        user_id = self.fake.add_user(email, password)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO user_profiles (user_id, email, display_name, role) "
                "VALUES (?, ?, 'Faculty', 'faculty')",
                (user_id, email),
            )
            connection.execute(
                "INSERT INTO teachers (auth_user_id, name, email) VALUES (?, 'Faculty', ?)",
                (user_id, email),
            )
            connection.commit()
            teacher_id = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
            ).fetchone()["teacher_id"]

        with self.client.session_transaction() as session:
            session["csrf_token"] = self.csrf_token
        response = self.client.post("/auth/login", data={
            "email": email, "password": password, "csrf_token": self.csrf_token,
        })
        self.assertIn(response.status_code, (301, 302, 303),
                      "the faculty fixture must be signed in")
        with self.client.session_transaction() as session:
            if not session.get("csrf_token"):
                session["csrf_token"] = self.csrf_token
        return teacher_id

    def make_class(self, name, owner_teacher_id=None, program="Program", semester=3,
                   section="A"):
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section, description,
                        owner_teacher_id)
                   VALUES (?, ?, ?, ?, '', ?)""",
                (name, program, semester, section, owner_teacher_id),
            )
            connection.commit()
            return connection.execute(
                "SELECT class_id FROM faculty_classes WHERE class_name = ?", (name,)
            ).fetchone()["class_id"]

    def make_student(self, name, class_id=None, semester=3, section="A"):
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO students (name, semester, section, class_id)
                   VALUES (?, ?, ?, ?)""",
                (name, semester, section, class_id),
            )
            connection.commit()
            return connection.execute(
                "SELECT student_id FROM students WHERE name = ?", (name,)
            ).fetchone()["student_id"]

    def post(self, path, data):
        return self.client.post(path, data={**data, "csrf_token": self.csrf_token})


class TestClassManagement(ClassManagementBase, unittest.TestCase):
    # -- backend-only behaviour -----------------------------------------
    def test_legacy_class_is_renamed_and_migration_is_idempotent(self):
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section)
                   VALUES ('Existing Demo - Semester 3 - Section A',
                           'Existing Demo', 3, 'A')"""
            )
            connection.execute(
                "INSERT INTO students (name, semester, section, class_id) "
                "VALUES ('Student', 3, 'A', 1)"
            )
            connection.commit()

        database.initialize_database()
        database.initialize_database()       # second run must be a no-op

        with self.connect() as connection:
            classes = connection.execute(
                "SELECT class_name FROM faculty_classes").fetchall()
            student = connection.execute(
                "SELECT class_id FROM students WHERE student_id = 1").fetchone()
        self.assertEqual([row["class_name"] for row in classes],
                         ["BCA AI & DS - Sem 3 - Section A"])
        self.assertEqual(student["class_id"], 1)

    def test_assessment_overview_respects_class_filter(self):
        from modules.faculty_dashboard import get_assessment_overview

        class_a = self.make_class("Class A")
        self.make_class("Class B")
        self.make_student("A Student", class_id=class_a)
        self.make_student("B Student", class_id=2)
        with self.connect() as connection:
            connection.execute("INSERT INTO subjects (subject_name) VALUES ('Data Structures')")
            connection.execute(
                """INSERT INTO assessment_items (subject_id, assessment_type, title)
                   VALUES (1, 'assignment', 'Lab Work')"""
            )
            connection.execute(
                """INSERT INTO assessment_submissions
                       (assessment_id, student_id, submitted) VALUES (1, 1, 1)"""
            )
            connection.commit()

        overview = get_assessment_overview(class_id=class_a)
        self.assertEqual(len(overview), 1)
        self.assertEqual(overview[0]["total_students"], 1)
        self.assertEqual(overview[0]["submitted_count"], 1)

    # -- route behaviour -------------------------------------------------
    def test_moving_student_changes_only_class_id(self):
        teacher_id = self.make_faculty()
        target = self.make_class("Target Class", teacher_id, program="Other Program",
                                 semester=5, section="C")
        source = self.make_class("Source Class", teacher_id)
        student_id = self.make_student("Student", class_id=source)

        response = self.post("/faculty/classes", {
            "action": "move_student",
            "student_id": str(student_id),
            "class_id": str(target),
        })
        self.assertIn(response.status_code, (200, 302))

        with self.connect() as connection:
            row = connection.execute(
                "SELECT semester, section, class_id FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
        # Moving a student never rewrites their semester or section.
        self.assertEqual((row["semester"], row["section"], row["class_id"]),
                         (3, "A", target))

    def test_duplicate_class_name_shows_specific_message(self):
        teacher_id = self.make_faculty()
        self.make_class("Class A", teacher_id)

        response = self.post("/faculty/classes", {
            "action": "create_class",
            "class_name": "Class A",
            "program": "Program",
            "semester": "3",
            "section": "A",
            "description": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"That class name already exists", response.data)

    def test_invalid_class_filter_does_not_crash_dashboard(self):
        self.make_faculty()
        response = self.client.get("/faculty/dashboard?class_id=not-a-number")
        self.assertEqual(response.status_code, 200)

    # -- authorization invariants (replace auto-class-assignment) --------
    def test_adding_a_student_requires_an_owned_class(self):
        teacher_id = self.make_faculty()
        owned = self.make_class("Owned Class", teacher_id)
        foreign = self.make_class("Foreign Class")

        # A class this faculty does not own is refused.
        response = self.post("/faculty/manage", {
            "action": "add_student", "class_id": str(foreign), "name": "Nope",
            "semester": "3", "section": "A", "email": "",
        })
        self.assertEqual(response.status_code, 403)

        # A class the faculty owns accepts the student, with no name rewriting.
        response = self.post("/faculty/manage", {
            "action": "add_student", "class_id": str(owned), "name": "New Student",
            "semester": "3", "section": "A", "email": "new@example.edu",
        })
        self.assertIn(response.status_code, (200, 302))
        with self.connect() as connection:
            row = connection.execute(
                """SELECT s.class_id, c.class_name
                     FROM students s JOIN faculty_classes c ON c.class_id = s.class_id
                    WHERE s.name = 'New Student'"""
            ).fetchone()
        self.assertEqual(row["class_name"], "Owned Class")

    def test_editing_a_student_cannot_move_them_into_an_unowned_class(self):
        teacher_id = self.make_faculty()
        owned = self.make_class("Owned Class", teacher_id)
        self.make_class("Foreign Class")
        student_id = self.make_student("Student", class_id=owned)

        response = self.post("/faculty/manage", {
            "action": "edit_student", "student_id": str(student_id),
            "name": "Student", "semester": "4", "section": "B", "email": "",
        })
        self.assertIn(response.status_code, (200, 302))

        with self.connect() as connection:
            row = connection.execute(
                "SELECT semester, section, class_id FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
        self.assertEqual((row["semester"], row["section"]), (4, "B"))
        # A semester/section change unassigns the class rather than silently
        # creating a new one the faculty would not own.
        self.assertIsNone(row["class_id"])


if __name__ == "__main__":
    unittest.main()
