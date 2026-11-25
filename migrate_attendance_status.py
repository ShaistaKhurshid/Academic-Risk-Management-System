
"""Safely migrate attendance statuses in the SQLite database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "instance" / "academic_risk.db"


def migrate():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    connection = sqlite3.connect(DB_PATH)

    try:
        # Check that no other table references attendance.
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        for table in tables:
            table_name = table[0]
            references = connection.execute(
                f"PRAGMA foreign_key_list('{table_name}')"
            ).fetchall()

            if any(reference[2] == "attendance" for reference in references):
                raise RuntimeError(
                    f"Cannot migrate: {table_name} references attendance."
                )

        # Disable foreign keys before beginning the table rebuild.
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN")

        # Create replacement table with the new allowed statuses.
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
                    CHECK (
                        status IN (
                            'Present',
                            'Absent',
                            'Present (Late)'
                        )
                    ),

                FOREIGN KEY(student_id)
                    REFERENCES students (id) ON DELETE CASCADE,

                FOREIGN KEY(course_id)
                    REFERENCES courses (id) ON DELETE CASCADE
            )
        """)

        # Copy records while converting old statuses.
        connection.execute("""
            INSERT INTO attendance_new (
                id,
                student_id,
                course_id,
                session_date,
                status
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

        # Replace the old table.
        connection.execute("DROP TABLE attendance")
        connection.execute(
            "ALTER TABLE attendance_new RENAME TO attendance"
        )

        # Confirm the migrated table contains valid relationships.
        violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if violations:
            raise RuntimeError(
                f"Foreign key violations detected: {violations}"
            )

        connection.commit()

        print("\nAttendance migration completed successfully!")

        print("\nUpdated attendance records:")
        records = connection.execute("""
            SELECT id, student_id, course_id, session_date, status
            FROM attendance
            ORDER BY id
        """).fetchall()

        for record in records:
            print(record)

        print("\nNew attendance constraint:")
        schema = connection.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE type='table' AND name='attendance'
        """).fetchone()

        print(schema[0])

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
