"""Safely add the risk_snapshots table (Phase 12: historical risk tracking).

HOW TO RUN (Windows, from the project folder, with the server STOPPED):

    python migrate_risk_snapshots.py

Other options:

    python migrate_risk_snapshots.py --db path\\to\\other.db   use another database file
    python migrate_risk_snapshots.py --no-backup               skip the backup (not advised)

WHAT IT DOES
  1. Checks that the database exists and already has the users, students and
     courses tables.
  2. Makes a consistent backup copy next to the database, named
     <database>.backup_before_risk_snapshots_<date>_<time>.db
  3. In ONE transaction, creates ONLY what is missing: the risk_snapshots table,
     its two indexes, and two triggers that make snapshots read-only.
  4. Before committing, checks that every existing table still has exactly the
     same number of rows. If anything differs it rolls back and changes nothing.
  5. Runs SQLite's own integrity and foreign-key checks.

WHAT IT NEVER DOES
  * It never drops, recreates, empties or alters an existing table.
  * It never touches student, teacher, course, attendance, assessment,
    assignment or follow-up data.

It is safe to run more than once: when everything already exists it reports
"already applied", changes nothing and makes no backup.

(`python init_db.py` also creates the new table on a fresh database, because
create_all() only creates tables that are missing. This script is the recommended
way for an existing database because it adds the backup and the safety checks.)

This file uses only the Python standard library on purpose, so it works even if
the rest of the application cannot start.
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "instance" / "academic_risk.db"

REQUIRED_EXISTING_TABLES = ("users", "students", "courses")

TABLE_NAME = "risk_snapshots"

# Must match app/models.py (RiskSnapshot). tests/test_risk_snapshot_migration_models.py
# compares the two so they cannot drift apart unnoticed.
CREATE_TABLE_SQL = """
CREATE TABLE risk_snapshots (
    id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    recorded_by_id INTEGER NOT NULL,
    recorded_at DATETIME NOT NULL,
    overall_risk_score FLOAT,
    classification VARCHAR(20) NOT NULL,
    attendance_percentage FLOAT,
    attendance_risk_score FLOAT,
    attendance_weight FLOAT,
    performance_percentage FLOAT,
    performance_risk_score FLOAT,
    performance_weight FLOAT,
    assignment_percentage FLOAT,
    assignment_risk_score FLOAT,
    assignment_weight FLOAT,
    explanations_json TEXT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_risk_snapshot_classification
        CHECK (classification IN ('Low Risk', 'Medium Risk', 'High Risk', 'Pending')),
    CONSTRAINT ck_risk_snapshot_score_not_negative
        CHECK (overall_risk_score IS NULL OR overall_risk_score >= 0),
    CONSTRAINT ck_risk_snapshot_pending_has_no_score
        CHECK ((classification = 'Pending') = (overall_risk_score IS NULL)),
    FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE RESTRICT,
    FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE RESTRICT,
    FOREIGN KEY(recorded_by_id) REFERENCES users (id) ON DELETE RESTRICT
)
"""

INDEX_SQL = {
    "ix_risk_snapshots_student_course_time": (
        "CREATE INDEX IF NOT EXISTS ix_risk_snapshots_student_course_time "
        "ON risk_snapshots (student_id, course_id, recorded_at)"
    ),
    "ix_risk_snapshots_course": (
        "CREATE INDEX IF NOT EXISTS ix_risk_snapshots_course "
        "ON risk_snapshots (course_id)"
    ),
}

# Must match RISK_SNAPSHOT_TRIGGER_SQL in app/models.py.
TRIGGER_SQL = {
    "trg_risk_snapshots_no_update": (
        "CREATE TRIGGER IF NOT EXISTS trg_risk_snapshots_no_update "
        "BEFORE UPDATE ON risk_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'risk_snapshots rows are immutable'); END"
    ),
    "trg_risk_snapshots_no_delete": (
        "CREATE TRIGGER IF NOT EXISTS trg_risk_snapshots_no_delete "
        "BEFORE DELETE ON risk_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'risk_snapshots rows are immutable'); END"
    ),
}

EXPECTED_COLUMNS = (
    "id", "student_id", "course_id", "recorded_by_id", "recorded_at",
    "overall_risk_score", "classification",
    "attendance_percentage", "attendance_risk_score", "attendance_weight",
    "performance_percentage", "performance_risk_score", "performance_weight",
    "assignment_percentage", "assignment_risk_score", "assignment_weight",
    "explanations_json",
)


def _names(connection, object_type):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?", (object_type,)
    ).fetchall()
    return {row[0] for row in rows}


def _row_counts(connection, tables):
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in sorted(tables)
    }


def make_backup(db_path):
    """Copy the database with SQLite's backup API (consistent even if it is open)."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(
        f"{db_path.stem}.backup_before_risk_snapshots_{stamp}{db_path.suffix}"
    )
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def migrate(db_path=DEFAULT_DB, backup=True):
    """Add the risk_snapshots table, indexes and triggers if they are missing.

    Returns a dictionary:
        status   "applied" or "already_applied"
        backup   path of the backup file (str) or None
        created  list of the objects that were created
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    connection = sqlite3.connect(db_path)
    connection.isolation_level = None          # we control the transaction ourselves

    try:
        tables = _names(connection, "table")

        missing_prerequisites = [t for t in REQUIRED_EXISTING_TABLES if t not in tables]
        if missing_prerequisites:
            raise RuntimeError(
                "This does not look like an Academic Risk database (missing tables: "
                + ", ".join(missing_prerequisites)
                + "). Run `python init_db.py` first."
            )

        table_exists = TABLE_NAME in tables
        if table_exists:
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")]
            missing_columns = [c for c in EXPECTED_COLUMNS if c not in columns]
            if missing_columns:
                raise RuntimeError(
                    f"The existing {TABLE_NAME} table is missing columns: "
                    + ", ".join(missing_columns)
                    + ". Nothing was changed. Restore from your backup and ask for help."
                )

        missing_indexes = [n for n in INDEX_SQL if n not in _names(connection, "index")]
        missing_triggers = [n for n in TRIGGER_SQL if n not in _names(connection, "trigger")]

        if table_exists and not missing_indexes and not missing_triggers:
            return {"status": "already_applied", "backup": None, "created": []}

        backup_path = make_backup(db_path) if backup else None

        other_tables = tables - {TABLE_NAME}
        counts_before = _row_counts(connection, other_tables)

        created = []
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        try:
            if not table_exists:
                connection.execute(CREATE_TABLE_SQL)
                created.append(f"table {TABLE_NAME}")
            for name in missing_indexes:
                connection.execute(INDEX_SQL[name])
                created.append(f"index {name}")
            for name in missing_triggers:
                connection.execute(TRIGGER_SQL[name])
                created.append(f"trigger {name}")

            counts_after = _row_counts(connection, other_tables)
            if counts_after != counts_before:
                raise RuntimeError(
                    "Row counts of existing tables changed unexpectedly; "
                    "the migration was rolled back."
                )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

        problems = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if problems or integrity != "ok":
            raise RuntimeError(
                "Post-migration checks failed (integrity: %s, foreign key problems: %d). "
                "Restore from the backup%s." % (
                    integrity, len(problems),
                    f" ({backup_path})" if backup_path else ""),
            )

        return {
            "status": "applied",
            "backup": str(backup_path) if backup_path else None,
            "created": created,
        }
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add the risk_snapshots table safely.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the SQLite database")
    parser.add_argument("--no-backup", action="store_true", help="do not make a backup first")
    args = parser.parse_args(argv)

    try:
        result = migrate(args.db, backup=not args.no_backup)
    except (FileNotFoundError, RuntimeError) as error:
        print("MIGRATION NOT APPLIED:", error)
        return 1

    if result["status"] == "already_applied":
        print("Migration already applied. No changes needed.")
        return 0

    if result["backup"]:
        print("Backup created:", result["backup"])
    for item in result["created"]:
        print("Created:", item)
    print("Migration completed successfully. Existing data was not modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
