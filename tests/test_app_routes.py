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


if __name__ == "__main__":
    unittest.main()
