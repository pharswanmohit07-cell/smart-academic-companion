import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "academic_companion.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
random.seed(42)

SUBJECTS = [
    ("Data Structures", "DSA"), ("C Programming", "C"),
    ("DBMS", "DBMS"), ("Python", "PY"),
    ("Mathematics", "MATH"), ("Statistics", "STAT"),
]
NAMES = [
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
    "DSA": ["Arrays and Pointers", "Linked Lists", "Stacks and Queues"],
    "C": ["Functions and Pointers", "Structures and Unions", "File Handling"],
    "DBMS": ["ER Model and Keys", "SQL Queries", "Normalization"],
    "PY": ["Python Collections", "Functions and Modules", "Exceptions"],
    "MATH": ["Matrices and Determinants", "Differentiation", "Probability"],
    "STAT": ["Descriptive Statistics", "Correlation and Regression",
             "Inferential Statistics"],
}
ASSIGNMENTS = {
    "DSA": ["Array Practice", "Linked List Lab", "Stack Exercises",
            "Queue Implementation", "DSA Quiz"],
    "C": ["Pointer Worksheet", "Structure Program", "Function Lab",
          "File Handling Lab", "C Quiz"],
    "DBMS": ["ER Diagram", "SQL Worksheet", "Join Queries",
             "Normalization Exercise", "DBMS Quiz"],
    "PY": ["Collections Lab", "Function Exercises", "File Processing",
           "Exception Handling", "Python Quiz"],
    "MATH": ["Matrix Worksheet", "Calculus Problems", "Probability",
             "Practice Set 4", "Math Quiz"],
    "STAT": ["Mean and Variance", "Correlation Worksheet",
             "Regression Problems", "Hypothesis Testing", "Statistics Quiz"],
}
ROOMS = ["R101", "R102", "R103", "R104", "LAB1", "LAB2", "LAB3", "LAB4"]
SLOTS = [(f"{h:02d}:00", f"{h+1:02d}:00") for h in range(9, 15)]


def add_column_if_missing(conn, table, column, definition):
    columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def prepare_schema(conn):
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    add_column_if_missing(conn, "students", "semester", "INTEGER NOT NULL DEFAULT 3")
    add_column_if_missing(conn, "students", "section", "TEXT NOT NULL DEFAULT 'A'")
    add_column_if_missing(conn, "students", "attendance_type",
                          "TEXT NOT NULL DEFAULT 'regular'")
    add_column_if_missing(conn, "marks", "topic_name", "TEXT")
    add_column_if_missing(conn, "timetable", "section", "TEXT NOT NULL DEFAULT 'A'")


def clear_old_data(conn):
    for table in ("assignments", "marks", "attendance", "timetable",
                  "exams", "subjects", "students"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.commit()


def seed(conn):
    prepare_schema(conn)
    clear_old_data(conn)

    kinds = ["regular"] * 24 + ["borderline"] * 10 + ["poor"] * 6
    random.shuffle(kinds)
    conn.executemany(
        """INSERT INTO students(name,email,semester,section,attendance_type)
           VALUES(?,?,?,?,?)""",
        [(name, f"student{i+1:02d}@example.edu", 3,
          "A" if i < 20 else "B", kinds[i]) for i, name in enumerate(NAMES)],
    )
    conn.executemany("INSERT INTO subjects(subject_name,subject_code) VALUES(?,?)",
                     SUBJECTS)
    students = list(conn.execute(
        "SELECT student_id, attendance_type FROM students ORDER BY student_id"))
    subjects = {r["subject_code"]: r["subject_id"] for r in conn.execute(
        "SELECT subject_code, subject_id FROM subjects")}

    attendance_rows, marks_rows, assignment_rows = [], [], []
    score_base = {"regular": 76, "borderline": 62, "poor": 46}
    attendance_range = {"regular": (31, 34), "borderline": (26, 28), "poor": (18, 23)}
    submit_prob = {"regular": .90, "borderline": .65, "poor": .35}
    today = date.today()

    for student in students:
        sid, kind = student["student_id"], student["attendance_type"]
        for code, subject_id in subjects.items():
            attended = random.randint(*attendance_range[kind])
            attendance_rows.append((sid, subject_id, 36, attended))
            for test_no, topic in enumerate(TOPICS[code], 1):
                score = max(5, min(100, score_base[kind] + random.randint(-20, 18)))
                exam_day = (today - timedelta(days=14 * (4 - test_no))).isoformat()
                marks_rows.append((sid, subject_id, f"Internal Test {test_no}",
                                   float(score), 100.0, exam_day, topic))
            for title in ASSIGNMENTS[code]:
                due = (today - timedelta(days=random.randint(1, 30))).isoformat()
                assignment_rows.append((sid, subject_id, title, due,
                                        int(random.random() < submit_prob[kind])))

    conn.executemany(
        """INSERT INTO attendance(student_id,subject_id,total_classes,attended_classes)
           VALUES(?,?,?,?)""", attendance_rows)
    conn.executemany(
        """INSERT INTO marks(student_id,subject_id,exam_name,marks_obtained,
           max_marks,exam_date,topic_name) VALUES(?,?,?,?,?,?,?)""", marks_rows)
    conn.executemany(
        """INSERT INTO assignments(student_id,subject_id,title,due_date,submitted)
           VALUES(?,?,?,?,?)""", assignment_rows)

    # One exam per subject, 21-28 days from today.
    exam_rows = []
    for code, subject_id in subjects.items():
        day = today + timedelta(days=random.randint(21, 28))
        start = random.choice([9, 11, 13])
        exam_rows.append((subject_id, f"{code} End-Semester Exam", day.isoformat(),
                          f"{start:02d}:00", f"{start+2:02d}:00"))
    conn.executemany(
        """INSERT INTO exams(subject_id,exam_name,exam_date,start_time,end_time)
           VALUES(?,?,?,?,?)""", exam_rows)

    # 5 weekdays x 6 slots x 2 sections = 60 bookings. Each simultaneous
    # section receives a different room; no room or section has overlapping slots.
    timetable_rows = []
    codes = list(subjects)
    for day in range(1, 6):
        for slot_idx, (start, end) in enumerate(SLOTS):
            room_pair = random.sample(ROOMS, 2)
            for section_idx, section in enumerate(("A", "B")):
                code = codes[(day + slot_idx + section_idx) % len(codes)]
                timetable_rows.append((subjects[code], room_pair[section_idx],
                                       day, start, end, section))
    conn.executemany(
        """INSERT INTO timetable(subject_id,room_number,day_of_week,start_time,
           end_time,section) VALUES(?,?,?,?,?,?)""", timetable_rows)


def print_summary(conn):
    print("\n=== Smart Academic Companion seed summary ===")
    for table in ("students", "subjects", "attendance", "marks",
                  "assignments", "exams", "timetable"):
        print(f"{table:12s}: {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    print("\nAttendance types:")
    for row in conn.execute(
        """SELECT attendance_type, COUNT(*) FROM students
           GROUP BY attendance_type
           ORDER BY CASE attendance_type WHEN 'regular' THEN 1
             WHEN 'borderline' THEN 2 ELSE 3 END"""):
        print(f"{row[0]:12s}: {row[1]}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        seed(conn)
        conn.commit()
        print_summary(conn)
        print(f"\nDatabase: {DB_PATH}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
