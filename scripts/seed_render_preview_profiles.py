"""Seed non-production role profiles for the hosted Render review app."""
from contextlib import closing

from db import get_connection


def main():
    with closing(get_connection()) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL CHECK (role IN ('student', 'faculty', 'admin'))
            )"""
        )

        students = connection.execute(
            "SELECT student_id, name, email FROM students ORDER BY student_id LIMIT 2"
        ).fetchall()
        if len(students) < 2:
            raise RuntimeError("The preview academic seed must create at least two students.")

        connection.execute(
            "UPDATE students SET auth_user_id = ? WHERE student_id = ?",
            ("local-preview-student", students[0]["student_id"]),
        )
        connection.execute(
            "UPDATE students SET auth_user_id = ? WHERE student_id = ?",
            ("local-preview-faculty", students[1]["student_id"]),
        )

        connection.execute(
            """INSERT INTO teachers (auth_user_id, name, email)
               VALUES (?, ?, ?)
               ON CONFLICT(auth_user_id) DO NOTHING""",
            ("local-preview-faculty", "Demo Faculty", "faculty.preview@example.local"),
        )
        teacher = connection.execute(
            "SELECT teacher_id FROM teachers WHERE auth_user_id = ?",
            ("local-preview-faculty",),
        ).fetchone()
        class_row = connection.execute(
            "SELECT class_id FROM faculty_classes ORDER BY class_id LIMIT 1"
        ).fetchone()
        if class_row:
            connection.execute(
                "UPDATE faculty_classes SET owner_teacher_id = ? WHERE class_id = ?",
                (teacher["teacher_id"], class_row["class_id"]),
            )

        profiles = [
            ("local-preview-student", students[0]["email"], students[0]["name"], "student"),
            ("local-preview-faculty", "faculty.preview@example.local", "Demo Faculty", "faculty"),
            ("local-preview-admin", "admin.preview@example.local", "Demo Administrator", "admin"),
        ]
        for profile in profiles:
            connection.execute(
                """INSERT INTO user_profiles (user_id, email, display_name, role)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO NOTHING""",
                profile,
            )
        connection.commit()
        print("Seeded isolated Student, Faculty and Admin preview profiles.")


if __name__ == "__main__":
    main()
