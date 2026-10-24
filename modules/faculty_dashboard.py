"""Database summaries for the faculty academic dashboard."""

from database import get_connection


def get_faculty_summary():
    """Return student attendance, subject-level exam marks and assessment status."""
    conn = get_connection()
    try:
        students = conn.execute(
            """
            SELECT
                s.student_id, s.name, s.semester, s.section,
                attendance.attendance_pct,
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

        mark_rows = conn.execute(
            """
            SELECT m.student_id, subject.subject_name,
                   CASE
                       WHEN lower(trim(m.exam_name)) = 'midterm' THEN 'midterm'
                       WHEN lower(trim(m.exam_name)) IN ('end term', 'end-term', 'endterm')
                           THEN 'endterm'
                   END AS exam_type,
                   SUM(m.marks_obtained) AS marks_obtained,
                   SUM(m.max_marks) AS max_marks
            FROM marks AS m
            JOIN subjects AS subject ON subject.subject_id = m.subject_id
            WHERE lower(trim(m.exam_name)) = 'midterm'
               OR lower(trim(m.exam_name)) IN ('end term', 'end-term', 'endterm')
            GROUP BY m.student_id, m.subject_id, exam_type
            ORDER BY subject.subject_name
            """
        ).fetchall()

        subject_names = [
            row["subject_name"]
            for row in conn.execute(
                "SELECT subject_name FROM subjects ORDER BY subject_name"
            ).fetchall()
        ]

        records = [dict(row) for row in students]
        by_student = {student["student_id"]: student for student in records}
        for student in records:
            student["midterm_results"] = []
            student["endterm_results"] = []

        for row in mark_rows:
            student = by_student.get(row["student_id"])
            if student is None or not row["max_marks"]:
                continue
            result = {
                "subject_name": row["subject_name"],
                "marks_obtained": row["marks_obtained"],
                "max_marks": row["max_marks"],
                "percentage": 100.0 * row["marks_obtained"] / row["max_marks"],
            }
            key = "midterm_results" if row["exam_type"] == "midterm" else "endterm_results"
            student[key].append(result)

        for student in records:
            attendance = student["attendance_pct"]
            student["midterm_low"] = any(
                result["percentage"] < 50 for result in student["midterm_results"]
            )
            student["endterm_low"] = any(
                result["percentage"] < 50 for result in student["endterm_results"]
            )
            student["data_complete"] = (
                attendance is not None
                and bool(student["midterm_results"])
                and bool(student["endterm_results"])
            )
            student["rule_flags"] = []
            if attendance is not None and attendance < 75:
                student["rule_flags"].append("Attendance below 75%")
            if student["midterm_low"]:
                student["rule_flags"].append("Midterm marks below 50% in one or more subjects")
            if student["endterm_low"]:
                student["rule_flags"].append("End Term marks below 50% in one or more subjects")
            total_items = student["total_items"] or 0
            submitted_items = student["submitted_items"] or 0
            student["pending_assessments"] = total_items - submitted_items
            if student["pending_assessments"] > 0:
                student["rule_flags"].append("Assessments pending")

        complete = [student for student in records if student["data_complete"]]
        return {
            "students": records,
            "subject_names": subject_names,
            "total_students": len(records),
            "incomplete_records": len(records) - len(complete),
            "low_attendance": sum(
                1 for student in records
                if student["attendance_pct"] is not None and student["attendance_pct"] < 75
            ),
            "low_marks": sum(
                1 for student in records if student["midterm_low"] or student["endterm_low"]
            ),
            "incomplete_assignments": sum(
                1 for student in records if student["pending_assessments"] > 0
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
