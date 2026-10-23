
import unittest
from unittest.mock import patch

import pandas as pd

from modules import risk_model


class TestRiskModel(unittest.TestCase):

    def test_labels_follow_demonstration_thresholds(self):
        data = pd.DataFrame({
            "student_id": [1, 2, 3, 4],
            "name": ["A", "B", "C", "D"],
            "attendance_pct": [74.9, 90, 90, 75],
            "average_marks_pct": [80, 49.9, 60, 50],
            "assignment_submission_ratio": [0.8, 0.7, 0.9, 1.0],
        })

        with patch.object(
            risk_model, "get_connection"
        ), patch.object(
            risk_model.pd, "read_sql_query", return_value=data
        ):
            result = risk_model._load_student_data()

        self.assertEqual(result["at_risk"].tolist(), [1, 1, 0, 0])

    def test_missing_student_raises_value_error(self):
        with patch.object(
            risk_model, "_load_student_data",
            return_value=pd.DataFrame(columns=[
                "student_id", "name", *risk_model.FEATURES, "at_risk"
            ]),
        ):
            with self.assertRaises(ValueError):
                risk_model.predict_risk(999999)

    def test_prediction_probability_is_between_zero_and_one(self):
        result = risk_model.predict_risk(1)
        self.assertGreaterEqual(result["risk_probability"], 0.0)
        self.assertLessEqual(result["risk_probability"], 1.0)

    def test_assignment_ratio_is_between_zero_and_one(self):
        result = risk_model.predict_risk(1)
        ratio = result["features"]["assignment_submission_ratio"]
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)


if __name__ == "__main__":
    unittest.main()
