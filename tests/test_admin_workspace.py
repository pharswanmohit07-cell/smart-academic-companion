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


if __name__ == "__main__":
    unittest.main()
