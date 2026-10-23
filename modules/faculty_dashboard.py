"""Database summaries for the faculty academic dashboard."""

from database import get_connection


def get_faculty_summary():
    """Return student exam totals, attendance and assessment status."""
    conn = get_connection()
    try:
        students = conn.execute(
            """
            SELECT
                s.student_id, s.name, s.semester, s.section,
                attendance.attendance_pct,
                midterm.marks_obtained AS midterm_obtained,
                midterm.max_marks AS midterm_max,
                endterm.marks_obtained AS endterm_obtained,
                endterm.max_marks AS endterm_max,
                assessments.total_items,
                assessments.submitted_items
            FROM students AS s
            LEFT JOIN (
                SELECT student_id,
                    100.0 * SUM(attended_classes) /
                    NULLIF(SUM(total_classes), 0) AS attendance_pct
                FROM attendance GROUP BY student_id
            ) AS attendance ON attendance.student_id = s.student_id
            LEFT JOIN (
                SELECT student_id,
                    SUM(marks_obtained) AS marks_obtained,
                    SUM(max_marks) AS max_marks
                FROM marks WHERE lower(trim(exam_name)) = 'midterm'
                GROUP BY student_id
            ) AS midterm ON midterm.student_id = s.student_id
            LEFT JOIN (
                SELECT student_id,
                    SUM(marks_obtained) AS marks_obtained,
                    SUM(max_marks) AS max_marks
                FROM marks WHERE lower(trim(exam_name)) IN ('end term', 'end-term', 'endterm')
                GROUP BY student_id
            ) AS endterm ON endterm.student_id = s.student_id
            LEFT JOIN (
                SELECT s.student_id,
                    COUNT(ai.assessment_id) AS total_items,
                    SUM(CASE WHEN sub.submitted = 1 THEN 1 ELSE 0 END) AS submitted_items
                FROM students s
                CROSS JOIN assessment_items ai
                LEFT JOIN assessment_submissions sub
                    ON sub.assessment_id = ai.assessment_id
                    AND sub.student_id = s.student_id
                GROUP BY s.student_id
            ) AS assessments ON assessments.student_id = s.student_id
            ORDER BY s.student_id
            """
        ).fetchall()

        records = [dict(row) for row in students]
        for student in records:
            attendance = student["attendance_pct"]
            student["data_complete"] = (
                attendance is not None
                and student["midterm_max"] is not None
                and student["endterm_max"] is not None
            )
            student["rule_flags"] = []
            if attendance is not None and attendance < 75:
                student["rule_flags"].append("Attendance below 75%")
            if student["midterm_max"] and (
                student["midterm_obtained"] / student["midterm_max"] < 0.5
            ):
                student["rule_flags"].append("Midterm marks below 50%")
            if student["endterm_max"] and (
                student["endterm_obtained"] / student["endterm_max"] < 0.5
            ):
                student["rule_flags"].append("End Term marks below 50%")
            total_items = student["total_items"] or 0
            submitted_items = student["submitted_items"] or 0
            student["pending_assessments"] = total_items - submitted_items
            if student["pending_assessments"] > 0:
                student["rule_flags"].append("Assessments pending")

        complete = [s for s in records if s["data_complete"]]
        return {
            "students": records,
            "total_students": len(records),
            "incomplete_records": len(records) - len(complete),
            "low_attendance": sum(
                1 for s in records
                if s["attendance_pct"] is not None and s["attendance_pct"] < 75
            ),
            "low_marks": sum(
                1 for s in records
                if any(flag in s["rule_flags"] for flag in (
                    "Midterm marks below 50%", "End Term marks below 50%"
                ))
            ),
            "incomplete_assignments": sum(
                1 for s in records if s["pending_assessments"] > 0
            ),
        }
    finally:
        conn.close()


def get_assessment_overview():
    """Return assessment items and their student submission counts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ai.assessment_id, ai.assessment_type, ai.title,
                   ai.due_date, sub.subject_name,
                   COUNT(s.student_id) AS total_students,
                   SUM(CASE WHEN ss.submitted = 1 THEN 1 ELSE 0 END) AS submitted_count
            FROM assessment_items ai
            JOIN subjects sub ON sub.subject_id = ai.subject_id
            CROSS JOIN students s
            LEFT JOIN assessment_submissions ss
                ON ss.assessment_id = ai.assessment_id
                AND ss.student_id = s.student_id
            GROUP BY ai.assessment_id
            ORDER BY ai.assessment_type, ai.title
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
