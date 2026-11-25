"""Tests that the database rules (unique, check, foreign key, cascade) really work."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (User, Student, Course, Enrolment, Attendance,
                        Assessment, StudentAssessment, FollowUp, ROLE_TEACHER)


# ---- small helpers to build rows -------------------------------------------
def make_student(student_id="S001", email="s001@test.local"):
    student = Student(student_id=student_id, name="Test Student", email=email,
                      semester="Semester 3")
    db.session.add(student)
    db.session.commit()
    return student


def make_course(code="CS201", teacher=None):
    course = Course(code=code, name="Test Course", teacher_id=teacher.id if teacher else None)
    db.session.add(course)
    db.session.commit()
    return course


# ---- tests -----------------------------------------------------------------
def test_student_id_must_be_unique(app):
    make_student("S001", "a@test.local")
    with pytest.raises(IntegrityError):
        make_student("S001", "b@test.local")
    db.session.rollback()


def test_duplicate_enrolment_is_blocked(app):
    student, course = make_student(), make_course()
    db.session.add(Enrolment(student_id=student.id, course_id=course.id))
    db.session.commit()
    db.session.add(Enrolment(student_id=student.id, course_id=course.id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_duplicate_attendance_is_blocked(app):
    student, course = make_student(), make_course()
    day = date(2026, 11, 21)
    db.session.add(Attendance(student_id=student.id, course_id=course.id,
                              session_date=day, status="Present"))
    db.session.commit()
    db.session.add(Attendance(student_id=student.id, course_id=course.id,
                              session_date=day, status="Absent"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_invalid_attendance_status_is_blocked(app):
    student, course = make_student(), make_course()
    db.session.add(Attendance(student_id=student.id, course_id=course.id,
                              session_date=date(2026, 11, 21), status="Sleeping"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_negative_marks_are_blocked_but_missing_marks_are_allowed(app):
    student, course = make_student(), make_course()
    test = Assessment(course_id=course.id, title="Quiz 1", max_marks=20)
    db.session.add(test)
    db.session.commit()

    # None = not graded yet: allowed
    db.session.add(StudentAssessment(assessment_id=test.id, student_id=student.id,
                                     marks_obtained=None))
    db.session.commit()
    db.session.delete(StudentAssessment.query.first())
    db.session.commit()

    # negative: blocked
    db.session.add(StudentAssessment(assessment_id=test.id, student_id=student.id,
                                     marks_obtained=-1))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_zero_max_marks_is_blocked(app):
    course = make_course()
    db.session.add(Assessment(course_id=course.id, title="Bad", max_marks=0))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_foreign_keys_are_enforced(app):
    """Proves the SQLite 'PRAGMA foreign_keys=ON' switch is working."""
    course = make_course()
    db.session.add(Enrolment(student_id=99999, course_id=course.id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleting_a_course_deletes_its_enrolments(app):
    student, course = make_student(), make_course()
    db.session.add(Enrolment(student_id=student.id, course_id=course.id))
    db.session.commit()

    db.session.delete(course)
    db.session.commit()

    assert Enrolment.query.count() == 0
    assert Student.query.count() == 1          # the student is NOT deleted


def test_deleting_a_teacher_keeps_the_course(app):
    teacher = User(full_name="T", email="t@test.local", role=ROLE_TEACHER)
    teacher.set_password("x")
    db.session.add(teacher)
    db.session.commit()
    course = make_course(teacher=teacher)

    db.session.delete(teacher)
    db.session.commit()

    db.session.refresh(course)
    assert course.teacher_id is None


def test_teacher_with_follow_ups_cannot_be_deleted(app):
    teacher = User(full_name="T", email="t@test.local", role=ROLE_TEACHER)
    teacher.set_password("x")
    db.session.add(teacher)
    db.session.commit()
    student, course = make_student(), make_course(teacher=teacher)
    db.session.add(FollowUp(student_id=student.id, course_id=course.id,
                            teacher_id=teacher.id, action_taken="Discussed attendance"))
    db.session.commit()

    db.session.delete(teacher)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
