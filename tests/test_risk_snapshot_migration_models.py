"""Phase 12: the migration script and the SQLAlchemy model must describe the SAME table.

migrate_risk_snapshots.py (used on existing databases) and RiskSnapshot in models.py
(used by db.create_all on fresh databases) are written separately. These tests fail
if they ever drift apart.
"""
import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import text

import migrate_risk_snapshots as migration
from app import db
from app.models import RISK_SNAPSHOT_TRIGGER_SQL, RiskSnapshot


def create_all_table_info():
    rows = db.session.execute(text("PRAGMA table_info(risk_snapshots)")).fetchall()
    return {(r[1], r[2].upper(), r[3], r[5]) for r in rows}          # name, type, notnull, pk


def migration_table_info():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "old.db"
        connection = sqlite3.connect(path)
        connection.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            CREATE TABLE students (id INTEGER PRIMARY KEY);
            CREATE TABLE courses (id INTEGER PRIMARY KEY);
        """)
        connection.commit()
        connection.close()
        migration.migrate(path, backup=False)
        connection = sqlite3.connect(path)
        rows = connection.execute("PRAGMA table_info(risk_snapshots)").fetchall()
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='risk_snapshots'").fetchone()[0]
        indexes = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")}
        triggers = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        connection.close()
        return {(r[1], r[2].upper(), r[3], r[5]) for r in rows}, sql, indexes, triggers


def test_migration_and_model_create_the_same_columns(app):
    migrated_info, _sql, _indexes, _triggers = migration_table_info()

    with app.app_context():
        assert migrated_info == create_all_table_info()


def test_migration_expected_columns_match_the_model():
    assert set(migration.EXPECTED_COLUMNS) == {c.name for c in RiskSnapshot.__table__.columns}


def test_migration_and_model_use_the_same_triggers():
    assert migration.TRIGGER_SQL == RISK_SNAPSHOT_TRIGGER_SQL


def test_create_all_also_creates_the_immutability_triggers_and_indexes(app):
    names = {row[0] for row in db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type IN ('trigger','index')"))}
    assert set(RISK_SNAPSHOT_TRIGGER_SQL) <= names
    assert {"ix_risk_snapshots_student_course_time", "ix_risk_snapshots_course"} <= names


def test_migration_creates_the_same_indexes_triggers_and_constraints_as_the_model(app):
    _info, sql, indexes, triggers = migration_table_info()
    assert {"ix_risk_snapshots_student_course_time", "ix_risk_snapshots_course"} <= indexes
    assert set(RISK_SNAPSHOT_TRIGGER_SQL) == triggers
    model_sql = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name='risk_snapshots'")).fetchone()[0]
    for constraint in ("ck_risk_snapshot_classification",
                       "ck_risk_snapshot_score_not_negative",
                       "ck_risk_snapshot_pending_has_no_score"):
        assert constraint in sql and constraint in model_sql
    assert sql.count("ON DELETE RESTRICT") == model_sql.count("ON DELETE RESTRICT") == 3
