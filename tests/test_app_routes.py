"""Classroom finder and favicon routes, exercised through the app factory.

These pages now require a signed-in user, so each test runs with an
authenticated student. The database-failure test patches ``db.get_connection``
to raise, which is where the route actually opens its connection.
"""

import unittest
from unittest.mock import patch

from tests.support import TempDatabaseMixin

from db.base import DatabaseError


class SignedInMixin(TempDatabaseMixin):
    def setUp(self):
        super().setUp()
        import wsgi

        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()

        # A student account and its academic record.
        import app.auth as auth_module

        fake = auth_module.get_auth()
        user_id = fake.add_user("student@example.com", "secret-pass-1")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO user_profiles (user_id, email, display_name, role) "
                "VALUES (?, 'student@example.com', 'Student', 'student')",
                (user_id,),
            )
            connection.execute(
                "INSERT INTO students (name, email, auth_user_id) "
                "VALUES ('Student', 'student@example.com', ?)",
                (user_id,),
            )
            connection.commit()

        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-token"
        response = self.client.post("/auth/login", data={
            "email": "student@example.com",
            "password": "secret-pass-1",
            "csrf_token": "test-token",
        })
        self.assertIn(response.status_code, (301, 302, 303),
                      "the test fixture must be signed in")
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
            if not token:
                session["csrf_token"] = "test-token"
                token = "test-token"
        self.csrf_token = token

    def post(self, path, data):
        return self.client.post(path, data={**data, "csrf_token": self.csrf_token})


class TestClassroomRoute(SignedInMixin, unittest.TestCase):
    def test_page_loads(self):
        self.assertEqual(self.client.get("/classrooms").status_code, 200)

    def test_end_before_start_shows_error(self):
        response = self.post(
            "/classrooms",
            {"day": "1", "start": "11:00", "end": "10:00"},
        )
        self.assertIn(
            b"Enter a start time that is earlier than the end time.",
            response.data,
        )

    def test_empty_timetable_is_reported_without_suggesting_seed_data(self):
        with patch("app.views.academic_views.find_rooms", return_value=([], None)):
            response = self.post(
                "/classrooms",
                {"day": "1", "start": "10:00", "end": "11:00"},
            )

        self.assertIn(b"No free rooms were found", response.data)
        # Production must never point operators at the destructive demo seeder.
        self.assertNotIn(b"seed_data.py", response.data)

    def test_database_error_does_not_recommend_destructive_seed_as_default(self):
        with patch(
            "app.views.academic_views.find_rooms",
            side_effect=DatabaseError("no such table: timetable"),
        ):
            response = self.post(
                "/classrooms",
                {"day": "1", "start": "10:00", "end": "11:00"},
            )

        self.assertIn(b"Timetable data is not available", response.data)
        self.assertIn(b"migrations", response.data)
        self.assertNotIn(b"seed_data.py", response.data)


class TestFaviconRoute(unittest.TestCase):
    """Browsers always request /favicon.ico; a 404 shows up as a console error."""

    def setUp(self):
        import wsgi

        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def test_favicon_is_not_a_404(self):
        response = self.client.get("/favicon.ico")
        self.assertNotEqual(response.status_code, 404)
        self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
