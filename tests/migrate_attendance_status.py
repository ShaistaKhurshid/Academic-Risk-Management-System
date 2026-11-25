
"""Safely update attendance statuses and SQLite CHECK constraint."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "instance" / "academic_risk.db"


def migrate():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN")

        # Create the new attendance table with the updated constraint.
        connection.execute("""
            CREATE TABLE attendance_new (
                id INTEGER NOT NULL PRIMARY KEY,
                student_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                session_date DATE NOT NULL,
                status VARCHAR(20) NOT NULL,

                CONSTRAINT uq_attendance_student_course_date
                    UNIQUE (student_id, course_id, session_date),

                CONSTRAINT ck_attendance_status
                    CHECK (status IN (
                        'Present',
                        'Absent',
                        'Present (Late)'
                    )),

                FOREIGN KEY(student_id)
                    REFERENCES students (id) ON DELETE CASCADE,

                FOREIGN KEY(course_id)
                    REFERENCES courses (id) ON DELETE CASCADE
            )
        """)

        # Copy existing records and convert the old statuses.
        connection.execute("""
            INSERT INTO attendance_new (
                id, student_id, course_id, session_date, status
            )
            SELECT
                id,
                student_id,
                course_id,
                session_date,
                CASE
                    WHEN status = 'Late' THEN 'Present (Late)'
                    WHEN status = 'Excused' THEN 'Absent'
                    ELSE status
                END
            FROM attendance
        """)

        connection.execute("DROP TABLE attendance")
        connection.execute(
            "ALTER TABLE attendance_new RENAME TO attendance"
        )

        connection.commit()

        print("Attendance migration completed successfully.")
        print("Updated attendance records:")

        rows = connection.execute("""
            SELECT id, student_id, course_id, session_date, status
            FROM attendance
            ORDER BY id
        """).fetchall()

        for row in rows:
            print(row)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.close()


if __name__ == "__main__":
    migrate()

