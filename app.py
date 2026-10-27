
import sqlite3
from contextlib import closing

from flask import Flask, render_template, request

from attendance_calculator import classes_needed, classes_missable
from database import get_connection, initialize_database
from modules.faculty_dashboard import get_assessment_overview, get_faculty_summary

# The classroom finder needs the compiled C library (c_core/core.dll).
# If it can't be loaded, the rest of the app should still work.
try:
    from modules import classroom
    CLASSROOM_ERROR = None
except (OSError, AttributeError):
    classroom = None
    CLASSROOM_ERROR = (
        "The C library could not be loaded. Build it with: "
        "gcc -shared -DCORE_BUILD_DLL -o c_core\\core.dll c_core\\core.c"
    )

app = Flask(__name__)

DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday",
             4: "Thursday", 5: "Friday"}
DAY_START = 9 * 60    # 09:00, start of the free-slot search window
DAY_END = 18 * 60     # 18:00, end of the free-slot search window


def to_minutes(hhmm):
    """Convert 'HH:MM' to minutes after midnight."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(minutes):
    """Convert minutes after midnight to 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def find_rooms(day, start, end):
    """Check every room for one day and time window using the C library."""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT timetable_id, room_number, day_of_week, "
            "start_time, end_time FROM timetable"
        ).fetchall()

    # Plain dicts: the ctypes wrapper calls row.get(), which sqlite3.Row lacks.
    bookings = [
        {
            "booking_id": r["timetable_id"],
            "room": r["room_number"],
            "section": "A",   # section is not needed for room availability
            "day_of_week": r["day_of_week"],
            "start_minute": to_minutes(r["start_time"]),
            "end_minute": to_minutes(r["end_time"]),
        }
        for r in rows
    ]

    with closing(get_connection()) as conn:
        locations = {
            row["room_number"]: dict(row)
            for row in conn.execute(
                "SELECT room_number, building, floor, room_type FROM room_locations"
            ).fetchall()
        }

    results = []
    for room in sorted({b["room"] for b in bookings}):
        is_free = classroom.is_room_free(bookings, room, day, start, end)
        if not is_free:
            continue
        location = locations.get(room, {})
        results.append({
            "room": room,
            "building": location.get("building") or "Not set",
            "floor": location.get("floor") or "Not set",
            "room_type": location.get("room_type") or ("Laboratory" if room.upper().startswith("LAB") else "Classroom"),
        })

    clashes = classroom.detect_clashes(bookings, day)
    summary = {
        "free_count": len(results),
        "room_count": len({b["room"] for b in bookings}),
        "clash_count": len(clashes),
    }
    return results, summary


@app.route("/")
def home():
    return render_template("base.html")


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    result = None
    error = None

    if request.method == "POST":
        try:
            attended = int(request.form["attended"])
            total = int(request.form["total"])
            upcoming = int(request.form["upcoming"])
            target_percent = float(request.form["target"])
        except (ValueError, KeyError):
            error = "Enter valid numbers for all fields."
        else:
            target = target_percent / 100
            try:
                if total == 0:
                    raise ValueError("Total classes must be greater than zero.")
                if attended < 0 or attended > total:
                    raise ValueError(
                        "Attended classes must be between 0 and total classes."
                    )
                if upcoming < 0:
                    raise ValueError("Upcoming classes cannot be negative.")
                if not 0 < target <= 1:
                    raise ValueError(
                        "Target must be greater than 0 and at most 100%."
                    )

                result = {
                    "current_percent": attended / total * 100,
                    "target_percent": target_percent,
                    "needed": classes_needed(attended, total, target),
                    "missable": classes_missable(attended, total, upcoming, target),
                    "attended": attended,
                    "total": total,
                    "upcoming": upcoming,
                }
            except ValueError as exc:
                error = str(exc)

    return render_template("attendance.html", result=result, error=error)


@app.route("/classrooms", methods=["GET", "POST"])
def classrooms():
    form = {"day": "1", "start": "10:00", "end": "11:00"}
    results = None
    summary = None
    error = CLASSROOM_ERROR

    if classroom is not None and request.method == "POST":
        form = {
            "day": request.form.get("day", "1"),
            "start": request.form.get("start", ""),
            "end": request.form.get("end", ""),
        }
        try:
            day = int(form["day"])
            start = to_minutes(form["start"])
            end = to_minutes(form["end"])
        except ValueError:
            error = "Choose a day and enter both times."
        else:
            if day not in DAY_NAMES:
                error = "Choose a day from Monday to Friday."
            elif not 0 <= start < end <= 24 * 60:
                error = "Enter a start time that is earlier than the end time."
            else:
                try:
                    results, summary = find_rooms(day, start, end)
                except sqlite3.OperationalError:
                    error = "Database tables are not ready. Run: python database.py. Only use seed_data.py for disposable demo data because it clears existing records."
                else:
                    if not results:
                        error = "No timetable entries found. Add timetable data, or use seed_data.py only for disposable demo data because it clears existing records."

    return render_template(
        "classrooms.html",
        form=form, days=DAY_NAMES, results=results,
        summary=summary, error=error,
    )


@app.route("/faculty/manage", methods=["GET", "POST"])
def faculty_manage():
    """Allow faculty to maintain students, attendance, marks and assessments."""
    message = request.args.get("message")
    error = None

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            with closing(get_connection()) as conn:
                if action == "add_student":
                    name = request.form.get("name", "").strip()
                    semester = int(request.form.get("semester", ""))
                    section = request.form.get("section", "").strip().upper()
                    email = request.form.get("email", "").strip() or None
                    if not name or semester < 1 or not section:
                        raise ValueError("Enter a name, valid semester and section.")
                    cursor = conn.execute(
                        "INSERT INTO students (name, email, semester, section) VALUES (?, ?, ?, ?)",
                        (name, email, semester, section),
                    )
                    student_id = cursor.lastrowid
                    conn.execute(
                        """INSERT INTO assessment_submissions
                           (assessment_id, student_id, submitted)
                           SELECT assessment_id, ?, 0 FROM assessment_items""",
                        (student_id,),
                    )
                    message = "Student added successfully."

                elif action == "edit_student":
                    student_id = int(request.form.get("student_id", ""))
                    name = request.form.get("name", "").strip()
                    semester = int(request.form.get("semester", ""))
                    section = request.form.get("section", "").strip().upper()
                    email = request.form.get("email", "").strip() or None
                    if not name or semester < 1 or not section:
                        raise ValueError("Enter a name, valid semester and section.")
                    conn.execute(
                        "UPDATE students SET name = ?, email = ?, semester = ?, section = ? WHERE student_id = ?",
                        (name, email, semester, section, student_id),
                    )
                    message = "Student details updated."

                elif action == "create_subject":
                    subject_name = request.form.get("subject_name", "").strip()
                    subject_code = request.form.get("subject_code", "").strip().upper() or None
                    if not subject_name:
                        raise ValueError("Enter a subject name.")
                    conn.execute(
                        "INSERT INTO subjects (subject_name, subject_code) VALUES (?, ?)",
                        (subject_name, subject_code),
                    )
                    message = "Subject added."

                elif action == "save_attendance":
                    student_id = int(request.form.get("student_id", ""))
                    subject_id = int(request.form.get("subject_id", ""))
                    total = int(request.form.get("total_classes", ""))
                    attended = int(request.form.get("attended_classes", ""))
                    if total < 1 or attended < 0 or attended > total:
                        raise ValueError("Attendance must satisfy 0 <= attended classes <= total classes.")
                    conn.execute(
                        """INSERT INTO attendance
                           (student_id, subject_id, total_classes, attended_classes)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(student_id, subject_id) DO UPDATE SET
                           total_classes = excluded.total_classes,
                           attended_classes = excluded.attended_classes""",
                        (student_id, subject_id, total, attended),
                    )
                    message = "Attendance saved."

                elif action == "save_marks":
                    student_id = int(request.form.get("student_id", ""))
                    subject_id = int(request.form.get("subject_id", ""))
                    exam_name = request.form.get("exam_name", "")
                    obtained = float(request.form.get("marks_obtained", ""))
                    maximum = float(request.form.get("max_marks", ""))
                    if exam_name not in ("Midterm", "End Term"):
                        raise ValueError("Choose Midterm or End Term.")
                    if maximum <= 0 or obtained < 0 or obtained > maximum:
                        raise ValueError("Marks must be between zero and the maximum marks.")
                    conn.execute(
                        "DELETE FROM marks WHERE student_id = ? AND subject_id = ? AND exam_name = ?",
                        (student_id, subject_id, exam_name),
                    )
                    conn.execute(
                        """INSERT INTO marks
                           (student_id, subject_id, exam_name, marks_obtained, max_marks, exam_date)
                           VALUES (?, ?, ?, ?, ?, date('now'))""",
                        (student_id, subject_id, exam_name, obtained, maximum),
                    )
                    message = f"{exam_name} marks saved."

                elif action == "create_assessment":
                    subject_id = int(request.form.get("subject_id", ""))
                    assessment_type = request.form.get("assessment_type", "")
                    title = request.form.get("title", "").strip()
                    due_date = request.form.get("due_date", "").strip() or None
                    if assessment_type not in ("assignment", "term_work") or not title:
                        raise ValueError("Choose an assessment type and enter a title.")
                    cursor = conn.execute(
                        """INSERT INTO assessment_items
                           (subject_id, assessment_type, title, due_date)
                           VALUES (?, ?, ?, ?)""",
                        (subject_id, assessment_type, title, due_date),
                    )
                    assessment_id = cursor.lastrowid
                    conn.execute(
                        """INSERT INTO assessment_submissions (assessment_id, student_id, submitted)
                           SELECT ?, student_id, 0 FROM students""",
                        (assessment_id,),
                    )
                    message = "Assessment created for all current students."

                elif action == "save_submission":
                    assessment_id = int(request.form.get("assessment_id", ""))
                    student_id = int(request.form.get("student_id", ""))
                    submitted = 1 if request.form.get("submitted") == "1" else 0
                    conn.execute(
                        """INSERT INTO assessment_submissions
                           (assessment_id, student_id, submitted, updated_at)
                           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(assessment_id, student_id) DO UPDATE SET
                           submitted = excluded.submitted, updated_at = CURRENT_TIMESTAMP""",
                        (assessment_id, student_id, submitted),
                    )
                    message = "Submission status updated."
                else:
                    raise ValueError("Choose a valid action.")

                conn.commit()
        except (ValueError, TypeError):
            error = "Please enter valid values in all required fields."
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: assessment_items" in str(exc):
                error = "That assessment title already exists for this subject and type."
            elif "UNIQUE constraint failed: subjects.subject_code" in str(exc):
                error = "That subject code is already in use."
            elif "UNIQUE constraint failed: students.email" in str(exc):
                error = "That email address is already in use."
            else:
                error = "Could not save the record. Check the selected student, subject and assessment."
        except sqlite3.Error:
            error = "Could not save the record. Make sure the database is initialized."

    with closing(get_connection()) as conn:
        students = [dict(row) for row in conn.execute(
            "SELECT student_id, name, semester, section FROM students ORDER BY name"
        ).fetchall()]
        subjects = [dict(row) for row in conn.execute(
            "SELECT subject_id, subject_name FROM subjects ORDER BY subject_name"
        ).fetchall()]
        assessments = [dict(row) for row in conn.execute(
            """SELECT ai.assessment_id, ai.title, ai.assessment_type, sub.subject_name
               FROM assessment_items ai JOIN subjects sub ON sub.subject_id = ai.subject_id
               ORDER BY ai.assessment_type, ai.title"""
        ).fetchall()]
        submissions = [dict(row) for row in conn.execute(
            """SELECT ss.assessment_id, ss.student_id, ss.submitted,
                      s.name AS student_name, ai.title, ai.assessment_type
               FROM assessment_submissions ss
               JOIN students s ON s.student_id = ss.student_id
               JOIN assessment_items ai ON ai.assessment_id = ss.assessment_id
               ORDER BY ai.assessment_type, ai.title, s.name"""
        ).fetchall()]
        saved_marks = [dict(row) for row in conn.execute(
            """SELECT m.student_id, s.name AS student_name, m.subject_id, sub.subject_name,
                      m.exam_name, m.marks_obtained, m.max_marks, m.exam_date
               FROM marks m
               JOIN students s ON s.student_id = m.student_id
               JOIN subjects sub ON sub.subject_id = m.subject_id
               ORDER BY s.name, sub.subject_name, m.exam_name"""
        ).fetchall()]
        saved_attendance = [dict(row) for row in conn.execute(
            """SELECT a.student_id, s.name AS student_name, a.subject_id, sub.subject_name,
                      a.attended_classes, a.total_classes
               FROM attendance a
               JOIN students s ON s.student_id = a.student_id
               JOIN subjects sub ON sub.subject_id = a.subject_id
               ORDER BY s.name, sub.subject_name"""
        ).fetchall()]
    return render_template(
        "faculty_manage.html", students=students, subjects=subjects,
        assessments=assessments, submissions=submissions,
        saved_marks=saved_marks, saved_attendance=saved_attendance,
        message=message, error=error,
    )


@app.route("/faculty/classes", methods=["GET", "POST"])
def faculty_classes():
    """Create custom faculty classes and manage their student lists."""
    message = request.args.get("message")
    error = None
    selected_class_id = request.args.get("class_id", type=int)

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            with closing(get_connection()) as conn:
                if action == "create_class":
                    class_name = request.form.get("class_name", "").strip()
                    program = request.form.get("program", "").strip()
                    semester = int(request.form.get("semester", ""))
                    section = request.form.get("section", "").strip().upper()
                    description = request.form.get("description", "").strip()
                    if not class_name or not program or semester < 1 or not section:
                        raise ValueError("Enter a class name, program, valid semester and section.")
                    cursor = conn.execute(
                        """INSERT INTO faculty_classes
                           (class_name, program, semester, section, description)
                           VALUES (?, ?, ?, ?, ?)""",
                        (class_name, program, semester, section, description),
                    )
                    selected_class_id = cursor.lastrowid
                    message = "Custom class created. It is ready for students."
                elif action == "add_student_to_class":
                    selected_class_id = int(request.form.get("class_id", ""))
                    name = request.form.get("name", "").strip()
                    email = request.form.get("email", "").strip() or None
                    class_row = conn.execute(
                        "SELECT semester, section FROM faculty_classes WHERE class_id = ?",
                        (selected_class_id,),
                    ).fetchone()
                    if class_row is None or not name:
                        raise ValueError("Choose a class and enter the student's name.")
                    conn.execute(
                        """INSERT INTO students (name, email, semester, section, class_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        (name, email, class_row["semester"], class_row["section"], selected_class_id),
                    )
                    message = "Student added to the selected class."
                elif action == "move_student":
                    student_id = int(request.form.get("student_id", ""))
                    selected_class_id = int(request.form.get("class_id", ""))
                    class_row = conn.execute(
                        "SELECT semester, section FROM faculty_classes WHERE class_id = ?",
                        (selected_class_id,),
                    ).fetchone()
                    student_row = conn.execute(
                        "SELECT student_id FROM students WHERE student_id = ?",
                        (student_id,),
                    ).fetchone()
                    if class_row is None or student_row is None:
                        raise ValueError("Choose an existing student and class.")
                    conn.execute(
                        """UPDATE students SET class_id = ?, semester = ?, section = ?
                           WHERE student_id = ?""",
                        (selected_class_id, class_row["semester"], class_row["section"], student_id),
                    )
                    message = "Student assigned to the selected class."
                else:
                    raise ValueError("Choose a valid class action.")
                conn.commit()
        except ValueError:
            error = "Please enter valid values in all required fields."
        except sqlite3.IntegrityError as exc:
            error = ("That class name already exists. Choose a different name."
                     if "faculty_classes.class_name" in str(exc)
                     else "Could not save this record. Check the email or selected class.")
        except sqlite3.Error:
            error = "Could not save the class record. Make sure the database is initialized."

    with closing(get_connection()) as conn:
        classes = [dict(row) for row in conn.execute(
            """SELECT c.class_id, c.class_name, c.program, c.semester, c.section,
                      c.description, COUNT(s.student_id) AS student_count
               FROM faculty_classes c LEFT JOIN students s ON s.class_id = c.class_id
               GROUP BY c.class_id ORDER BY c.created_at, c.class_name"""
        ).fetchall()]
        if selected_class_id and not any(c["class_id"] == selected_class_id for c in classes):
            selected_class_id = None
        if selected_class_id is None and classes:
            selected_class_id = classes[0]["class_id"]
        selected_class = next((c for c in classes if c["class_id"] == selected_class_id), None)
        class_students = []
        unassigned_students = []
        if selected_class:
            class_students = [dict(row) for row in conn.execute(
                """SELECT student_id, name, email, semester, section
                   FROM students WHERE class_id = ? ORDER BY name""",
                (selected_class_id,),
            ).fetchall()]
            unassigned_students = [dict(row) for row in conn.execute(
                """SELECT student_id, name, semester, section FROM students
                   WHERE class_id IS NULL ORDER BY name"""
            ).fetchall()]

    return render_template(
        "faculty_classes.html", classes=classes, selected_class=selected_class,
        selected_class_id=selected_class_id, class_students=class_students,
        unassigned_students=unassigned_students, message=message, error=error,
    )

@app.route("/risk")
def risk_dashboard():
    error = None
    summary = None
    assessments = []
    selected_class_id = request.args.get("class_id", type=int)
    classes = []

    try:
        with closing(get_connection()) as conn:
            classes = [dict(row) for row in conn.execute(
                """SELECT class_id, class_name, program, semester, section
                   FROM faculty_classes ORDER BY class_name"""
            ).fetchall()]
        if selected_class_id and not any(item["class_id"] == selected_class_id for item in classes):
            selected_class_id = None
        summary = get_faculty_summary(class_id=selected_class_id)
        assessments = get_assessment_overview()
    except sqlite3.Error:
        error = (
            "Could not load student records. "
            "Check that the database is initialized."
        )

    return render_template(
        "risk.html",
        summary=summary,
        assessments=assessments,
        classes=classes,
        selected_class_id=selected_class_id,
        error=error,
    )


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
