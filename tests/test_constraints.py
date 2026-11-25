"""Database rules that Milestone 1 did not test yet, plus the cascade behaviour.

The cascade tests document what the MODEL does if a row is deleted. The admin
pages never allow such a delete when dependent records exist (see the admin tests).
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (User, Student, Course, Enrolment, Attendance, Assessment,
                        StudentAssessment, Assignment, AssignmentSubmission, FollowUp)


def commit_must_fail():
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ---- unique rules -----------------------------------------------------------
def test_user_email_is_unique_even_with_different_case(build):
    build.teacher(email="dup@test.local")
    db.session.add(User(full_name="B", email="DUP@test.local", role="teacher",
                        password_hash="x"))
    commit_must_fail()


def test_student_email_is_unique(build):
    build.student(email="same@test.local")
    db.session.add(Student(student_id="S999", name="B", email="same@test.local",
                           semester="Semester 1"))
    commit_must_fail()


def test_course_code_is_unique(build):
    build.course(code="CS201")
    db.session.add(Course(code="CS201", name="Other"))
    commit_must_fail()


def test_one_marks_row_per_student_per_assessment(build):
    student, course = build.student(), build.course()
    test = build.assessment(course)
    build.marks(test, student, 10)
    db.session.add(StudentAssessment(assessment_id=test.id, student_id=student.id,
                                     marks_obtained=12))
    commit_must_fail()


def test_one_submission_per_student_per_assignment(build):
    student, course = build.student(), build.course()
    work = build.assignment(course)
    build.submission(work, student)
    db.session.add(AssignmentSubmission(assignment_id=work.id, student_id=student.id,
                                        status="Not Submitted"))
    commit_must_fail()


# ---- check rules ------------------------------------------------------------
def test_invalid_user_role_is_blocked(app):
    db.session.add(User(full_name="Bad", email="bad@test.local", role="superuser",
                        password_hash="x"))
    commit_must_fail()


def test_invalid_submission_status_is_blocked(build):
    student, course = build.student(), build.course()
    work = build.assignment(course)
    db.session.add(AssignmentSubmission(assignment_id=work.id, student_id=student.id,
                                        status="Maybe"))
    commit_must_fail()


# ---- cascade behaviour (model level) ----------------------------------------
def make_full_graph(build):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course)
    build.attendance(student, course)
    test = build.assessment(course)
    build.marks(test, student)
    work = build.assignment(course)
    build.submission(work, student)
    build.follow_up(student, course, teacher)
    return teacher, course, student, test, work


def test_deleting_a_student_removes_only_that_students_rows(build):
    teacher, course, student, test, work = make_full_graph(build)
    db.session.delete(student)
    db.session.commit()
    assert Enrolment.query.count() == 0
    assert Attendance.query.count() == 0
    assert StudentAssessment.query.count() == 0
    assert AssignmentSubmission.query.count() == 0
    assert FollowUp.query.count() == 0
    assert Course.query.count() == 1            # course, assessment, assignment stay
    assert Assessment.query.count() == 1
    assert Assignment.query.count() == 1


def test_deleting_a_course_removes_everything_in_it_but_not_students(build):
    teacher, course, student, test, work = make_full_graph(build)
    db.session.delete(course)
    db.session.commit()
    assert Enrolment.query.count() == 0
    assert Attendance.query.count() == 0
    assert Assessment.query.count() == 0
    assert StudentAssessment.query.count() == 0
    assert Assignment.query.count() == 0
    assert AssignmentSubmission.query.count() == 0
    assert FollowUp.query.count() == 0
    assert Student.query.count() == 1


def test_deleting_an_assessment_removes_its_marks(build):
    teacher, course, student, test, work = make_full_graph(build)
    db.session.delete(test)
    db.session.commit()
    assert StudentAssessment.query.count() == 0


def test_deleting_an_assignment_removes_its_submissions(build):
    teacher, course, student, test, work = make_full_graph(build)
    db.session.delete(work)
    db.session.commit()
    assert AssignmentSubmission.query.count() == 0
