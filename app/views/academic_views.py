"""
Shared academic tools: attendance calculator, classroom finder, study planner.

These are the project's original routes, moved from ``app.py`` into a
blueprint so every page can sit behind ``@login_required``. The algorithms,
validation rules and templates are unchanged; only three things differ:

* login is required (see ``app/auth.py``),
* classroom bookings are read through the portable database layer,
* ``building`` is taken from the timetable row when the schema has it.
"""

import logging
from contextlib import contextmanager

from flask import Blueprint, current_app, render_template, request

from app import auth as auth_module
from attendance_calculator import classes_missable, classes_needed
from db import DatabaseError, get_connection
from db.base import to_minutes

log = logging.getLogger(__name__)

bp = Blueprint("academic", __name__)

DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday",
             4: "Thursday", 5: "Friday"}


def _to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def find_rooms(day, start, end):
    """Check every room for one day and time window using the C library."""
    classroom = current_app.extensions["sac"]["classroom"]

    with closing_connection() as connection:
        has_building = "building" in connection.table_columns("timetable")
        building_column = "building" if has_building else "'Main' AS building"
        rows = connection.execute(
            f"SELECT timetable_id, room_number, {building_column}, day_of_week, "
            "start_time, end_time FROM timetable"
        ).fetchall()

        locations = {
            row["room_number"]: dict(row)
            for row in connection.execute(
                "SELECT room_number, building, floor, room_type FROM room_locations"
            ).fetchall()
        }

    # Plain dicts: the ctypes wrapper calls row.get(), which Row supports too,
    # but the wrapper also fills defaults for bookings without a building.
    bookings = [
        {
            "booking_id": row["timetable_id"],
            "building": row["building"] or "Main",
            "room": row["room_number"],
            "section": "A",   # section does not affect room availability
            "day_of_week": row["day_of_week"],
            "start_minute": to_minutes(row["start_time"]),
            "end_minute": to_minutes(row["end_time"]),
        }
        for row in rows
    ]

    results = []
    for room in sorted({booking["room"] for booking in bookings}):
        if not classroom.is_room_free(bookings, room, day, start, end):
            continue
        location = locations.get(room, {})
        results.append({
            "room": room,
            "building": location.get("building") or "Main",
            "floor": location.get("floor") or "Not set",
            "room_type": location.get("room_type") or (
                "Laboratory" if room.upper().startswith("LAB") else "Classroom"),
        })

    clashes = classroom.detect_clashes(bookings, day)
    summary = {
        "free_count": len(results),
        "room_count": len({booking["room"] for booking in bookings}),
        "clash_count": len(clashes),
    }
    return results, summary


@contextmanager
def closing_connection():
    """Open a database connection and always close it."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@bp.route("/attendance", methods=["GET", "POST"])
@auth_module.login_required
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


@bp.route("/classrooms", methods=["GET", "POST"])
@auth_module.login_required
def classrooms():
    classroom = current_app.extensions["sac"]["classroom"]
    form = {"day": "1", "start": "10:00", "end": "11:00"}
    results = None
    summary = None
    error = current_app.extensions["sac"]["classroom_error"]

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
                except DatabaseError as exc:
                    log.warning("classroom lookup failed: %s", exc)
                    error = (
                        "Timetable data is not available right now. "
                        "An administrator needs to apply the database migrations."
                    )
                else:
                    if not results:
                        error = (
                            "No free rooms were found for that time. "
                            "Check the timetable data."
                        )

    return render_template(
        "classrooms.html",
        form=form, days=DAY_NAMES, results=results,
        summary=summary, error=error,
    )


@bp.route("/study-planner", methods=["GET", "POST"])
@auth_module.login_required
def study_planner_page():
    """Build a study plan from topic mastery using the C heap algorithms."""
    study_planner = current_app.extensions["sac"]["study_planner"]
    error = current_app.extensions["sac"]["study_planner_error"]
    plan = None
    available_minutes = "120"
    # Default rows so the page is usable straight away.
    rows = [
        {"name": "Recursion", "mastery_pct": "40", "estimated_minutes": "45"},
        {"name": "Normalisation", "mastery_pct": "60", "estimated_minutes": "30"},
        {"name": "Graph Algorithms", "mastery_pct": "25", "estimated_minutes": "60"},
    ]

    if study_planner is not None and request.method == "POST":
        available_minutes = request.form.get("available_minutes", "").strip()
        names = request.form.getlist("topic_name")
        masteries = request.form.getlist("mastery_pct")
        minutes = request.form.getlist("estimated_minutes")
        rows = [
            {"name": names[i].strip(), "mastery_pct": masteries[i].strip(),
             "estimated_minutes": minutes[i].strip()}
            for i in range(min(len(names), len(masteries), len(minutes)))
        ]

        topics = []
        for index, row in enumerate(rows, start=1):
            # Skip rows the user has not filled in at all.
            if not (row["name"] or row["mastery_pct"] or row["estimated_minutes"]):
                continue
            try:
                topics.append({
                    "name": row["name"],
                    "mastery_pct": float(row["mastery_pct"]),
                    "estimated_minutes": int(row["estimated_minutes"]),
                })
            except ValueError:
                error = (
                    f"Row {index}: enter a mastery percentage and estimated "
                    "minutes as numbers."
                )
                break

        if error is None and not topics:
            error = "Add at least one topic before generating a plan."

        if error is None:
            try:
                plan = study_planner.build_plan(topics, available_minutes)
            except ValueError as exc:
                error = str(exc)

    return render_template(
        "study_planner.html",
        plan=plan,
        rows=rows,
        available_minutes=available_minutes,
        error=error,
        max_topics=study_planner.MAX_TOPICS if study_planner else 10,
    )
