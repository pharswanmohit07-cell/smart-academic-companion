"""Add demo Midterm/End Term marks, assessments and room locations.

Run this AFTER seed_data.py (or after adding students yourself) so the
faculty dashboard has something to show.

This script only ADDS missing rows. It never deletes or overwrites data,
so it is safe to run more than once and it will not touch marks, statuses
or room locations that were entered by hand.

Usage:  python demo_data.py
"""

import random
from contextlib import closing

from database import get_connection, initialize_database

# A fixed seed makes the generated marks identical on every machine.
rng = random.Random(7)

EXAMS = [("Midterm", 50), ("End Term", 100)]

# Typical score (percent) for each kind of student, as in seed_data.py.
BASE_PERCENT = {"regular": 76, "borderline": 62, "poor": 46}

# Chance that a student has submitted an assessment.
SUBMIT_CHANCE = {"regular": 0.90, "borderline": 0.65, "poor": 0.35}

# (subject name, type, title). Subjects that do not exist are skipped.
ASSESSMENTS = [
    ("Data Structures", "assignment", "Linked List Assignment"),
    ("C Programming", "term_work", "Pointers Term Work"),
    ("DBMS", "assignment", "SQL Worksheet"),
    ("Python", "term_work", "Python Mini Lab"),
]


def add_marks(conn, students, subjects):
    """Insert Midterm and End Term marks only where none exist yet."""
    added = 0
    for student in students:
        base = BASE_PERCENT.get(student["attendance_type"], 62)
        for subject in subjects:
            for exam_name, maximum in EXAMS:
                exists = conn.execute(
                    "SELECT 1 FROM marks WHERE student_id = ? AND subject_id = ? "
                    "AND exam_name = ?",
                    (student["student_id"], subject["subject_id"], exam_name),
                ).fetchone()
                if exists:
                    continue
                percent = max(5, min(100, base + rng.randint(-20, 18)))
                obtained = round(maximum * percent / 100)
                conn.execute(
                    "INSERT INTO marks (student_id, subject_id, exam_name, "
                    "marks_obtained, max_marks, exam_date) "
                    "VALUES (?, ?, ?, ?, ?, date('now'))",
                    (student["student_id"], subject["subject_id"],
                     exam_name, obtained, maximum),
                )
                added += 1
    return added


def add_assessments(conn, students):
    """Create a few assessments and a submission row for every student."""
    items_added = 0
    submissions_added = 0

    for subject_name, kind, title in ASSESSMENTS:
        subject = conn.execute(
            "SELECT subject_id FROM subjects WHERE subject_name = ?",
            (subject_name,),
        ).fetchone()
        if subject is None:
            continue

        cursor = conn.execute(
            "INSERT OR IGNORE INTO assessment_items "
            "(subject_id, assessment_type, title, due_date) "
            "VALUES (?, ?, ?, date('now', '+7 days'))",
            (subject["subject_id"], kind, title),
        )
        items_added += cursor.rowcount

        item = conn.execute(
            "SELECT assessment_id FROM assessment_items "
            "WHERE subject_id = ? AND assessment_type = ? AND title = ?",
            (subject["subject_id"], kind, title),
        ).fetchone()

        for student in students:
            chance = SUBMIT_CHANCE.get(student["attendance_type"], 0.65)
            submitted = 1 if rng.random() < chance else 0
            # INSERT OR IGNORE keeps any status a teacher already saved.
            cursor = conn.execute(
                "INSERT OR IGNORE INTO assessment_submissions "
                "(assessment_id, student_id, submitted) VALUES (?, ?, ?)",
                (item["assessment_id"], student["student_id"], submitted),
            )
            submissions_added += cursor.rowcount

    return items_added, submissions_added


def add_room_locations(conn):
    """Fill in building and floor for timetable rooms that have none."""
    rooms = conn.execute(
        "SELECT DISTINCT room_number FROM timetable ORDER BY room_number"
    ).fetchall()
    added = 0
    for row in rooms:
        room = row["room_number"]
        if room.upper().startswith("LAB"):
            location = ("Lab Block", "Ground floor", "Laboratory")
        else:
            location = ("Main Building", "First floor", "Classroom")
        cursor = conn.execute(
            "INSERT OR IGNORE INTO room_locations "
            "(room_number, building, floor, room_type) VALUES (?, ?, ?, ?)",
            (room, *location),
        )
        added += cursor.rowcount
    return added


def main():
    initialize_database()  # creates missing tables; never deletes data

    with closing(get_connection()) as conn:
        students = conn.execute(
            "SELECT student_id, attendance_type FROM students ORDER BY student_id"
        ).fetchall()
        subjects = conn.execute(
            "SELECT subject_id, subject_name FROM subjects ORDER BY subject_id"
        ).fetchall()

        if not students or not subjects:
            print("No students or subjects found, so nothing was added.")
            print("Add some through /faculty/manage, or run seed_data.py on a")
            print("disposable demo database (it deletes existing records).")
            return

        try:
            marks = add_marks(conn, students, subjects)
            items, submissions = add_assessments(conn, students)
            rooms = add_room_locations(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    print("Demo data added (existing records were left untouched):")
    print(f"  Midterm/End Term marks : {marks}")
    print(f"  Assessment items       : {items}")
    print(f"  Submission rows        : {submissions}")
    print(f"  Room locations         : {rooms}")
    if marks == items == submissions == rooms == 0:
        print("Nothing new to add: the demo data is already in place.")


if __name__ == "__main__":
    main()
