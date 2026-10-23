
"""Database summaries for the faculty academic dashboard."""

from database import get_connection


def get_faculty_summary():
    """Return student metrics and class-level dashboard counts."""
    conn = get_connection()
    try:
        students = conn.execute(
            """
            SELECT
                s.student_id,
                s.name,
                s.semester,
                s.section,
                attendance.attendance_pct,
                marks.average_marks_pct,
                assignments.assignment_submission_ratio
            FROM students AS s
            LEFT JOIN (
                SELECT
                    student_id,
                    100.0 * SUM(attended_classes)
                        / NULLIF(SUM(total_classes), 0) AS attendance_pct
                FROM attendance
                GROUP BY student_id
            ) AS attendance
                ON attendance.student_id = s.student_id
            LEFT JOIN (
                SELECT
                    student_id,
                    100.0 * AVG(
                        1.0 * marks_obtained / NULLIF(max_marks, 0)
                    ) AS average_marks_pct
                FROM marks
                GROUP BY student_id
            ) AS marks
                ON marks.student_id = s.student_id
            LEFT JOIN (
                SELECT
                    student_id,
                    AVG(1.0 * submitted)
                        AS assignment_submission_ratio
                FROM assignments
                GROUP BY student_id
            ) AS assignments
                ON assignments.student_id = s.student_id
            ORDER BY s.student_id
            """
        ).fetchall()

        records = [dict(row) for row in students]

        for student in records:
            attendance = student["attendance_pct"]
            marks = student["average_marks_pct"]
            ratio = student["assignment_submission_ratio"]

            # Missing information is not automatically classified as low risk.
            student["data_complete"] = (
                attendance is not None
                and marks is not None
                and ratio is not None
            )

            student["rule_flags"] = []

            if attendance is not None and attendance < 75:
                student["rule_flags"].append("Attendance below 75%")

            if marks is not None and marks < 50:
                student["rule_flags"].append("Average marks below 50%")

            if ratio is not None and ratio < 1:
                student["rule_flags"].append("Some assignments not submitted")

        complete = [s for s in records if s["data_complete"]]

        return {
            "students": records,
            "total_students": len(records),
            "incomplete_records": len(records) - len(complete),
            "low_attendance": sum(
                1 for s in records
                if s["attendance_pct"] is not None
                and s["attendance_pct"] < 75
            ),
            "low_marks": sum(
                1 for s in records
                if s["average_marks_pct"] is not None
                and s["average_marks_pct"] < 50
            ),
            "incomplete_assignments": sum(
                1 for s in records
                if s["assignment_submission_ratio"] is not None
                and s["assignment_submission_ratio"] < 1
            ),
        }
    finally:
        conn.close()
