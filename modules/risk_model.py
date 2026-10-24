
"""
Risk model for the Smart Academic Companion.

Trains a logistic regression classifier on data read directly from the
SQLite database (academic_companion.db) to estimate whether a student is
at academic risk.

WARNING: The demonstration labels are rule-based (attendance <75% OR
average marks <50%), so accuracy metrics are not evidence of real-world
predictive power and must not be used for real academic decisions.
"""

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from database import get_connection

FEATURES = [
    "attendance_pct",
    "average_marks_pct",
    "assignment_submission_ratio",
]

# Fixed seed keeps the train/test split reproducible across calls, so
# predictions stay consistent within one run.
RANDOM_SEED = 42


def _load_student_data():
    """Build student features and demonstration labels from SQLite."""
    conn = get_connection()
    try:
        data = pd.read_sql_query(
            """
            WITH attendance_by_student AS (
                SELECT student_id,
                    100.0 * SUM(attended_classes) /
                    NULLIF(SUM(total_classes), 0) AS attendance_pct
                FROM attendance
                GROUP BY student_id
            ),
            marks_by_student AS (
                SELECT student_id,
                    100.0 * AVG(marks_obtained / NULLIF(max_marks, 0))
                        AS average_marks_pct
                FROM marks
                GROUP BY student_id
            ),
            legacy_assignment_ratio AS (
                SELECT student_id,
                    1.0 * AVG(submitted) AS submission_ratio
                FROM assignments
                GROUP BY student_id
            ),
            assessment_submission_ratio AS (
                SELECT s.student_id,
                    1.0 * SUM(COALESCE(ss.submitted, 0)) /
                    NULLIF(COUNT(ai.assessment_id), 0) AS submission_ratio
                FROM students AS s
                CROSS JOIN assessment_items AS ai
                LEFT JOIN assessment_submissions AS ss
                    ON ss.assessment_id = ai.assessment_id
                    AND ss.student_id = s.student_id
                GROUP BY s.student_id
            )
            SELECT
                s.student_id,
                s.name,
                attendance.attendance_pct,
                marks.average_marks_pct,
                COALESCE(
                    assessments.submission_ratio,
                    legacy.submission_ratio
                ) AS assignment_submission_ratio
            FROM students AS s
            LEFT JOIN attendance_by_student AS attendance
                ON attendance.student_id = s.student_id
            LEFT JOIN marks_by_student AS marks
                ON marks.student_id = s.student_id
            LEFT JOIN assessment_submission_ratio AS assessments
                ON assessments.student_id = s.student_id
            LEFT JOIN legacy_assignment_ratio AS legacy
                ON legacy.student_id = s.student_id
            GROUP BY s.student_id, s.name
            """,
            conn,
        )    finally:
        conn.close()

    # Students with no attendance/marks/assignment rows cannot be scored.
    data = data.dropna(subset=FEATURES)

    # Demonstration label: at risk if attendance <75% OR average marks <50%.
    data["at_risk"] = (
        (data["attendance_pct"] < 75) | (data["average_marks_pct"] < 50)
    ).astype(int)
    return data


def train_model():
    """Train a logistic regression model on the student data.

    Returns:
        (model, metrics): the fitted sklearn pipeline and a dict of
        evaluation metrics from the held-out test split.
    """
    data = _load_student_data()
    if data.empty or len(data) < 10:
        raise ValueError(
            "Not enough student data in the database to train the risk "
            "model (need at least 10 students with complete data)."
        )

    X = data[FEATURES]
    y = data["at_risk"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )

    model = make_pipeline(StandardScaler(), LogisticRegression())
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "confusion_matrix": confusion_matrix(
            y_test, predictions, labels=[0, 1]
        ).tolist(),
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
        "label_rule": (
            "At risk if attendance <75% or average marks <50%."
        ),
        "warning": (
            "Demonstration on generated data; not evidence of real-world "
            "accuracy."
        ),
    }
    return model, metrics


def predict_risk(student_id):
    """Return the student's estimated risk and strongest factor."""
    data = _load_student_data()
    student_rows = data[data["student_id"] == student_id]
    if student_rows.empty:
        raise ValueError("Student not found or required data is incomplete.")

    model, _ = train_model()
    row = student_rows.iloc[0]
    features = row[FEATURES].to_frame().T
    probability = float(model.predict_proba(features)[0][1])

    # Approximate feature contribution using the fitted logistic model.
    # Standardized feature value x coefficient indicates direction/magnitude.
    scaler = model.named_steps["standardscaler"]
    classifier = model.named_steps["logisticregression"]
    standardized = scaler.transform(features)[0]
    contributions = standardized * classifier.coef_[0]
    strongest_index = max(
        range(len(FEATURES)),
        key=lambda index: abs(contributions[index]),
    )

    return {
        "student_id": int(row["student_id"]),
        "name": row["name"],
        "risk_probability": probability,
        "risk_percent": round(probability * 100, 2),
        "predicted_at_risk": bool(model.predict(features)[0]),
        "features": {feature: float(row[feature]) for feature in FEATURES},
        "top_factor": FEATURES[strongest_index],
        "top_factor_direction": (
            "increases estimated risk"
            if contributions[strongest_index] > 0
            else "decreases estimated risk"
        ),
        "warning": (
            "Demonstration on generated data; not evidence of real-world "
            "accuracy."
        ),
    }
