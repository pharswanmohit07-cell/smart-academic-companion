"""Risk dashboard as an authenticated faculty account sees it.

Ported from the standalone ``app`` object to the application factory. Every
page now needs a signed-in faculty account, and the dashboard only shows
students in classes that account owns, so the fixtures create both.
"""

import unittest
from unittest.mock import patch

from tests.support import FakeAuthState, TempDatabaseMixin

import database
import modules.risk_model as risk_model
from db import last_insert_id


def seed_students(connection, count, class_id):
    """Insert students with complete data so the model can be trained."""
    connection.execute(
        "INSERT INTO subjects (subject_name, subject_code) VALUES ('Python', 'PY')"
    )
    connection.execute(
        """INSERT INTO assessment_items (subject_id, assessment_type, title)
           VALUES (1, 'assignment', 'Lab 1')"""
    )
    for index in range(count):
        cursor = connection.execute(
            "INSERT INTO students (name, email, class_id) VALUES (?, ?, ?)",
            (f"Student {index + 1}", f"s{index}@example.edu", class_id),
        )
        student_id = last_insert_id(connection, "students", "student_id")
        # Alternate strong and weak records so both labels exist.
        attended = 20 if index % 2 == 0 else 8
        marks = 80 if index % 2 == 0 else 35
        connection.execute(
            """INSERT INTO attendance
                   (student_id, subject_id, total_classes, attended_classes)
               VALUES (?, 1, 20, ?)""",
            (student_id, attended),
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
    return cursor


class RiskDashboardBase(TempDatabaseMixin):
    def setUp(self):
        super().setUp()
        import wsgi

        self.fake = FakeAuthState.current
        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()
        self.csrf_token = "risk-dashboard-token"

        # One faculty login owning one class; the students live in that class.
        user_id = self.fake.add_user("faculty@example.com", "secret-pass-1")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO user_profiles (user_id, email, display_name, role) "
                "VALUES (?, 'faculty@example.com', 'Faculty', 'faculty')",
                (user_id,),
            )
            connection.execute(
                "INSERT INTO teachers (auth_user_id, name, email) "
                "VALUES (?, 'Faculty', 'faculty@example.com')",
                (user_id,),
            )
            connection.commit()
            teacher_id = connection.execute(
                "SELECT teacher_id FROM teachers WHERE auth_user_id = ?", (user_id,)
            ).fetchone()["teacher_id"]
            connection.execute(
                """INSERT INTO faculty_classes
                       (class_name, program, semester, section, description,
                        owner_teacher_id)
                   VALUES ('Risk Class', 'Program', 3, 'A', '', ?)""",
                (teacher_id,),
            )
            connection.commit()
            self.class_id = connection.execute(
                "SELECT class_id FROM faculty_classes WHERE class_name = 'Risk Class'"
            ).fetchone()["class_id"]

        with self.client.session_transaction() as session:
            session["csrf_token"] = self.csrf_token
        response = self.client.post("/auth/login", data={
            "email": "faculty@example.com",
            "password": "secret-pass-1",
            "csrf_token": self.csrf_token,
        })
        self.assertIn(response.status_code, (301, 302, 303))
        with self.client.session_transaction() as session:
            if not session.get("csrf_token"):
                session["csrf_token"] = self.csrf_token

    def seed(self, count):
        with self.connect() as connection:
            seed_students(connection, count, self.class_id)


class TestRiskDashboardIntegration(RiskDashboardBase, unittest.TestCase):
    def test_dashboard_shows_risk_score_and_main_factor(self):
        self.seed(12)
        response = self.client.get("/faculty/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Risk estimate", response.data)
        self.assertIn(b"Main factor:", response.data)
        self.assertIn(b"%", response.data)
        self.assertIn(b"Risk estimates are for guidance only.", response.data)
        for technical in (b"logistic", b"min-heap", b"max-heap"):
            self.assertNotIn(technical, response.data)

    def test_students_without_data_show_no_prediction(self):
        self.seed(12)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO students (name, email, class_id) VALUES "
                "('Empty Record', 'e@example.edu', ?)",
                (self.class_id,),
            )
            connection.commit()
        response = self.client.get("/faculty/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Not available (incomplete data)", response.data)

    def test_model_failure_does_not_crash_dashboard(self):
        self.seed(12)
        # The view imports the model module, so patch the module attribute.
        with patch.object(risk_model, "predict_students",
                          side_effect=RuntimeError("model exploded")):
            response = self.client.get("/faculty/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Risk estimates are unavailable right now", response.data)
        self.assertIn(b"unaffected", response.data)
        self.assertIn(b"Faculty Academic Dashboard", response.data)
        self.assertNotIn(b"RuntimeError", response.data)

    def test_too_few_students_is_handled_gracefully(self):
        self.seed(3)
        response = self.client.get("/faculty/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Risk estimates are unavailable right now", response.data)

    def test_class_filter_still_works_with_predictions(self):
        self.seed(12)
        response = self.client.get(f"/faculty/dashboard?class_id={self.class_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Risk estimate", response.data)

    def test_pending_assessment_does_not_hide_score(self):
        """A row with submitted = 0 must still count as complete data."""
        self.seed(12)
        with self.connect() as connection:
            connection.execute(
                "UPDATE assessment_submissions SET submitted = 0 WHERE student_id = 1"
            )
            connection.commit()
        predictions = risk_model.predict_students([1, 2])
        self.assertEqual(set(predictions), {1, 2})
        self.assertAlmostEqual(
            predictions[1]["features"]["assignment_submission_ratio"], 0.0
        )

    def test_risk_model_still_scores_a_single_student(self):
        self.seed(12)
        result = risk_model.predict_risk(1)
        self.assertGreaterEqual(result["risk_probability"], 0.0)
        self.assertLessEqual(result["risk_probability"], 1.0)
        self.assertIn(result["top_factor"], risk_model.FEATURES)
        self.assertIn("top_factor_label", result)


if __name__ == "__main__":
    unittest.main()
