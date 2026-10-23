
import sqlite3
from contextlib import closing

from flask import Flask, render_template, request

from attendance_calculator import classes_needed, classes_missable
from database import get_connection, initialize_database
from modules.faculty_dashboard import get_faculty_summary

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

    results = []
    for room in sorted({b["room"] for b in bookings}):
        slots = classroom.find_free_slots(
            bookings, room, day, DAY_START, DAY_END
        )
        results.append({
            "room": room,
            "free": classroom.is_room_free(bookings, room, day, start, end),
            "slots": [
                (to_hhmm(s["start_minute"]), to_hhmm(s["end_minute"]))
                for s in slots
            ],
        })

    clashes = classroom.detect_clashes(bookings, day)
    summary = {
        "free_count": sum(1 for r in results if r["free"]),
        "room_count": len(results),
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
                    error = "Database not ready. Run: python seed_data.py"
                else:
                    if not results:
                        error = "No timetable found. Run: python seed_data.py"

    return render_template(
        "classrooms.html",
        form=form, days=DAY_NAMES, results=results,
        summary=summary, error=error,
    )

@app.route("/risk")
def risk_dashboard():
    error = None
    summary = None

    try:
        summary = get_faculty_summary()
    except sqlite3.Error:
        error = (
            "Could not load student records. "
            "Check that the database is initialized."
        )

    return render_template(
        "risk.html",
        summary=summary,
        error=error,
    )


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
