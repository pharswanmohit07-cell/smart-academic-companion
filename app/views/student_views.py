"""
Student dashboard: the student's own academic record, and only that.

Ownership comes from the session's ``student_id``, which is read from
``students.auth_user_id = auth.users.id`` at sign-in. The student id is never
taken from the URL or a form, so a student cannot request another student's
records even by guessing ids.
"""

import logging

from flask import Blueprint, render_template, url_for

from app import auth as auth_module
from modules import risk_model

log = logging.getLogger(__name__)

bp = Blueprint("student", __name__)


def _own_summary(account):
    """Attendance per subject, marks per subject and assessment status."""
    from contextlib import closing

    from db import get_connection

    with closing(get_connection()) as connection:
        attendance = connection.execute(
            """SELECT sub.subject_name, sub.subject_code,
                      a.attended_classes, a.total_classes,
                      CASE WHEN a.total_classes > 0
                           THEN 100.0 * a.attended_classes / a.total_classes
                           ELSE NULL END AS attendance_pct
                 FROM attendance AS a
                 JOIN subjects AS sub ON sub.subject_id = a.subject_id
                WHERE a.student_id = ?
                ORDER BY sub.subject_name""",
            (account.student_id,),
        ).fetchall()

        marks = connection.execute(
            """SELECT sub.subject_name, m.exam_name, m.marks_obtained, m.max_marks,
                      CASE WHEN m.max_marks > 0
                           THEN 100.0 * m.marks_obtained / m.max_marks
                           ELSE NULL END AS percentage
                 FROM marks AS m
                 JOIN subjects AS sub ON sub.subject_id = m.subject_id
                WHERE m.student_id = ?
                ORDER BY sub.subject_name, m.exam_name""",
            (account.student_id,),
        ).fetchall()

        assessments = connection.execute(
            """SELECT ai.assessment_id, ai.title, ai.assessment_type, ai.due_date,
                      sub.subject_name, ss.submitted
                 FROM assessment_items AS ai
                 JOIN subjects AS sub ON sub.subject_id = ai.subject_id
                 LEFT JOIN assessment_submissions AS ss
                        ON ss.assessment_id = ai.assessment_id
                       AND ss.student_id = ?
                ORDER BY ai.due_date NULLS LAST, ai.title""",
            (account.student_id,),
        ).fetchall()

    return [dict(row) for row in attendance], [dict(row) for row in marks], \
        [dict(row) for row in assessments]


def _risk_for(account):
    """The student's own risk estimate; never fails the dashboard."""
    try:
        return risk_model.predict_students([account.student_id]).get(account.student_id)
    except Exception:  # noqa: BLE001 - a model problem must not break the page
        log.info("risk estimate unavailable for student %s", account.student_id)
        return None


@bp.route("/student/dashboard")
@auth_module.login_required
def dashboard():
    account = auth_module.current_account()
    if account.is_faculty:
        return auth_module.redirect_to_dashboard(account)

    if account.student_id is None:
        return auth_module.redirect_to_dashboard(account)

    attendance, marks, assessments = _own_summary(account)

    total_held = sum(row["total_classes"] or 0 for row in attendance)
    total_attended = sum(row["attended_classes"] or 0 for row in attendance)
    overall = (100.0 * total_attended / total_held) if total_held else None
    pending = [row for row in assessments if not row["submitted"]]

    return render_template(
        "student_dashboard.html",
        record_name=_record_name(account),
        attendance=attendance,
        marks=marks,
        assessments=assessments,
        pending_count=len(pending),
        overall_attendance=overall,
        risk=_risk_for(account),
        attendance_url=url_for("academic.attendance"),
        classrooms_url=url_for("academic.classrooms"),
        planner_url=url_for("academic.study_planner_page"),
    )


def _record_name(account):
    """Name on the student's own academic record, if one has been entered."""
    from contextlib import closing

    from db import get_connection

    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT name FROM students WHERE student_id = ?", (account.student_id,)
        ).fetchone()
    name = (row["name"] if row else "") or ""
    # A new account's record is named after the email local part, lower-case.
    if not name.strip() or name[:1].islower():
        return ""
    return name
