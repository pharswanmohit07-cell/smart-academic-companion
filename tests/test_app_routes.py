import unittest

from app import app


class TestClassroomRoute(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_page_loads(self):
        self.assertEqual(self.client.get("/classrooms").status_code, 200)

    def test_end_before_start_shows_error(self):
        response = self.client.post(
            "/classrooms",
            data={"day": "1", "start": "11:00", "end": "10:00"},
        )
        self.assertIn(
            b"Enter a start time that is earlier than the end time.",
            response.data,
        )

    def test_empty_timetable_shows_safe_seed_data_warning(self):
        from unittest.mock import patch

        with patch("app.CLASSROOM_ERROR", None), patch(
            "app.find_rooms", return_value=([], None)
        ):
            response = self.client.post(
                "/classrooms",
                data={"day": "1", "start": "10:00", "end": "11:00"},
            )

        self.assertIn(b"No timetable entries found.", response.data)
        self.assertIn(b"it clears existing records", response.data)

    def test_database_error_does_not_recommend_destructive_seed_as_default(self):
        import sqlite3
        from unittest.mock import patch

        with patch("app.CLASSROOM_ERROR", None), patch(
            "app.find_rooms", side_effect=sqlite3.OperationalError("no such table")
        ):
            response = self.client.post(
                "/classrooms",
                data={"day": "1", "start": "10:00", "end": "11:00"},
            )

        self.assertIn(b"Run: python database.py", response.data)
        self.assertIn(b"disposable demo data", response.data)


if __name__ == "__main__":
    unittest.main()
