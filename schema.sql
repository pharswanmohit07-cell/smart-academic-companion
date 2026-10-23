PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    semester INTEGER NOT NULL DEFAULT 3,
    section TEXT NOT NULL DEFAULT 'A',
    attendance_type TEXT NOT NULL DEFAULT 'regular'
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
    total_classes INTEGER NOT NULL DEFAULT 0 CHECK (total_classes >= 0),
    attended_classes INTEGER NOT NULL DEFAULT 0 CHECK (attended_classes >= 0),
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
    topic_name TEXT,
    CHECK (marks_obtained <= max_marks),
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

CREATE TABLE IF NOT EXISTS timetable (
    timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    room_number TEXT NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT 'A',
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    CHECK (start_time < end_time)
);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT,
    submitted INTEGER NOT NULL DEFAULT 0 CHECK (submitted IN (0, 1)),
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

CREATE TABLE IF NOT EXISTS assessment_items (
    assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    assessment_type TEXT NOT NULL CHECK (assessment_type IN ('assignment', 'term_work')),
    title TEXT NOT NULL,
    due_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    UNIQUE (subject_id, assessment_type, title)
);

CREATE TABLE IF NOT EXISTS assessment_submissions (
    assessment_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    submitted INTEGER NOT NULL DEFAULT 0 CHECK (submitted IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (assessment_id, student_id),
    FOREIGN KEY (assessment_id) REFERENCES assessment_items(assessment_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_marks_student_subject ON marks(student_id, subject_id);
CREATE INDEX IF NOT EXISTS idx_timetable_day ON timetable(day_of_week);
CREATE INDEX IF NOT EXISTS idx_assessment_submissions_student ON assessment_submissions(student_id);
