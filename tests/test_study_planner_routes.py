import unittest
from unittest.mock import patch

import app as app_module


class TestStudyPlannerPage(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_page_loads(self):
        response = self.client.get("/study-planner")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI Study Planner", response.data)
        self.assertIn(b"Generate study plan", response.data)

    def test_home_and_navigation_link_to_planner(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"/study-planner", home.data)
        self.assertIn(b"Manage Classes", home.data)

    def test_valid_plan_is_generated(self):
        response = self.client.post("/study-planner", data={
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
        self.assertIn(b"Topics that could not fit", response.data)

    def test_plan_that_fits_everything_has_no_warning(self):
        response = self.client.post("/study-planner", data={
            "available_minutes": "300",
            "topic_name": ["Recursion", "Arrays"],
            "mastery_pct": ["20", "90"],
            "estimated_minutes": ["60", "30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complete", response.data)
        self.assertNotIn(b"Topics that could not fit", response.data)

    def test_missing_topic_fields_shows_error(self):
        response = self.client.post("/study-planner", data={
            "available_minutes": "60",
            "topic_name": ["Recursion"],
            "mastery_pct": [""],
            "estimated_minutes": [""],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"enter a mastery percentage and estimated", response.data)

    def test_invalid_mastery_shows_error(self):
        response = self.client.post("/study-planner", data={
            "available_minutes": "60",
            "topic_name": ["Recursion"],
            "mastery_pct": ["150"],
            "estimated_minutes": ["30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"must be between 0% and 100%", response.data)

    def test_invalid_available_time_shows_error(self):
        response = self.client.post("/study-planner", data={
            "available_minutes": "0",
            "topic_name": ["Recursion"],
            "mastery_pct": ["20"],
            "estimated_minutes": ["30"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Available study time must be between 1 and 100000 minutes.", response.data)

    def test_empty_submission_shows_error(self):
        response = self.client.post("/study-planner", data={
            "available_minutes": "60",
            "topic_name": ["", "", ""],
            "mastery_pct": ["", "", ""],
            "estimated_minutes": ["", "", ""],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Add at least one topic", response.data)

    def test_missing_c_library_shows_safe_message(self):
        with patch.object(app_module, "study_planner", None), patch.object(
            app_module, "STUDY_PLANNER_ERROR", "C library unavailable for testing."
        ):
            response = self.client.post("/study-planner", data={
                "available_minutes": "60",
                "topic_name": ["Recursion"],
                "mastery_pct": ["20"],
                "estimated_minutes": ["30"],
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"C library unavailable for testing.", response.data)


if __name__ == "__main__":
    unittest.main()
