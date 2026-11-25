
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "instance" / "academic_risk.db"


def migrate():
    connection = sqlite3.connect(DB_PATH)

    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(assignments)"
            ).fetchall()
        }

        if "original_deadline" in columns:
            print("Migration already applied. No changes needed.")
            return

        connection.execute("BEGIN")

        connection.execute(
            "ALTER TABLE assignments ADD COLUMN original_deadline DATE"
        )

        connection.execute(
            """
            UPDATE assignments
            SET original_deadline = deadline
            WHERE original_deadline IS NULL
            """
        )

        connection.commit()

        print("Migration completed successfully.")

        print(
            "Assignment columns:",
            [
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(assignments)"
                ).fetchall()
            ],
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
