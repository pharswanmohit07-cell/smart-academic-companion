"""
Faculty area: academic dashboard, record management and class management.

Authorization, in layers:

1. ``@auth_module.faculty_required`` on every route: only the trusted roles
   ``faculty`` and ``admin`` from ``public.user_profiles`` get in.
2. Class-level ownership: a faculty account may only see and change classes
   whose ``faculty_classes.owner_teacher_id`` is their own ``teachers`` row.
   ``scope`` below is the single source of truth: ``None`` for an admin (no
   filter) or the list of owned class ids.
3. Student-level ownership: every student id that arrives in a form is checked
   with ``auth_module.require_student_ids`` before it is written, so posting a
   guessed id is rejected instead of modifying another class's record.

Saves are unchanged in behaviour apart from that scoping; the SQL now uses the
portable placeholder/upsert forms translated by :mod:`db`.
"""

import logging
from contextlib import contextmanager

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)

from app import auth as auth_module
from app.accounts import profiles_table
from db import DatabaseError, IntegrityError, get_connection, last_insert_id
from modules.faculty_dashboard import get_assessment_overview, get_faculty_summary

log = logging.getLogger(__name__)

bp = Blueprint("faculty", __name__, url_prefix="/faculty")


@contextmanager
def closing_connection():
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def _account():
    return auth_module.current_account()


def scope():
    """Class ids the caller may manage, or None for an admin (all classes)."""
    return auth_module.owned_class_ids()


def _owned_or_404(class_id):
    auth_module.require_class_owner(class_id)
    return class_id


def _class_filter_sql(column, class_ids):
    """Build ``AND column IN (?, ?, ...)`` for the caller's classes."""
    if class_ids is None:
        return "", []
    if not class_ids:
        return "AND 1 = 0", []
    placeholders = ", ".join("?" for _ in class_ids)
    return f"AND {column} IN ({placeholders})", list(class_ids)


# --------------------------------------------------------------- dashboard
@bp.route("/dashboard")
@auth_module.faculty_required
def dashboard():
    classes = _visible_classes()
    selected_class_id = request.args.get("class_id", type=int)
    if selected_class_id is not None:
        _owned_or_404(selected_class_id)
        if not any(item["class_id"] == selected_class_id for item in classes):
            abort(403)

    summary = get_faculty_summary(class_id=selected_class_id, class_ids=scope())
    assessments = get_assessment_overview(
        class_id=selected_class_id, class_ids=scope()
    )

    risk_predictions = {}
    risk_lookup_error = None
    if summary["students"]:
        try:
            # Load the numerical/ML stack only when a faculty dashboard is opened.
            # Student tools and public pages should not pay its import cost.
            from modules import risk_model

            risk_predictions = risk_model.predict_students(
                [student["student_id"] for student in summary["students"]],
                class_ids=auth_module.owned_class_ids(),
            )
        except Exception:  # noqa: BLE001 - a model error must not crash the page
            risk_lookup_error = (
                "Risk estimates are unavailable right now because there is not "
                "enough data to calculate them. The academic records above are "
                "unaffected."
            )

    return render_template(
        "risk.html",
        summary=summary,
        assessments=assessments,
        classes=classes,
        selected_class_id=selected_class_id,
        error=None,
        risk_predictions=risk_predictions,
        risk_lookup_error=risk_lookup_error,
    )


def _visible_classes():
    class_ids = scope()
    condition, params = _class_filter_sql("class_id", class_ids)
    with closing_connection() as connection:
        rows = connection.execute(
            f"""SELECT class_id, class_name, program, semester, section
                  FROM faculty_classes
                 WHERE 1 = 1 {condition}
                 ORDER BY class_name""",
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------- record manager
@bp.route("/manage", methods=["GET", "POST"])
@auth_module.faculty_required
def manage():
    """Maintain students, attendance, marks and assessments for owned classes."""
    account = _account()
    class_ids = scope()
    error = None

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            with closing_connection() as connection:
                if action == "add_student":
                    class_id = int(request.form.get("class_id", ""))
                    _owned_or_404(class_id)
                    name = request.form.get("name", "").strip()
                    semester = int(request.form.get("semester", ""))
                    section = request.form.get("section", "").strip().upper()
                    email = request.form.get("email", "").strip() or None
                    if not name or semester < 1 or not section:
                        raise ValueError("Enter a name, valid semester and section.")
                    connection.execute(
                        """INSERT INTO students (name, email, semester, section, class_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        (name, email, semester, section, class_id),
                    )
                    student_id = last_insert_id(connection, "students", "student_id")
                    connection.execute(
                        """INSERT INTO assessment_submissions
                               (assessment_id, student_id, submitted)
                           SELECT assessment_id, ?, 0 FROM assessment_items""",
                        (student_id,),
                    )
                    flash("Student added successfully.", "success")

                elif action == "edit_student":
                    student_id = int(request.form.get("student_id", ""))
                    auth_module.require_student_ids([student_id])
                    name = request.form.get("name", "").strip()
                    semester = int(request.form.get("semester", ""))
                    section = request.form.get("section", "").strip().upper()
                    email = request.form.get("email", "").strip() or None
                    if not name or semester < 1 or not section:
                        raise ValueError("Enter a name, valid semester and section.")
                    connection.execute(
                        """UPDATE students
                              SET name = ?, email = ?, semester = ?, section = ?,
                                  class_id = CASE
                                      WHEN semester != ? OR upper(section) != ? THEN NULL
                                      ELSE class_id
                                  END
                            WHERE student_id = ?""",
                        (name, email, semester, section, semester, section, student_id),
                    )
                    flash("Student details updated.", "success")

                elif action == "create_subject":
                    subject_name = request.form.get("subject_name", "").strip()
                    subject_code = request.form.get("subject_code", "").strip().upper() or None
                    if not subject_name:
                        raise ValueError("Enter a subject name.")
                    connection.execute(
                        "INSERT INTO subjects (subject_name, subject_code) VALUES (?, ?)",
                        (subject_name, subject_code),
                    )
                    flash("Subject added.", "success")

                elif action == "create_class":
                    _create_class(connection, account)

                elif action == "save_attendance":
                    # Authorization first: a caller who does not own this student
                    # gets 403 regardless of how malformed the rest of the body is.
                    student_id = int(request.form.get("student_id", ""))
                    auth_module.require_student_ids([student_id])
                    subject_id = int(request.form.get("subject_id", ""))
                    total = int(request.form.get("total_classes", ""))
                    attended = int(request.form.get("attended_classes", ""))
                    if total < 1 or attended < 0 or attended > total:
                        raise ValueError(
                            "Attendance must satisfy 0 <= attended classes <= total classes."
                        )
                    connection.execute(
                        """INSERT INTO attendance
                               (student_id, subject_id, total_classes, attended_classes)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(student_id, subject_id) DO UPDATE SET
                               total_classes = excluded.total_classes,
                               attended_classes = excluded.attended_classes""",
                        (student_id, subject_id, total, attended),
                    )
                    flash("Attendance saved.", "success")

                elif action == "save_marks":
                    student_id = int(request.form.get("student_id", ""))
                    auth_module.require_student_ids([student_id])
                    subject_id = int(request.form.get("subject_id", ""))
                    exam_name = request.form.get("exam_name", "")
                    obtained = float(request.form.get("marks_obtained", ""))
                    maximum = float(request.form.get("max_marks", ""))
                    if exam_name not in ("Midterm", "End Term"):
                        raise ValueError("Choose Midterm or End Term.")
                    if maximum <= 0 or obtained < 0 or obtained > maximum:
                        raise ValueError("Marks must be between zero and the maximum marks.")
                    connection.execute(
                        "DELETE FROM marks WHERE student_id = ? AND subject_id = ? AND exam_name = ?",
                        (student_id, subject_id, exam_name),
                    )
                    connection.execute(
                        """INSERT INTO marks
                               (student_id, subject_id, exam_name, marks_obtained,
                                max_marks, exam_date)
                           VALUES (?, ?, ?, ?, ?, date('now'))""",
                        (student_id, subject_id, exam_name, obtained, maximum),
                    )
                    flash(f"{exam_name} marks saved.", "success")

                elif action == "create_assessment":
                    subject_id = int(request.form.get("subject_id", ""))
                    assessment_type = request.form.get("assessment_type", "")
                    title = request.form.get("title", "").strip()
                    due_date = request.form.get("due_date", "").strip() or None
                    if assessment_type not in ("assignment", "term_work") or not title:
                        raise ValueError("Choose an assessment type and enter a title.")
                    cursor = connection.execute(
                        """INSERT INTO assessment_items
                               (subject_id, assessment_type, title, due_date)
                           VALUES (?, ?, ?, ?)""",
                        (subject_id, assessment_type, title, due_date),
                    )
                    assessment_id = last_insert_id(connection, "assessment_items",
                                                   "assessment_id")
                    connection.execute(
                        """INSERT INTO assessment_submissions
                               (assessment_id, student_id, submitted)
                           SELECT ?, student_id, 0 FROM students""",
                        (assessment_id,),
                    )
                    flash("Assessment created for all current students.", "success")

                elif action == "save_submission":
                    assessment_id = int(request.form.get("assessment_id", ""))
                    student_id = int(request.form.get("student_id", ""))
                    auth_module.require_student_ids([student_id])
                    submitted = 1 if request.form.get("submitted") == "1" else 0
                    connection.execute(
                        """INSERT INTO assessment_submissions
                               (assessment_id, student_id, submitted, updated_at)
                           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(assessment_id, student_id) DO UPDATE SET
                               submitted = excluded.submitted,
                               updated_at = CURRENT_TIMESTAMP""",
                        (assessment_id, student_id, submitted),
                    )
                    flash("Submission status updated.", "success")

                else:
                    raise ValueError("Choose a valid action.")

                connection.commit()
        except ValueError:
            error = "Please enter valid values in all required fields."
        except IntegrityError as exc:
            error = _integrity_message(exc)
        except DatabaseError:
            log.exception("record save failed")
            error = "Could not save the record. Check the selected student and subject."

        # POST-redirect-GET: a reload or a browser back button cannot resubmit
        # the form. Errors stay on this page so the values are not lost.
        if error is None:
            return redirect(url_for("faculty.manage"))

    data = _manage_page_data(class_ids)
    return render_template(
        "faculty_manage.html",
        classes=_visible_classes(),
        message=request.args.get("message"),
        error=error,
        **data,
    )


def _integrity_message(exc):
    text = str(exc).lower()
    if "assessment_items" in text:
        return "That assessment title already exists for this subject and type."
    if "subject_code" in text:
        return "That subject code is already in use."
    if "students.email" in text or "students_email" in text:
        return "That email address is already in use."
    return "Could not save the record. Check the selected student, subject and assessment."


def _manage_page_data(class_ids):
    condition, params = _class_filter_sql("s.class_id", class_ids)
    with closing_connection() as connection:
        students = [dict(row) for row in connection.execute(
            f"""SELECT s.student_id, s.name, s.semester, s.section, s.class_id
                  FROM students AS s
                 WHERE 1 = 1 {condition}
                 ORDER BY s.name""",
            tuple(params),
        ).fetchall()]
        subjects = [dict(row) for row in connection.execute(
            "SELECT subject_id, subject_name FROM subjects ORDER BY subject_name"
        ).fetchall()]
        assessments = [dict(row) for row in connection.execute(
            """SELECT ai.assessment_id, ai.title, ai.assessment_type, sub.subject_name
                 FROM assessment_items ai
                 JOIN subjects sub ON sub.subject_id = ai.subject_id
                ORDER BY ai.assessment_type, ai.title"""
        ).fetchall()]
        submissions = [dict(row) for row in connection.execute(
            f"""SELECT ss.assessment_id, ss.student_id, ss.submitted,
                       s.name AS student_name, ai.title, ai.assessment_type
                  FROM assessment_submissions ss
                  JOIN students s ON s.student_id = ss.student_id
                  JOIN assessment_items ai ON ai.assessment_id = ss.assessment_id
                 WHERE 1 = 1 {condition}
                 ORDER BY ai.assessment_type, ai.title, s.name""",
            tuple(params),
        ).fetchall()]
        saved_marks = [dict(row) for row in connection.execute(
            f"""SELECT m.student_id, s.name AS student_name, m.subject_id,
                       sub.subject_name, m.exam_name, m.marks_obtained, m.max_marks,
                       m.exam_date
                  FROM marks m
                  JOIN students s ON s.student_id = m.student_id
                  JOIN subjects sub ON sub.subject_id = m.subject_id
                 WHERE 1 = 1 {condition}
                 ORDER BY s.name, sub.subject_name, m.exam_name""",
            tuple(params),
        ).fetchall()]
        saved_attendance = [dict(row) for row in connection.execute(
            f"""SELECT a.student_id, s.name AS student_name, a.subject_id,
                       sub.subject_name, a.attended_classes, a.total_classes
                  FROM attendance a
                  JOIN students s ON s.student_id = a.student_id
                  JOIN subjects sub ON sub.subject_id = a.subject_id
                 WHERE 1 = 1 {condition}
                 ORDER BY s.name, sub.subject_name""",
            tuple(params),
        ).fetchall()]

    return {
        "students": students,
        "subjects": subjects,
        "assessments": assessments,
        "submissions": submissions,
        "saved_marks": saved_marks,
        "saved_attendance": saved_attendance,
    }


# -------------------------------------------------------- class management
def _create_class(connection, account):
    class_name = request.form.get("class_name", "").strip()
    program = request.form.get("program", "").strip()
    semester = int(request.form.get("semester", ""))
    section = request.form.get("section", "").strip().upper()
    description = request.form.get("description", "").strip()
    if not class_name or not program or semester < 1 or not section:
        raise ValueError("Enter a class name, program, valid semester and section.")
    if not account.teacher_id:
        raise ValueError("Your faculty account is not linked to a teacher record yet.")
    connection.execute(
        """INSERT INTO faculty_classes
               (class_name, program, semester, section, description, owner_teacher_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (class_name, program, semester, section, description, account.teacher_id),
    )
    return last_insert_id(connection, "faculty_classes", "class_id")


@bp.route("/classes", methods=["GET", "POST"])
@auth_module.faculty_required
def classes():
    """Create custom classes and manage the students inside them."""
    account = _account()
    class_ids = scope()
    error = None
    selected_class_id = request.args.get("class_id", type=int)
    if selected_class_id is not None:
        _owned_or_404(selected_class_id)

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            with closing_connection() as connection:
                if action == "create_class":
                    selected_class_id = _create_class(connection, account)
                    flash("Custom class created. It is ready for students.", "success")
                elif action == "add_student_to_class":
                    selected_class_id = int(request.form.get("class_id", ""))
                    _owned_or_404(selected_class_id)
                    name = request.form.get("name", "").strip()
                    email = request.form.get("email", "").strip() or None
                    class_row = connection.execute(
                        "SELECT semester, section FROM faculty_classes WHERE class_id = ?",
                        (selected_class_id,),
                    ).fetchone()
                    if class_row is None or not name:
                        raise ValueError("Choose a class and enter the student's name.")
                    connection.execute(
                        """INSERT INTO students (name, email, semester, section, class_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        (name, email, class_row["semester"], class_row["section"],
                         selected_class_id),
                    )
                    flash("Student added to the selected class.", "success")
                elif action == "move_student":
                    student_id = int(request.form.get("student_id", ""))
                    selected_class_id = int(request.form.get("class_id", ""))
                    auth_module.require_student_ids([student_id])
                    _owned_or_404(selected_class_id)
                    connection.execute(
                        "UPDATE students SET class_id = ? WHERE student_id = ?",
                        (selected_class_id, student_id),
                    )
                    flash("Student assigned to the selected class.", "success")
                else:
                    raise ValueError("Choose a valid class action.")
                connection.commit()
        except ValueError as exc:
            message = str(exc)
            error = ("Enter a valid semester number."
                     if "invalid literal for int()" in message else message)
        except IntegrityError as exc:
            error = ("That class name already exists. Choose a different name."
                     if "faculty_classes" in str(exc)
                     else "Could not save this record. Check the email or selected class.")
        except DatabaseError:
            log.exception("class save failed")
            error = "Could not save the class record."
        except Exception as exc:  # noqa: BLE001 - surfaced as a page message
            # Authorization failures (403/404) must reach Flask, not be turned
            # into a 200 with an error banner.
            from werkzeug.exceptions import HTTPException

            if isinstance(exc, HTTPException):
                raise
            log.exception("class action failed")
            error = "Could not save the class record. Check the values and try again."

        if error is None:
            return redirect(url_for("faculty.classes", class_id=selected_class_id))

    data = _classes_page_data(class_ids, selected_class_id)
    return render_template(
        "faculty_classes.html",
        classes=data["classes"],
        selected_class=data["selected_class"],
        selected_class_id=data["selected_class_id"],
        class_students=data["class_students"],
        unassigned_students=data["unassigned_students"],
        message=request.args.get("message"),
        error=error,
    )


def _classes_page_data(class_ids, selected_class_id):
    condition, params = _class_filter_sql("c.class_id", class_ids)
    with closing_connection() as connection:
        classes = [dict(row) for row in connection.execute(
            f"""SELECT c.class_id, c.class_name, c.program, c.semester, c.section,
                       c.description, COUNT(s.student_id) AS student_count
                  FROM faculty_classes c
                  LEFT JOIN students s ON s.class_id = c.class_id
                 WHERE 1 = 1 {condition}
                 GROUP BY c.class_id
                 ORDER BY c.created_at, c.class_name""",
            tuple(params),
        ).fetchall()]

        if selected_class_id and not any(c["class_id"] == selected_class_id
                                         for c in classes):
            selected_class_id = None
        if selected_class_id is None and classes:
            selected_class_id = classes[0]["class_id"]

        selected_class = next(
            (c for c in classes if c["class_id"] == selected_class_id), None)
        class_students, unassigned_students = [], []
        if selected_class:
            class_students = [dict(row) for row in connection.execute(
                """SELECT student_id, name, email, semester, section
                     FROM students WHERE class_id = ? ORDER BY name""",
                (selected_class_id,),
            ).fetchall()]
            # "Unassigned" only lists students of the caller's own classes:
            # moving a student between classes is still an ownership change.
            unassigned_condition, unassigned_params = _class_filter_sql(
                "class_id", class_ids)
            unassigned_students = [dict(row) for row in connection.execute(
                f"""SELECT student_id, name, semester, section FROM students
                     WHERE class_id IS NULL {unassigned_condition} ORDER BY name""",
                tuple(unassigned_params),
            ).fetchall()]

    return {
        "classes": classes,
        "selected_class": selected_class,
        "selected_class_id": selected_class_id,
        "class_students": class_students,
        "unassigned_students": unassigned_students,
    }


# ------------------------------------------------------------------ admin
@bp.route("/admin")
@auth_module.admin_required
def admin_dashboard():
    """Combined Admin landing page backed only by current database records."""
    try:
        with closing_connection() as connection:
            table = profiles_table(connection)
            role_counts = {row["role"]: row["total"] for row in connection.execute(
                f"SELECT role, COUNT(*) AS total FROM {table} GROUP BY role"
            ).fetchall()}
            class_count = connection.execute(
                "SELECT COUNT(*) AS total FROM faculty_classes"
            ).fetchone()["total"]
    except DatabaseError:
        log.exception("admin dashboard summary could not be loaded")
        flash("Some workspace totals are unavailable right now.", "warning")
        role_counts = {}
        class_count = None
    return render_template(
        "admin/dashboard.html",
        student_count=role_counts.get("student"),
        faculty_count=role_counts.get("faculty"),
        admin_count=role_counts.get("admin"),
        class_count=class_count,
    )


@bp.route("/admin/users")
@auth_module.admin_required
def admin_users():
    """Searchable Admin-only directory of trusted account profiles."""
    query = (request.args.get("q") or "").strip()[:120]
    selected_role = (request.args.get("role") or "all").strip().lower()
    if selected_role not in ("all", "student", "faculty", "admin"):
        selected_role = "all"

    try:
        with closing_connection() as connection:
            table = profiles_table(connection)
            conditions = []
            params = []
            if query:
                conditions.append(
                    "(lower(COALESCE(email, '')) LIKE lower(?) "
                    "OR lower(COALESCE(display_name, '')) LIKE lower(?))"
                )
                pattern = f"%{query}%"
                params.extend((pattern, pattern))
            if selected_role != "all":
                conditions.append("role = ?")
                params.append(selected_role)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            profiles = [dict(row) for row in connection.execute(
                f"""SELECT user_id, email, display_name, role
                      FROM {table}{where} ORDER BY role, email""",
                tuple(params),
            ).fetchall()]
            teachers = [dict(row) for row in connection.execute(
                "SELECT teacher_id, name, email FROM teachers ORDER BY name"
            ).fetchall()]
    except DatabaseError:
        log.exception("admin user directory could not be loaded")
        flash("The account directory could not be loaded. Please try again.", "danger")
        profiles, teachers = [], []

    return render_template(
        "admin/users.html",
        profiles=profiles,
        teachers=teachers,
        search_query=query,
        selected_role=selected_role,
    )


@bp.route("/admin/set-role", methods=["POST"])
@auth_module.admin_required
def admin_set_role():
    """Change a non-admin account between Student and Faculty atomically."""
    account = _account()
    email = (request.form.get("email") or "").strip().lower()
    role = (request.form.get("role") or "").strip().lower()
    search_query = (request.form.get("q") or "").strip()[:120]
    selected_role = (request.form.get("filter_role") or "all").strip().lower()
    if selected_role not in ("all", "student", "faculty", "admin"):
        selected_role = "all"
    redirect_url = url_for(
        "faculty.admin_users", q=search_query, role=selected_role
    )

    if role not in ("student", "faculty"):
        flash("Choose Student or Faculty as the new role.", "danger")
        return redirect(redirect_url)
    if not email or email == (account.email or "").lower():
        flash("You cannot change your own role.", "danger")
        return redirect(redirect_url)

    try:
        with closing_connection() as connection:
            table = profiles_table(connection)
            profile = connection.execute(
                f"SELECT user_id, email, role, display_name FROM {table} "
                "WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
            if profile is None:
                flash("No profile found for that email.", "danger")
                return redirect(redirect_url)
            if str(profile["user_id"]) == str(account.user_id):
                flash("You cannot change your own role.", "danger")
                return redirect(redirect_url)
            current_role = (profile["role"] or "").strip().lower()
            if current_role == "admin":
                flash("Administrator accounts are protected from role changes.", "danger")
                return redirect(redirect_url)
            if current_role not in ("student", "faculty"):
                flash("That account has an unsupported role and was not changed.", "danger")
                return redirect(redirect_url)
            if current_role == role:
                flash(f"{email} already has the {role} role.", "info")
                return redirect(redirect_url)

            if role == "faculty":
                existing = connection.execute(
                    "SELECT teacher_id FROM teachers WHERE auth_user_id = ?",
                    (profile["user_id"],),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """INSERT INTO teachers (auth_user_id, name, email)
                           VALUES (?, ?, ?)
                           ON CONFLICT (auth_user_id) DO NOTHING""",
                        (profile["user_id"],
                         profile["display_name"] or profile["email"],
                         profile["email"]),
                    )
                connection.execute(
                    f"UPDATE {table} SET role = ? WHERE user_id = ?",
                    (role, profile["user_id"]),
                )
            else:
                connection.execute(
                    f"UPDATE {table} SET role = ? WHERE user_id = ?",
                    (role, profile["user_id"]),
                )
                connection.execute(
                    "UPDATE teachers SET auth_user_id = NULL WHERE auth_user_id = ?",
                    (profile["user_id"],),
                )
            connection.commit()
        log.info("admin %s set role of %s to %s", account.user_id, email, role)
        flash(
            f"{email} is now {role}. The new dashboard access takes effect "
            "the next time this account signs in.",
            "success",
        )
    except DatabaseError:
        log.exception("role change failed")
        try:
            connection.rollback()
        except Exception:  # noqa: BLE001 - connection may already be closed
            pass
        flash("Could not change that role. The previous role has been kept.", "danger")
    return redirect(redirect_url)
