"""Shared test setup: a fresh in-memory database for every test."""
from datetime import date

import pytest

from app import create_app, db
from app.models import (User, Student, Course, Enrolment, Attendance, Assessment,
                        StudentAssessment, Assignment, AssignmentSubmission,
                        FollowUp, ROLE_ADMIN, ROLE_TEACHER)
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()

        admin = User(full_name="Test Admin", email="admin@test.local", role=ROLE_ADMIN)
        admin.set_password("AdminPass1")
        teacher = User(full_name="Test Teacher", email="teacher@test.local", role=ROLE_TEACHER)
        teacher.set_password("TeacherPass1")
        inactive = User(full_name="Old Teacher", email="old@test.local",
                        role=ROLE_TEACHER, is_active=False)
        inactive.set_password("OldPass1")

        db.session.add_all([admin, teacher, inactive])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Milestone 2 helpers
#
# TEAM NOTE: these tests run inside ONE shared app context, so Flask-Login
# remembers the first user who logged in. Rule: use only ONE logged-in client
# per test (admin_client OR teacher_client, never both in the same test).
# ---------------------------------------------------------------------------
def _logged_in_client(app, email, password):
    client = app.test_client()
    response = client.post("/login", data={"email": email, "password": password})
    assert response.status_code == 302, "test login failed for " + email
    return client


@pytest.fixture()
def admin_client(app):
    """A test browser already logged in as the administrator."""
    return _logged_in_client(app, "admin@test.local", "AdminPass1")


@pytest.fixture()
def teacher_client(app):
    """A test browser already logged in as the (active) teacher."""
    return _logged_in_client(app, "teacher@test.local", "TeacherPass1")


@pytest.fixture()
def fresh(app):
    """fresh(Model, id) re-reads a row from the database, ignoring cached copies."""
    def _fresh(model, pk):
        db.session.expire_all()
        return db.session.get(model, pk)
    return _fresh


class Builder:
    """Creates test rows quickly. Every method saves to the database and returns the row."""

    def __init__(self):
        self.n = 0

    def _next(self):
        self.n += 1
        return self.n

    def student(self, **kwargs):
        n = self._next()
        data = dict(student_id=f"S{n:03d}", name=f"Student {n}",
                    email=f"student{n}@test.local", semester="Semester 3")
        data.update(kwargs)
        row = Student(**data)
        db.session.add(row)
        db.session.commit()
        return row

    def teacher(self, **kwargs):
        n = self._next()
        data = dict(full_name=f"Teacher {n}", email=f"teacher{n}@test.local",
                    role=ROLE_TEACHER, password_hash="not-a-real-hash")
        data.update(kwargs)
        row = User(**data)
        db.session.add(row)
        db.session.commit()
        return row

    def course(self, teacher=None, **kwargs):
        n = self._next()
        data = dict(code=f"C{n:03d}", name=f"Course {n}",
                    teacher_id=teacher.id if teacher else None)
        data.update(kwargs)
        row = Course(**data)
        db.session.add(row)
        db.session.commit()
        return row

    def enrol(self, student, course):
        row = Enrolment(student_id=student.id, course_id=course.id)
        db.session.add(row)
        db.session.commit()
        return row

    def attendance(self, student, course, day=date(2026, 11, 1), status="Present"):
        row = Attendance(student_id=student.id, course_id=course.id,
                         session_date=day, status=status)
        db.session.add(row)
        db.session.commit()
        return row

    def assessment(self, course, max_marks=20, title="Quiz 1"):
        row = Assessment(course_id=course.id, title=title, max_marks=max_marks)
        db.session.add(row)
        db.session.commit()
        return row

    def marks(self, assessment, student, marks_obtained=10):
        row = StudentAssessment(assessment_id=assessment.id, student_id=student.id,
                                marks_obtained=marks_obtained)
        db.session.add(row)
        db.session.commit()
        return row

    def assignment(self, course, title="Assignment 1", deadline=date(2026, 12, 1)):
        row = Assignment(course_id=course.id, title=title, deadline=deadline)
        db.session.add(row)
        db.session.commit()
        return row

    def submission(self, assignment, student, status="Submitted"):
        row = AssignmentSubmission(assignment_id=assignment.id, student_id=student.id,
                                   status=status)
        db.session.add(row)
        db.session.commit()
        return row

    def follow_up(self, student, course, teacher, action="Discussed attendance"):
        row = FollowUp(student_id=student.id, course_id=course.id,
                       teacher_id=teacher.id, action_taken=action)
        db.session.add(row)
        db.session.commit()
        return row

    def record(self, kind, student, course, teacher):
        """Create ONE academic record of the named kind for student+course."""
        if kind == "attendance":
            return self.attendance(student, course)
        if kind == "marks":
            return self.marks(self.assessment(course), student)
        if kind == "submission":
            return self.submission(self.assignment(course), student)
        if kind == "follow_up":
            return self.follow_up(student, course, teacher)
        raise ValueError("unknown record kind: " + kind)


@pytest.fixture()
def build(app):
    return Builder()


@pytest.fixture()
def csrf_app():
    """An app with CSRF protection switched ON (the normal TestConfig turns it off)."""
    class CsrfOnConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfOnConfig)
    with app.app_context():
        db.create_all()
        user = User(full_name="CSRF Admin", email="csrf@test.local", role=ROLE_ADMIN)
        user.set_password("CsrfPass123")
        db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()
