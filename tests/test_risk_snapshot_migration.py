"""Phase 12: migrate_risk_snapshots.py must add the new table WITHOUT touching data.

These tests use only sqlite3 and temporary files (no Flask), so they run against a
realistic "old" database that already contains data.
"""
import sqlite3
import tempfile
from pathlib import Path

import migrate_risk_snapshots as migration


# ------------------------------------------------------------------ helpers
def make_old_database(path):
    """A database as it looks BEFORE Phase 12, with existing data."""
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, role TEXT);
        CREATE TABLE students (id INTEGER PRIMARY KEY, student_id TEXT, name TEXT);
        CREATE TABLE courses (id INTEGER PRIMARY KEY, code TEXT, teacher_id INTEGER);
        CREATE TABLE enrolments (id INTEGER PRIMARY KEY, student_id INTEGER, course_id INTEGER);
        CREATE TABLE attendance (id INTEGER PRIMARY KEY, student_id INTEGER,
                                 course_id INTEGER, session_date DATE, status TEXT);
        INSERT INTO users VALUES (1, 'Dr. Asha Verma', 'teacher1@college.test', 'teacher');
        INSERT INTO users VALUES (2, 'Demo Admin', 'admin@college.test', 'admin');
        INSERT INTO students VALUES (1, 'S001', 'Student One');
        INSERT INTO students VALUES (2, 'S002', 'Student Two');
        INSERT INTO courses VALUES (1, 'CS201', 1);
        INSERT INTO enrolments VALUES (1, 1, 1);
        INSERT INTO enrolments VALUES (2, 2, 1);
        INSERT INTO attendance VALUES (1, 1, 1, '2026-11-01', 'Present');
        INSERT INTO attendance VALUES (2, 2, 1, '2026-11-01', 'Absent');
    """)
    connection.commit()
    connection.close()


def dump(path, exclude=("risk_snapshots",)):
    """Every row of every table (except the excluded ones), for before/after comparison."""
    connection = sqlite3.connect(path)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: sorted(connection.execute(f'SELECT * FROM "{t}"').fetchall())
                for t in tables if t not in exclude}
    finally:
        connection.close()


def names(path, kind):
    connection = sqlite3.connect(path)
    try:
        return {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type=?", (kind,))}
    finally:
        connection.close()


def backups_in(folder):
    return sorted(p.name for p in Path(folder).glob("*backup_before_risk_snapshots*"))


def valid_snapshot_values(**overrides):
    values = {
        "student_id": 1, "course_id": 1, "recorded_by_id": 1,
        "recorded_at": "2026-11-20 10:00:00",
        "overall_risk_score": 12.5, "classification": "Low Risk",
        "explanations_json": "[]",
    }
    values.update(overrides)
    return values


def insert_snapshot(connection, **overrides):
    values = valid_snapshot_values(**overrides)
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    connection.execute(f"INSERT INTO risk_snapshots ({columns}) VALUES ({marks})",
                       list(values.values()))


def migrated_database(folder):
    path = Path(folder) / "academic_risk.db"
    make_old_database(path)
    migration.migrate(path)
    return path


def expect_database_error(action, needle=None):
    try:
        action()
    except sqlite3.DatabaseError as error:
        if needle is not None:
            assert needle in str(error), f"{needle!r} not in {error!r}"
        return
    raise AssertionError("expected the database to refuse this, but it was accepted")


# ----------------------------------------------------------------- the tests
def test_migration_creates_table_indexes_and_triggers():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        result = migration.migrate(path)

        assert result["status"] == "applied"
        assert "risk_snapshots" in names(path, "table")
        assert set(migration.INDEX_SQL) <= names(path, "index")
        assert set(migration.TRIGGER_SQL) <= names(path, "trigger")


def test_migration_creates_exactly_the_expected_columns_in_order():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(risk_snapshots)"))
        connection.close()
        assert columns == migration.EXPECTED_COLUMNS


def test_migration_does_not_change_any_existing_data():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        before = dump(path)

        migration.migrate(path)

        assert dump(path) == before


def test_migration_makes_a_backup_of_the_original_data():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        before = dump(path)

        result = migration.migrate(path)

        assert result["backup"] is not None
        backup = Path(result["backup"])
        assert backup.exists() and backup.parent == path.parent
        assert dump(backup) == before                       # backup holds the old data
        assert "risk_snapshots" not in names(backup, "table")   # ... and predates the change


def test_running_twice_is_safe_and_makes_no_second_backup():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)

        first = migration.migrate(path)
        data_after_first = dump(path)
        second = migration.migrate(path)

        assert first["status"] == "applied"
        assert second["status"] == "already_applied"
        assert second["backup"] is None and second["created"] == []
        assert len(backups_in(folder)) == 1
        assert dump(path) == data_after_first


def test_second_run_keeps_existing_snapshots():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        insert_snapshot(connection)
        connection.commit()
        connection.close()

        migration.migrate(path)

        connection = sqlite3.connect(path)
        assert connection.execute("SELECT COUNT(*) FROM risk_snapshots").fetchone()[0] == 1
        connection.close()


def test_no_backup_option_skips_the_backup():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        result = migration.migrate(path, backup=False)
        assert result["status"] == "applied" and result["backup"] is None
        assert backups_in(folder) == []


def test_missing_database_is_an_error_and_nothing_is_created():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "does_not_exist.db"
        try:
            migration.migrate(path)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError")
        assert not path.exists()
        assert list(Path(folder).iterdir()) == []


def test_database_without_the_core_tables_is_refused():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "empty.db"
        sqlite3.connect(path).close()                       # an empty SQLite file
        try:
            migration.migrate(path)
        except RuntimeError as error:
            assert "init_db.py" in str(error)
        else:
            raise AssertionError("expected RuntimeError")
        assert "risk_snapshots" not in names(path, "table")
        assert backups_in(folder) == []


def test_partial_state_only_adds_what_is_missing_and_keeps_snapshots():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        insert_snapshot(connection)
        connection.execute("DROP TRIGGER trg_risk_snapshots_no_update")   # simulate partial state
        connection.commit()
        connection.close()

        result = migration.migrate(path)

        assert result["status"] == "applied"
        assert result["created"] == ["trigger trg_risk_snapshots_no_update"]
        connection = sqlite3.connect(path)
        assert connection.execute("SELECT COUNT(*) FROM risk_snapshots").fetchone()[0] == 1
        connection.close()
        assert set(migration.TRIGGER_SQL) <= names(path, "trigger")


def test_existing_table_with_missing_columns_is_refused_untouched():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE risk_snapshots (id INTEGER PRIMARY KEY)")
        connection.commit()
        connection.close()
        before = dump(path, exclude=())

        try:
            migration.migrate(path)
        except RuntimeError as error:
            assert "missing columns" in str(error)
        else:
            raise AssertionError("expected RuntimeError")

        assert dump(path, exclude=()) == before
        assert backups_in(folder) == []


def test_rollback_when_row_counts_change_unexpectedly():
    """The safety net: if existing row counts differ mid-migration, nothing is kept."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        original = migration._row_counts
        calls = {"n": 0}

        def lying_row_counts(connection, tables):
            calls["n"] += 1
            counts = original(connection, tables)
            if calls["n"] == 2:                              # the "after" measurement
                counts["students"] += 1
            return counts

        migration._row_counts = lying_row_counts
        try:
            try:
                migration.migrate(path)
            except RuntimeError as error:
                assert "rolled back" in str(error)
            else:
                raise AssertionError("expected RuntimeError")
        finally:
            migration._row_counts = original

        assert "risk_snapshots" not in names(path, "table")
        assert not (names(path, "trigger") & set(migration.TRIGGER_SQL))


# ------------------------------------------ the migrated table's safety rules
def test_snapshots_cannot_be_updated():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        insert_snapshot(connection)
        connection.commit()
        expect_database_error(
            lambda: connection.execute("UPDATE risk_snapshots SET overall_risk_score = 99"),
            "immutable")
        connection.close()


def test_snapshots_cannot_be_deleted():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        insert_snapshot(connection)
        connection.commit()
        expect_database_error(lambda: connection.execute("DELETE FROM risk_snapshots"), "immutable")
        assert connection.execute("SELECT COUNT(*) FROM risk_snapshots").fetchone()[0] == 1
        connection.close()


def test_invalid_classification_is_refused():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        expect_database_error(lambda: insert_snapshot(connection, classification="Severe"))
        connection.close()


def test_pending_snapshot_must_have_no_score_and_scored_snapshot_must_not_be_pending():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")

        insert_snapshot(connection, classification="Pending", overall_risk_score=None)   # valid

        expect_database_error(
            lambda: insert_snapshot(connection, classification="Pending", overall_risk_score=0.0))
        expect_database_error(
            lambda: insert_snapshot(connection, classification="Low Risk", overall_risk_score=None))
        connection.close()


def test_negative_score_is_refused():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        expect_database_error(lambda: insert_snapshot(connection, overall_risk_score=-1.0))
        connection.close()


def test_unavailable_indicators_are_stored_as_null_not_zero():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        insert_snapshot(connection, attendance_percentage=0.0, performance_percentage=None)
        row = connection.execute(
            "SELECT attendance_percentage, performance_percentage FROM risk_snapshots").fetchone()
        connection.close()
        assert row[0] == 0.0 and row[0] is not None       # a real zero
        assert row[1] is None                              # unavailable stays NULL


def test_unknown_student_or_course_or_teacher_is_refused():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        expect_database_error(lambda: insert_snapshot(connection, student_id=999))
        expect_database_error(lambda: insert_snapshot(connection, course_id=999))
        expect_database_error(lambda: insert_snapshot(connection, recorded_by_id=999))
        connection.close()


def test_a_student_with_snapshots_cannot_be_deleted():
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        insert_snapshot(connection)
        connection.commit()
        expect_database_error(lambda: connection.execute("DELETE FROM students WHERE id = 1"))
        assert connection.execute("SELECT COUNT(*) FROM students WHERE id = 1").fetchone()[0] == 1
        connection.close()


def test_every_foreign_key_uses_restrict_not_cascade():
    """History must never disappear because a parent row is deleted. The immutability
    trigger would also block a cascade, but RESTRICT is the first line of defence."""
    with tempfile.TemporaryDirectory() as folder:
        path = migrated_database(folder)
        connection = sqlite3.connect(path)
        rows = connection.execute("PRAGMA foreign_key_list(risk_snapshots)").fetchall()
        connection.close()
        # columns: id, seq, table, from, to, on_update, on_delete, match
        assert {(row[2], row[6]) for row in rows} == {
            ("students", "RESTRICT"), ("courses", "RESTRICT"), ("users", "RESTRICT")}


# --------------------------------------------------------------- command line
def test_command_line_reports_success_then_already_applied():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "academic_risk.db"
        make_old_database(path)
        assert migration.main(["--db", str(path)]) == 0
        assert migration.main(["--db", str(path)]) == 0
        assert len(backups_in(folder)) == 1


def test_command_line_returns_error_code_for_missing_database():
    with tempfile.TemporaryDirectory() as folder:
        assert migration.main(["--db", str(Path(folder) / "nope.db")]) == 1
