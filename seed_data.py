
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# Use the same database file as database.py.
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "academic_companion.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

random.seed(42)

SUBJECTS = [
    ("Data Structures", "DSA"),
    ("C Programming", "C"),
    ("DBMS", "DBMS"),
    ("Python", "PY"),
    ("Mathematics", "MATH"),
    ("Statistics", "STAT"),
]

STUDENT_NAMES = [
    "Aarav Sharma", "Aditi Verma", "Aditya Singh", "Ananya Gupta",
    "Arjun Mehta", "Avni Joshi", "Dev Patel", "Diya Kapoor",
    "Ishaan Kumar", "Isha Malhotra", "Kabir Chauhan", "Kavya Nair",
    "Krishna Agarwal", "Meera Reddy", "Mohit Saxena", "Nandini Rao",
    "Neha Mishra", "Nikhil Bansal", "Parth Shah", "Pooja Yadav",
    "Pranav Das", "Priya Iyer", "Rahul Thakur", "Riya Sethi",
    "Rohan Kulkarni", "Sakshi Jain", "Sameer Khan", "Shreya Pandey",
    "Siddharth Bose", "Simran Kaur", "Tanvi Desai", "Varun Arora",
    "Vedant Joshi", "Yash Tiwari", "Zoya Ali", "Aniket Roy",
    "Bhavna Negi", "Harsh Vardhan", "Kirti Rawat", "Manish Pal",
]

TOPICS = {
    "DSA": [
        "Arrays and Pointers",
        "Linked Lists",
        "Stacks and Queues",
    ],
    "C": [
        "Functions and Pointers",
        "Structures and Unions",
        "File Handling",
    ],
    "DBMS": [
        "ER Model and Keys",
        "SQL Queries",
        "Normalization",
    ],
    "PY": [
        "Python Collections",
        "Functions and Modules",
        "File Handling and Exceptions",
    ],
    "MATH": [
        "Matrices and Determinants",
        "Differentiation",
        "Probability",
    ],
    "STAT": [
        "Descriptive Statistics",
        "Correlation and Regression",
        "Inferential Statistics",
    ],
}

ASSIGNMENT_TITLES = {
    "DSA": ["Array Practice", "Linked List Lab", "Stack Exercises",
            "Queue Implementation", "DSA Quiz"],
    "C": ["Pointer Worksheet", "Structure Program", "Function Lab",
          "File Handling Lab", "C Programming Quiz"],
    "DBMS": ["ER Diagram", "SQL Worksheet", "Join Queries",
             "Normalization Exercise", "DBMS Quiz"],
    "PY": ["List and Dictionary Lab", "Function Exercises",
           "File Processing", "Exception Handling Lab", "Python Quiz"],
    "MATH": ["Matrix Worksheet", "Calculus Problems",
             "Probability Worksheet", "Practice Set 4", "Math Quiz"],
    "STAT": ["Mean and Variance", "Correlation Worksheet",
             "Regression Problems", "Hypothesis Testing",
             "Statistics Quiz"],
}

ROOMS = ["R101", "R102", "R103", "R104",
         "LAB1", "LAB2", "LAB3", "LAB4"]

# Six one-hour slots from 09:00 to 15:00.
TIME_SLOTS = [
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("11:00", "12:00"),
    ("12:00", "13:00"),
    ("13:00", "14:00"),
    ("14:00", "15:00"),
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def add_column_if_missing(connection, table, column, definition):
    """Add a schema column only when it does not already exist."""
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if column not in existing:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def prepare_schema(connection):
    """Create base tables and add fields needed by this seed dataset."""
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    add_column_if_missing(connection, "students", "semester",
                          "INTEGER NOT NULL DEFAULT 3")
    add_column_if_missing(connection, "students", "section",
                          "TEXT NOT NULL DEFAULT 'A'")
    add_column_if_missing(connection, "students", "attendance_type",
                          "TEXT NOT NULL DEFAULT 'regular'")
    add_column_if_missing(connection, "marks", "topic_name", "TEXT")
    add_column_if_missing(connection, "timetable", "section",
                          "TEXT NOT NULL DEFAULT 'A'")

    connection.commit()


def clear_old_data(connection):
    """Delete existing records in foreign-key-safe order."""
    for table in [
        "assignments",
        "marks",
        "attendance",
        "timetable",
        "exams",
        "subjects",
        "students",
    ]:
        connection.execute(f"DELETE FROM {table}")

    # Reset generated IDs so each run starts from the same IDs.
    connection.execute("DELETE FROM sqlite_sequence")
    connection.commit()


def make_students(connection):
    """Insert 40 students: 24 regular, 10 borderline, 6 poor."""
    students = []
    types = (
        ["regular"] * 24
        + ["borderline"] * 10
        + ["poor"] * 6
    )
    random.shuffle(types)

    for index, name in enumerate(STUDENT_NAMES):
        section = "A" if index < 20 else "B"
        email_name = name.lower().replace(" ", ".")
        students.append((
            name,
            f"{email_name}@example.edu",
            3,
            section,
            types[index],
        ))

    connection.executemany(
        """
        INSERT INTO students
            (name, email, semester, section, attendance_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        students,
    )

    return {
        row["student_id"]: row
        for row in connection.execute(
            "SELECT student_id, name, semester, section, attendance_type "
            "FROM students ORDER BY student_id"
        )
    }


def make_subjects(connection):
    """Insert the six project subjects."""
    connection.executemany(
        "INSERT INTO subjects (subject_name, subject_code) VALUES (?, ?)",
        SUBJECTS,
    )

    return {
        row["subject_code"]: row["subject_id"]
        for row in connection.execute(
            "SELECT subject_id, subject_code FROM subjects"
        )
    }


def attendance_count(attendance_type):
    """Return attended classes out of 36 for the selected type."""
    if attendance_type == "regular":
        return random.randint(31, 34)  # 86.1% to 94.4%
    if attendance_type == "borderline":
        return random.randint(26, 28)  # 72.2% to 77.8%
    return random.randint(18, 23)      # 50.0% to 63.9%


def make_attendance(connection, students, subject_ids):
    """Insert 12 weeks of attendance for each student and subject."""
    rows = []

    for student_id, student in students.items():
        for subject_id in subject_ids.values():
            total = 36  # Three classes per week for twelve weeks.
            attended = attendance_count(student["attendance_type"])
            rows.append((student_id, subject_id, total, attended))

    connection.executemany(
        """
        INSERT INTO attendance
            (student_id, subject_id, total_classes, attended_classes)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def make_marks(connection, students, subject_ids):
    """Insert three topic-based internal tests per subject per student."""
    rows = []

    for student_id, student in students.items():
        attendance_type = student["attendance_type"]

        # Attendance influences marks, but random noise keeps the
        # relationship realistic rather than perfectly predictable.
        base_score = {
            "regular": 76,
            "borderline": 62,
            "poor": 46,
        }[attendance_type]

        for code, subject_id in subject_ids.items():
            for test_number, topic in enumerate(TOPICS[code], start=1):
                score = max(
                    5,
                    min(100, base_score + random.randint(-20, 18)),
                )
                rows.append((
                    student_id,
                    subject_id,
                    f"Internal Test {test_number}",
                    float(score),
                    100.0,
                    (date.today() - timedelta(days=14 * (4 - test_number)))
                    .isoformat(),
                    topic,
                ))

    connection.executemany(
        """
        INSERT INTO marks
            (student_id, subject_id, exam_name, marks_obtained,
             max_marks, exam_date, topic_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def make_assignments(connection, students, subject_ids):
    """Insert five assignments per student per subject."""
    rows = []

    for student_id, student in students.items():
        attendance_type = student["attendance_type"]

        # Weaker attendance types tend to submit fewer assignments.
        submission_probability = {
            "regular": 0.90,
            "borderline": 0.65,
            "poor": 0.35,
        }[attendance_type]

        for code, subject_id in subject_ids.items():
            for number, title in enumerate(ASSIGNMENT_TITLES[code], start=1):
                submitted = int(random.random() < submission_probability)
                due_date = (date.today() - timedelta(days=number * 3)).isoformat()

                rows.append((
                    student_id,
                    subject_id,
                    title,
                    due_date,
                    submitted,
                ))

    connection.executemany(
        """
        INSERT INTO assignments
            (student_id, subject_id, title, due_date, submitted)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def make_exams(connection, subject_ids):
    """Schedule one exam per subject 21 to 28 days from today."""
    today = date.today()
    rows = []

    for code, subject_id in subject_ids.items():
        exam_day = today + timedelta(days=random.randint(21, 28))
        start_hour = random.choice([9, 11, 13])
        end_hour = start_hour + 2

        rows.append((
            subject_id,
            f"{code} End-Semester Exam",
            exam_day.isoformat(),
            f"{start_hour:02d}:00",
            f"{end_hour:02d}:00",
        ))

    connection.executemany(
        """
        INSERT INTO exams
            (subject_id, exam_name, exam_date, start_time, end_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def make_timetable(connection, subject_ids):
    """
    Create a clash-free weekly timetable.

    Every section gets one class in each of six daily slots.
    A room is used at most once per slot across both sections.
    """
    rows = []
    codes = list(subject_ids.keys())

    for day_number in range(1, 6):
        for slot_number, (start_time, end_time) in enumerate(TIME_SLOTS):
            # Different rooms guarantee no simultaneous room bookings.
            rooms_for_slot = random.sample(ROOMS, 2)

            for section_index, section in enumerate(["A", "B"]):
                code_index = (
                    day_number + slot_number + section_index
                ) % len(codes)
                code = codes[code_index]
                room = rooms_for_slot[section_index]

                rows.append((
                    subject_ids[code],
                    room,
                    day_number,
                    start_time,
                    end_time,
                    section,
                ))

    connection.executemany(
        """
        INSERT INTO timetable
            (subject_id, room_number, day_of_week,
             start_time, end_time, section)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def print_summary(connection):
    """Print counts and attendance-type distribution."""
    print("\n=== Smart Academic Companion: Seed Summary ===")

    for table in [
        "students",
        "subjects",
        "attendance",
        "marks",
        "assignments",
        "exams",
        "timetable",
    ]:
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        print(f"{table:12s}: {count}")

    print("\nAttendance types:")
    for row in connection.execute(
        """
        SELECT attendance_type, COUNT(*) AS total
        FROM students
        GROUP BY attendance_type
        ORDER BY CASE attendance_type
            WHEN 'regular' THEN 1
            WHEN 'borderline' THEN 2
            ELSE 3
        END
        """
    ):
        print(f"{row['attendance_type']:12s}: {row['total']}")


def main():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        prepare_schema(connection)
        clear_old_data(connection)

        students = make_students(connection)
        subject_ids = make_subjects(connection)

        make_attendance(connection, students, subject_ids)
        make_marks(connection, students, subject_ids)
        make_assignments(connection, students, subject_ids)
        make_exams(connection, subject_ids)
        make_timetable(connection, subject_ids)

        connection.commit()
        print_summary(connection)
        print(f"\nDatabase: {DB_PATH}")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
