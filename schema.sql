
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subjects (
    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL,
    subject_code TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    total_classes INTEGER NOT NULL DEFAULT 0
        CHECK (total_classes >= 0),
    attended_classes INTEGER NOT NULL DEFAULT 0
        CHECK (attended_classes >= 0),
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    UNIQUE (student_id, subject_id),
    CHECK (attended_classes <= total_classes)
);

CREATE TABLE IF NOT EXISTS marks (
    mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    exam_name TEXT NOT NULL,
    marks_obtained REAL NOT NULL CHECK (marks_obtained >= 0),
    max_marks REAL NOT NULL CHECK (max_marks > 0),
    exam_date TEXT,
    CHECK (marks_obtained <= max_marks),
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

CREATE TABLE IF NOT EXISTS timetable (
    timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    room_number TEXT NOT NULL,
    day_of_week INTEGER NOT NULL
        CHECK (day_of_week BETWEEN 1 AND 7),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    CHECK (start_time < end_time)
);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT,
    submitted INTEGER NOT NULL DEFAULT 0
        CHECK (submitted IN (0, 1)),
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

CREATE TABLE IF NOT EXISTS exams (
    exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    exam_name TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

CREATE INDEX IF NOT EXISTS idx_attendance_student
    ON attendance(student_id);

CREATE INDEX IF NOT EXISTS idx_marks_student_subject
    ON marks(student_id, subject_id);

CREATE INDEX IF NOT EXISTS idx_timetable_day
    ON timetable(day_of_week);
