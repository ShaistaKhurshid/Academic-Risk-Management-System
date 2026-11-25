"""Phase 12: RiskSnapshot model rules and RiskHistoryService (needs the database).

Remember (see conftest.py): use only ONE logged-in client per test.
"""
from datetime import date, datetime

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import db
from app.models import (Enrolment, RiskSnapshot, Student, StudentAssessment, User,
                        RISK_CLASSIFICATIONS)
from app.services.academic_risk_service import AcademicRiskService
from app.services.risk_history_service import RiskHistoryService
from app.services.risk_history_summary import (VALUE_FIELDS, snapshot_to_values,
                                               snapshot_values_from_report)


# ------------------------------------------------------------------ helpers
def my_teacher():
    return User.query.filter_by(email="teacher@test.local").first()


def owned_course_with_student(build, **student_kwargs):
    course = build.course(teacher=my_teacher())
    student = build.student(**student_kwargs)
    build.enrol(student, course)
    return course, student


def add_full_data(build, student, course):
    """Attendance 75%, marks 50%, assignments 60% -> overall 8.0, Low Risk."""
    for day, status in [(1, "Present"), (2, "Present"), (3, "Present (Late)"), (4, "Absent")]:
        build.attendance(student, course, date(2026, 11, day), status)
    build.marks(build.assessment(course, max_marks=20, title="Quiz 1"), student, 10)
    statuses = ["Submitted", "Late Submission", "Not Submitted", "Excused", "Submitted"]
    for number, status in enumerate(statuses, start=1):
        build.submission(build.assignment(course, title=f"A{number}"), student, status)


def record(student, course):
    return RiskHistoryService.record_snapshot(student.id, course.id, my_teacher().id)


def make_snapshot(student, course, score=20.0, classification="Low Risk", **columns):
    values = dict(student_id=student.id, course_id=course.id,
                  recorded_by_id=my_teacher().id, overall_risk_score=score,
                  classification=classification, explanations_json="[]")
    values.update(columns)
    row = RiskSnapshot(**values)
    db.session.add(row)
    db.session.commit()
    return row


def snapshot_count():
    return RiskSnapshot.query.count()


# --------------------------------------------------------- creation + values
def test_recording_creates_a_snapshot_with_the_engine_values(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)

    snapshot, created = record(student, course)

    assert created is True
    report = AcademicRiskService.generate_report(student.id, course.id)
    assert snapshot.overall_risk_score == pytest.approx(report["overall"]["overall_risk_score"])
    assert snapshot.overall_risk_score == pytest.approx(8.0)
    assert snapshot.classification == "Low Risk"
    assert snapshot.attendance_percentage == 75.0
    assert snapshot.performance_percentage == 50.0
    assert snapshot.assignment_percentage == 60.0
    assert snapshot_to_values(snapshot) == snapshot_values_from_report(report)


def test_snapshot_stores_who_recorded_it_and_when(build):
    course, student = owned_course_with_student(build)
    before = datetime.now()
    snapshot, _ = record(student, course)
    assert snapshot.recorded_by_id == my_teacher().id
    assert snapshot.student_id == student.id and snapshot.course_id == course.id
    assert before.replace(microsecond=0) <= snapshot.recorded_at <= datetime.now()


def test_weights_used_are_stored(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    snapshot, _ = record(student, course)
    assert (snapshot.attendance_weight, snapshot.performance_weight,
            snapshot.assignment_weight) == (0.4, 0.4, 0.2)


def test_explanations_are_stored_as_json(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    snapshot, _ = record(student, course)
    assert snapshot.explanations_json == '["Assignment completion risk"]'


def test_pending_student_is_recorded_as_pending_with_no_values(build):
    course, student = owned_course_with_student(build)
    snapshot, created = record(student, course)
    assert created is True
    assert snapshot.classification == "Pending"
    assert snapshot.overall_risk_score is None
    for field in VALUE_FIELDS:
        if field not in ("classification", "explanations_json"):
            assert getattr(snapshot, field) is None, field
    assert snapshot.explanations_json == "[]"


def test_partial_data_stores_only_available_indicators(build):
    course, student = owned_course_with_student(build)
    for day, status in [(1, "Present"), (2, "Absent"), (3, "Absent"), (4, "Absent")]:
        build.attendance(student, course, date(2026, 11, day), status)
    snapshot, _ = record(student, course)

    assert snapshot.attendance_percentage == 25.0
    assert snapshot.attendance_weight == 1.0
    assert snapshot.performance_percentage is None
    assert snapshot.assignment_percentage is None
    assert snapshot.classification == "High Risk"


def test_zero_percentage_is_stored_as_zero_not_null(build):
    course, student = owned_course_with_student(build)
    for day in (1, 2, 3):
        build.attendance(student, course, date(2026, 11, day), "Absent")
    snapshot, _ = record(student, course)
    assert snapshot.attendance_percentage == 0.0
    assert snapshot.attendance_percentage is not None
    assert snapshot.performance_percentage is None


# ------------------------------------------------ duplicates and immutability
def test_recording_twice_without_changes_does_not_duplicate(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)

    first, created_first = record(student, course)
    second, created_second = record(student, course)

    assert (created_first, created_second) == (True, False)
    assert second.id == first.id
    assert snapshot_count() == 1


def test_changed_data_creates_a_second_snapshot_in_order(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    first, _ = record(student, course)

    build.attendance(student, course, date(2026, 11, 5), "Absent")      # data changes
    second, created = record(student, course)

    assert created is True and second.id != first.id
    history = RiskHistoryService.get_history(student.id, course.id)
    assert [row.id for row in history] == [first.id, second.id]
    assert RiskHistoryService.get_latest(student.id, course.id).id == second.id


def test_old_snapshot_does_not_change_when_current_data_is_updated(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    first, _ = record(student, course)
    first_id = first.id
    original_values = dict(snapshot_to_values(first))

    # Teacher edits marks and attendance afterwards.
    mark = StudentAssessment.query.filter_by(student_id=student.id).first()
    mark.marks_obtained = 20
    db.session.commit()
    build.attendance(student, course, date(2026, 11, 9), "Absent")

    db.session.expire_all()
    assert snapshot_to_values(db.session.get(RiskSnapshot, first_id)) == original_values
    # ... while the live calculation HAS moved on:
    live = snapshot_values_from_report(AcademicRiskService.generate_report(student.id, course.id))
    assert live["performance_percentage"] == 100.0


def test_a_snapshot_cannot_be_updated_through_the_orm(build):
    course, student = owned_course_with_student(build)
    snapshot, _ = record(student, course)
    snapshot_id = snapshot.id

    snapshot.classification = "High Risk"
    snapshot.overall_risk_score = 99.0
    with pytest.raises(DBAPIError):
        db.session.commit()
    db.session.rollback()

    kept = db.session.get(RiskSnapshot, snapshot_id)
    assert kept.classification == "Pending" and kept.overall_risk_score is None


def test_a_snapshot_cannot_be_bulk_updated(build):
    course, student = owned_course_with_student(build)
    record(student, course)
    with pytest.raises(DBAPIError):
        RiskSnapshot.query.update({"classification": "High Risk", "overall_risk_score": 99.0})
        db.session.commit()
    db.session.rollback()
    assert RiskSnapshot.query.first().classification == "Pending"


def test_a_snapshot_cannot_be_deleted(build):
    course, student = owned_course_with_student(build)
    snapshot, _ = record(student, course)
    db.session.delete(snapshot)
    with pytest.raises(DBAPIError):
        db.session.commit()
    db.session.rollback()
    assert snapshot_count() == 1


# ----------------------------------------------- several students and courses
def test_history_is_kept_separately_for_each_course(build):
    teacher = my_teacher()
    course_a, course_b = build.course(teacher=teacher), build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course_a)
    build.enrol(student, course_b)
    build.attendance(student, course_a, date(2026, 11, 1), "Present")
    build.attendance(student, course_b, date(2026, 11, 1), "Absent")

    snapshot_a, _ = record(student, course_a)
    snapshot_b, _ = record(student, course_b)

    assert snapshot_a.attendance_percentage == 100.0
    assert snapshot_b.attendance_percentage == 0.0
    assert [s.id for s in RiskHistoryService.get_history(student.id, course_a.id)] == [snapshot_a.id]
    assert [s.id for s in RiskHistoryService.get_history(student.id, course_b.id)] == [snapshot_b.id]


def test_history_is_kept_separately_for_each_student(build):
    course = build.course(teacher=my_teacher())
    first, second = build.student(), build.student()
    build.enrol(first, course)
    build.enrol(second, course)
    build.attendance(first, course, date(2026, 11, 1), "Present")
    build.attendance(second, course, date(2026, 11, 1), "Absent")
    record(first, course)
    record(second, course)
    assert len(RiskHistoryService.get_history(first.id, course.id)) == 1
    assert RiskHistoryService.get_history(first.id, course.id)[0].attendance_percentage == 100.0


def test_get_history_is_empty_when_nothing_was_recorded(build):
    course, student = owned_course_with_student(build)
    assert RiskHistoryService.get_history(student.id, course.id) == []
    assert RiskHistoryService.get_latest(student.id, course.id) is None


# --------------------------------------------------------- invalid combinations
def test_recording_for_a_student_not_enrolled_is_refused(build):
    course = build.course(teacher=my_teacher())
    outsider = build.student()
    with pytest.raises(ValueError):
        record(outsider, course)
    assert snapshot_count() == 0


def test_recording_for_unknown_student_or_course_is_refused_and_session_stays_usable(build):
    course, student = owned_course_with_student(build)
    with pytest.raises(ValueError):
        RiskHistoryService.record_snapshot(99999, course.id, my_teacher().id)
    with pytest.raises(ValueError):
        RiskHistoryService.record_snapshot(student.id, 99999, my_teacher().id)
    assert snapshot_count() == 0
    record(student, course)                              # the session still works
    assert snapshot_count() == 1


def test_student_enrolled_in_a_different_course_is_refused(build):
    teacher = my_teacher()
    course_a, course_b = build.course(teacher=teacher), build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course_b)
    with pytest.raises(ValueError):
        record(student, course_a)
    assert snapshot_count() == 0


# ------------------------------------------------------------- whole course
def test_course_recording_snapshots_every_enrolled_student_once(build):
    course = build.course(teacher=my_teacher())
    students = [build.student() for _ in range(3)]
    for student in students:
        build.enrol(student, course)
    add_full_data(build, students[0], course)             # one scored, two Pending

    result = RiskHistoryService.record_course_snapshots(course.id, my_teacher().id)
    assert result == {"recorded": 3, "unchanged": 0, "total": 3}
    assert snapshot_count() == 3

    again = RiskHistoryService.record_course_snapshots(course.id, my_teacher().id)
    assert again == {"recorded": 0, "unchanged": 3, "total": 3}
    assert snapshot_count() == 3


def test_course_recording_only_adds_for_students_whose_results_changed(build):
    course = build.course(teacher=my_teacher())
    first, second = build.student(), build.student()
    build.enrol(first, course)
    build.enrol(second, course)
    RiskHistoryService.record_course_snapshots(course.id, my_teacher().id)

    build.attendance(first, course, date(2026, 11, 1), "Absent")      # only `first` changes
    result = RiskHistoryService.record_course_snapshots(course.id, my_teacher().id)

    assert result == {"recorded": 1, "unchanged": 1, "total": 2}
    assert len(RiskHistoryService.get_history(first.id, course.id)) == 2
    assert len(RiskHistoryService.get_history(second.id, course.id)) == 1


def test_course_recording_ignores_other_courses(build):
    teacher = my_teacher()
    course, other_course = build.course(teacher=teacher), build.course(teacher=teacher)
    mine, theirs = build.student(), build.student()
    build.enrol(mine, course)
    build.enrol(theirs, other_course)
    RiskHistoryService.record_course_snapshots(course.id, teacher.id)
    assert RiskHistoryService.get_history(theirs.id, other_course.id) == []


def test_course_recording_with_no_students_records_nothing(build):
    course = build.course(teacher=my_teacher())
    assert RiskHistoryService.record_course_snapshots(course.id, my_teacher().id) == \
        {"recorded": 0, "unchanged": 0, "total": 0}


def test_course_recording_is_all_or_nothing(build, monkeypatch):
    course = build.course(teacher=my_teacher())
    for _ in range(3):
        build.enrol(build.student(), course)

    original = RiskHistoryService._add_snapshot_if_changed
    calls = {"n": 0}

    def fails_on_the_third_student(student_id, course_id, recorded_by_id):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated failure")
        return original(student_id, course_id, recorded_by_id)

    monkeypatch.setattr(RiskHistoryService, "_add_snapshot_if_changed",
                        staticmethod(fails_on_the_third_student))
    with pytest.raises(RuntimeError):
        RiskHistoryService.record_course_snapshots(course.id, my_teacher().id)

    assert snapshot_count() == 0


# ---------------------------------------------------------- database rules
def test_invalid_classification_is_refused(build):
    course, student = owned_course_with_student(build)
    with pytest.raises(IntegrityError):
        make_snapshot(student, course, classification="Severe")
    db.session.rollback()


def test_pending_with_a_score_and_scored_without_a_score_are_refused(build):
    course, student = owned_course_with_student(build)
    with pytest.raises(IntegrityError):
        make_snapshot(student, course, classification="Pending", score=0.0)
    db.session.rollback()
    with pytest.raises(IntegrityError):
        make_snapshot(student, course, classification="Low Risk", score=None)
    db.session.rollback()
    assert snapshot_count() == 0


def test_every_allowed_classification_can_be_stored(build):
    course, student = owned_course_with_student(build)
    for label in RISK_CLASSIFICATIONS:
        score = None if label == "Pending" else 10.0
        make_snapshot(student, course, classification=label, score=score)
    assert snapshot_count() == len(RISK_CLASSIFICATIONS)


def test_snapshot_for_unknown_student_is_refused(build):
    course, _student = owned_course_with_student(build)
    row = RiskSnapshot(student_id=99999, course_id=course.id, recorded_by_id=my_teacher().id,
                       overall_risk_score=5.0, classification="Low Risk", explanations_json="[]")
    db.session.add(row)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_a_student_or_course_or_teacher_with_snapshots_cannot_be_deleted(build):
    course, student = owned_course_with_student(build)
    record(student, course)

    for victim in (student, course, my_teacher()):
        db.session.delete(victim)
        with pytest.raises((IntegrityError, DBAPIError)):
            db.session.commit()
        db.session.rollback()
    assert snapshot_count() == 1


def test_unenrolling_a_student_keeps_their_history(build):
    course, student = owned_course_with_student(build)
    record(student, course)
    Enrolment.query.filter_by(student_id=student.id, course_id=course.id).delete()
    db.session.commit()
    assert snapshot_count() == 1


def test_dependent_record_counts_include_risk_history(build):
    course, student = owned_course_with_student(build)
    assert student.dependent_record_counts()["risk history snapshots"] == 0
    record(student, course)
    assert student.dependent_record_counts()["risk history snapshots"] == 1
    assert course.dependent_record_counts()["risk history snapshots"] == 1


def test_snapshot_value_fields_match_the_model_columns():
    columns = {column.name for column in RiskSnapshot.__table__.columns}
    assert set(VALUE_FIELDS) <= columns
    assert columns == set(VALUE_FIELDS) | {"id", "student_id", "course_id",
                                           "recorded_by_id", "recorded_at"}
