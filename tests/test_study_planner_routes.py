import unittest
from unittest.mock import patch

from tests.support import TempDatabaseMixin, FakeAuthState


class SignedInClientMixin(TempDatabaseMixin):
    """A test client already signed in as a student (the page under test only
    needs any authenticated user)."""

    def setUp(self):
        super().setUp()
        import app.auth as auth_module
        import wsgi
        from app.accounts import Account

        self.original_load_account = auth_module.load_account
        self.student = Account("test-student", "student@example.edu", "Student",
                               "student", student_id=1)
        auth_module.load_account = lambda user_id, email="", display_name="": self.student
        self.addCleanup(setattr, auth_module, "load_account", self.original_load_account)

        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()
        self.sign_in()

    def sign_in(self):
        self.client.get("/auth/login")
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
            session["csrf_token"] = token or "test-token"
            session["account"] = self.student.to_session()
            session["signed_in_at"] = __import__("time").time()
            session["refreshed_at"] = __import__("time").time()

    def post(self, path, data):
        self.client.get(path)
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
        return self.client.post(path, data={**data, "csrf_token": token})


class TestStudyPlannerPage(SignedInClientMixin, unittest.TestCase):

    def test_page_loads(self):
        response = self.client.get("/study-planner")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI Study Planner", response.data)
        self.assertIn(b"Generate Study Plan", response.data)

    def test_home_and_navigation_link_to_planner(self):
        home = self.client.get("/dashboard", follow_redirects=True)
        self.assertIn(home.status_code, (200, 302))
        page = self.client.get("/student/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"/study-planner", page.data)
        self.assertIn(b"Study Planner", page.data)

    def test_valid_plan_is_generated(self):
        response = self.post("/study-planner", {
            "available_minutes": "120",
            "topic_name": ["Recursion", "Hashing", "Arrays"],
            "mastery_pct": ["20", "50", "90"],
            "estimated_minutes": ["60", "45", "30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recommended study order", response.data)
        # Weakest topic first and the totals are shown.
        self.assertIn(b"Recursion", response.data)
        self.assertIn(b"120 min", response.data)
        self.assertIn(b"Topics that did not fit", response.data)

    def test_plan_that_fits_everything_has_no_warning(self):
        response = self.post("/study-planner", {
            "available_minutes": "300",
            "topic_name": ["Recursion", "Arrays"],
            "mastery_pct": ["20", "90"],
            "estimated_minutes": ["60", "30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complete", response.data)
        self.assertNotIn(b"Topics that did not fit", response.data)

    def test_missing_topic_fields_shows_error(self):
        response = self.post("/study-planner", {
            "available_minutes": "60",
            "topic_name": ["Recursion"],
            "mastery_pct": [""],
            "estimated_minutes": [""],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"enter a mastery percentage and estimated", response.data)

    def test_invalid_mastery_shows_error(self):
        response = self.post("/study-planner", {
            "available_minutes": "60",
            "topic_name": ["Recursion"],
            "mastery_pct": ["150"],
            "estimated_minutes": ["30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"must be between 0% and 100%", response.data)

    def test_invalid_available_time_shows_error(self):
        response = self.post("/study-planner", {
            "available_minutes": "0",
            "topic_name": ["Recursion"],
            "mastery_pct": ["20"],
            "estimated_minutes": ["30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Available study time must be between 1 and 100000 minutes.", response.data)

    def test_empty_submission_shows_error(self):
        response = self.post("/study-planner", {
            "available_minutes": "60",
            "topic_name": ["", "", ""],
            "mastery_pct": ["", "", ""],
            "estimated_minutes": ["", "", ""],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Add at least one topic", response.data)

    def test_missing_c_library_shows_safe_message(self):
        with patch.dict(self.app.extensions["sac"],
                        study_planner=False,
                        study_planner_error="C library unavailable for testing."):
            response = self.post("/study-planner", {
                "available_minutes": "60",
                "topic_name": ["Recursion"],
                "mastery_pct": ["20"],
                "estimated_minutes": ["30"],
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"C library unavailable for testing.", response.data)


if __name__ == "__main__":
    unittest.main()
