import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app as app_module
import database


def seed_students(count):
    """Insert students with complete data so the model can be trained."""
    with closing(database.get_connection()) as connection:
        connection.execute(
            "INSERT INTO subjects (subject_name, subject_code) VALUES ('Python', 'PY')"
        )
        connection.execute(
            """INSERT INTO assessment_items (subject_id, assessment_type, title)
               VALUES (1, 'assignment', 'Lab 1')"""
        )
        for index in range(count):
            name = f"Student {index + 1}"
            cursor = connection.execute(
                "INSERT INTO students (name, email) VALUES (?, ?)",
                (name, f"s{index}@example.edu"),
            )
            student_id = cursor.lastrowid
            # Alternate strong and weak records so both labels exist.
            total = 20
            attended = 20 if index % 2 == 0 else 8
            marks = 80 if index % 2 == 0 else 35
            connection.execute(
                """INSERT INTO attendance
                   (student_id, subject_id, total_classes, attended_classes)
                   VALUES (?, 1, ?, ?)""",
                (student_id, total, attended),
            )
            for exam in ("Midterm", "End Term"):
                connection.execute(
                    """INSERT INTO marks
                       (student_id, subject_id, exam_name, marks_obtained, max_marks)
                       VALUES (?, 1, ?, ?, 100)""",
                    (student_id, exam, marks),
                )
            connection.execute(
                """INSERT INTO assessment_submissions
                   (assessment_id, student_id, submitted) VALUES (1, ?, 1)""",
                (student_id,),
            )
        connection.commit()


class TestRiskDashboardIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "risk_dashboard.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.database_patch.start()
        database.initialize_database()
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_dashboard_shows_risk_score_and_strongest_factor(self):
        seed_students(12)
        response = self.client.get("/risk")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Demonstration risk score", response.data)
        self.assertIn(b"Strongest factor:", response.data)
        self.assertIn(b"%", response.data)
        self.assertIn(b"not a validated dropout predictor", response.data)

    def test_students_without_data_show_no_prediction(self):
        seed_students(12)
        with closing(database.get_connection()) as connection:
            connection.execute(
                "INSERT INTO students (name, email) VALUES ('Empty Record', 'e@example.edu')"
            )
            connection.commit()
        response = self.client.get("/risk")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No prediction (incomplete data)", response.data)

    def test_model_failure_does_not_crash_dashboard(self):
        seed_students(12)
        with patch.object(app_module.risk_model, "predict_students",
                          side_effect=RuntimeError("model exploded")):
            response = self.client.get("/risk")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"The academic records above are unaffected", response.data)
        self.assertIn(b"Faculty Academic Dashboard", response.data)

    def test_too_few_students_is_handled_gracefully(self):
        seed_students(3)
        response = self.client.get("/risk")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"could not score these students", response.data)

    def test_class_filter_still_works_with_predictions(self):
        seed_students(12)
        response = self.client.get("/risk?class_id=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Demonstration risk score", response.data)

    def test_pending_assessment_does_not_hide_score(self):
        """A row with submitted = 0 must still count as complete data."""
        seed_students(12)
        with closing(database.get_connection()) as connection:
            connection.execute(
                "UPDATE assessment_submissions SET submitted = 0 WHERE student_id = 1"
            )
            connection.commit()
        predictions = app_module.risk_model.predict_students([1, 2])
        self.assertEqual(set(predictions), {1, 2})
        self.assertAlmostEqual(
            predictions[1]["features"]["assignment_submission_ratio"], 0.0
        )

    def test_risk_model_still_scores_a_single_student(self):
        seed_students(12)
        result = app_module.risk_model.predict_risk(1)
        self.assertGreaterEqual(result["risk_probability"], 0.0)
        self.assertLessEqual(result["risk_probability"], 1.0)
        self.assertIn(result["top_factor"], app_module.risk_model.FEATURES)
        self.assertIn("top_factor_label", result)


if __name__ == "__main__":
    unittest.main()
