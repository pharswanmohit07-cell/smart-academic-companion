"""Admin workspace routing and navigation regression tests."""

import unittest

from tests.test_auth_authorization import AppTestBase


class TestAdminWorkspaceRouting(AppTestBase, unittest.TestCase):
    def test_dashboard_endpoint_resolves_each_role_separately(self):
        from app.auth import dashboard_endpoint
        from app.accounts import Account

        admin = Account("admin-id", "admin@example.com", "Admin", "admin")
        faculty = Account("faculty-id", "faculty@example.com", "Faculty", "faculty")
        student = Account("student-id", "student@example.com", "Student", "student", student_id=1)

        self.assertEqual(dashboard_endpoint(admin), "faculty.admin_dashboard")
        self.assertEqual(dashboard_endpoint(faculty), "faculty.dashboard")
        self.assertEqual(dashboard_endpoint(student), "student.dashboard")

    def test_admin_dashboard_requires_sign_in(self):
        response = self.client.get("/faculty/admin", follow_redirects=False)
        self.assertIn(response.status_code, (301, 302, 303))

    def test_admin_dashboard_is_admin_only(self):
        self.make_profile("admin@example.com", role="admin")
        self.make_teacher("faculty@example.com")
        self.make_student("student@example.com", "Student One")

        self.as_user("admin@example.com")
        response = self.client.get("/faculty/admin")
        self.assertEqual(response.status_code, 200)

        self.client = self.app.test_client()
        self.as_user("faculty@example.com")
        self.assertEqual(self.client.get("/faculty/admin").status_code, 403)

        self.client = self.app.test_client()
        self.as_user("student@example.com")
        self.assertEqual(self.client.get("/faculty/admin").status_code, 403)

    def test_navigation_exposes_only_the_links_allowed_for_each_role(self):
        self.make_profile("admin@example.com", role="admin")
        self.make_teacher("faculty@example.com")
        self.make_student("student@example.com", "Student One")

        self.as_user("admin@example.com")
        admin_page = self.client.get("/faculty/admin").data
        for label in (b"Faculty Dashboard", b"Manage Records", b"Manage Classes", b"Users"):
            self.assertIn(label, admin_page)

        self.client = self.app.test_client()
        self.as_user("faculty@example.com")
        faculty_page = self.client.get("/faculty/dashboard").data
        self.assertIn(b"Faculty Dashboard", faculty_page)
        self.assertIn(b"Manage Records", faculty_page)
        self.assertNotIn(b">Users</a>", faculty_page)

        self.client = self.app.test_client()
        self.as_user("student@example.com")
        student_page = self.client.get("/student/dashboard").data
        for label in (b"Faculty Dashboard", b"Manage Records", b"Manage Classes", b">Users</a>"):
            self.assertNotIn(label, student_page)


class TestAdminUserDirectory(AppTestBase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.admin_id = self.make_profile("admin@example.com", role="admin")
        self.student_id, self.student_record_id = self.make_student(
            "learner@example.com", "Learner One"
        )
        self.faculty_id, self.teacher_record_id = self.make_teacher(
            "teacher@example.com", "Teacher One"
        )
        self.as_user("admin@example.com")

    def test_users_directory_searches_name_and_email(self):
        response = self.client.get("/faculty/admin/users?q=learner")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"learner@example.com", response.data)
        self.assertNotIn(b"teacher@example.com", response.data)

        response = self.client.get("/faculty/admin/users?q=teacher%40example.com")
        self.assertIn(b"teacher@example.com", response.data)
        self.assertNotIn(b"learner@example.com", response.data)

    def test_users_directory_filters_by_role_and_invalid_filter_falls_back(self):
        response = self.client.get("/faculty/admin/users?role=faculty")
        self.assertIn(b"teacher@example.com", response.data)
        self.assertNotIn(b"learner@example.com", response.data)
        response = self.client.get("/faculty/admin/users?role=invalid")
        self.assertIn(b"learner@example.com", response.data)
        self.assertIn(b"teacher@example.com", response.data)

    def test_student_to_faculty_links_teacher_and_demotes_back_safely(self):
        response = self.submit(
            "/faculty/admin/set-role",
            {"email": "learner@example.com", "role": "faculty"},
            page="/faculty/admin/users",
            visible=True,
        )
        self.assertEqual(response.status_code, 200)
        with self.connect() as connection:
            profile = connection.execute(
                "SELECT role FROM user_profiles WHERE user_id = ?", (self.student_id,)
            ).fetchone()
            teacher = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (self.student_id,)
            ).fetchone()
        self.assertEqual(profile["role"], "faculty")
        self.assertIsNotNone(teacher)

        response = self.submit(
            "/faculty/admin/set-role",
            {"email": "learner@example.com", "role": "student"},
            page="/faculty/admin/users",
            visible=True,
        )
        self.assertEqual(response.status_code, 200)
        with self.connect() as connection:
            profile = connection.execute(
                "SELECT role FROM user_profiles WHERE user_id = ?", (self.student_id,)
            ).fetchone()
            teacher = connection.execute(
                "SELECT teacher_id, auth_user_id FROM teachers WHERE teacher_id = ?",
                (teacher["teacher_id"],),
            ).fetchone()
        self.assertEqual(profile["role"], "student")
        self.assertIsNone(teacher["auth_user_id"])

    def test_admin_cannot_change_self_or_another_admin(self):
        other_admin = self.make_profile("other-admin@example.com", role="admin")
        for email in ("admin@example.com", "other-admin@example.com"):
            with self.subTest(email=email):
                self.submit(
                    "/faculty/admin/set-role",
                    {"email": email, "role": "faculty"},
                    page="/faculty/admin/users",
                    visible=True,
                )
        with self.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT role FROM user_profiles WHERE user_id = ?", (self.admin_id,)
                ).fetchone()["role"],
                "admin",
            )
            self.assertEqual(
                connection.execute(
                    "SELECT role FROM user_profiles WHERE user_id = ?", (other_admin,)
                ).fetchone()["role"],
                "admin",
            )

    def test_role_change_requires_supported_target_role_and_csrf(self):
        response = self.client.post(
            "/faculty/admin/set-role",
            data={"email": "learner@example.com", "role": "admin"},
        )
        self.assertIn(response.status_code, (400, 403))
        with self.connect() as connection:
            role = connection.execute(
                "SELECT role FROM user_profiles WHERE user_id = ?", (self.student_id,)
            ).fetchone()["role"]
        self.assertEqual(role, "student")

    def test_faculty_and_student_cannot_open_admin_users(self):
        self.client = self.app.test_client()
        self.as_user("teacher@example.com")
        self.assertEqual(self.client.get("/faculty/admin/users").status_code, 403)
        self.client = self.app.test_client()
        self.as_user("learner@example.com")
        self.assertEqual(self.client.get("/faculty/admin/users").status_code, 403)


if __name__ == "__main__":
    unittest.main()
