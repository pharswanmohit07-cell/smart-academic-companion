import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import database
from modules import risk_model


class TestRiskModelDatabaseFeatures(unittest.TestCase):
    def test_new_assessment_submissions_supply_assignment_ratio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "risk_features.db"
            with patch.object(database, "DATABASE_PATH", db_path):
                database.initialize_database()
                with closing(sqlite3.connect(db_path)) as connection:
                    connection.execute(
                        "INSERT INTO students (name, email) VALUES (?, ?)",
                        ("Risk Test Student", "risk@example.edu"),
                    )
                    connection.execute(
                        "INSERT INTO subjects (subject_name, subject_code) VALUES (?, ?)",
                        ("Python", "PY"),
                    )
                    connection.execute(
                        """INSERT INTO attendance
                           (student_id, subject_id, total_classes, attended_classes)
                           VALUES (1, 1, 10, 8)"""
                    )
                    connection.execute(
                        """INSERT INTO marks
                           (student_id, subject_id, exam_name, marks_obtained, max_marks)
                           VALUES (1, 1, 'Midterm', 40, 100)"""
                    )
                    connection.executemany(
                        """INSERT INTO assessment_items
                           (subject_id, assessment_type, title)
                           VALUES (1, 'assignment', ?)""",
                        [("Assignment A",), ("Assignment B",)],
                    )
                    connection.execute(
                        """INSERT INTO assessment_submissions
                           (assessment_id, student_id, submitted)
                           VALUES (1, 1, 1)"""
                    )
                    # No row for the second assessment must count as pending.
                    connection.commit()

                result = risk_model._load_student_data()
                self.assertEqual(len(result), 1)
                self.assertAlmostEqual(result.iloc[0]["attendance_pct"], 80.0)
                self.assertAlmostEqual(result.iloc[0]["average_marks_pct"], 40.0)
                self.assertAlmostEqual(
                    result.iloc[0]["assignment_submission_ratio"], 0.5
                )


if __name__ == "__main__":
    unittest.main()
