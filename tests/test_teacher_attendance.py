
from datetime import date

from app import db
from app.models import Attendance, User


def test_teacher_can_record_attendance(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/attendance",
        data={
            "session_date": "2026-11-21",
            "entries-0-student_id": str(student.id),
            "entries-0-status": "Present",
        },
    )

    assert response.status_code == 302

    record = Attendance.query.filter_by(
        student_id=student.id,
        course_id=course.id,
        session_date=date(2026, 11, 21),
    ).one()

    assert record.status == "Present"


def test_teacher_can_update_existing_attendance(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    build.attendance(
        student,
        course,
        day=date(2026, 11, 21),
        status="Present",
    )

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/attendance",
        data={
            "session_date": "2026-11-21",
            "entries-0-student_id": str(student.id),
            "entries-0-status": "Absent",
        },
    )

    assert response.status_code == 302

    records = Attendance.query.filter_by(
        student_id=student.id,
        course_id=course.id,
        session_date=date(2026, 11, 21),
    ).all()

    assert len(records) == 1
    assert records[0].status == "Absent"


def test_teacher_cannot_access_another_teachers_course(
    app, teacher_client, build
):
    other_teacher = build.teacher()
    course = build.course(teacher=other_teacher)

    response = teacher_client.get(
        f"/teacher/courses/{course.id}/attendance"
    )

    assert response.status_code == 403


def test_unenrolled_student_attendance_is_rejected(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    enrolled_student = build.student()
    unenrolled_student = build.student()
    course = build.course(teacher=teacher)

    build.enrol(enrolled_student, course)

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/attendance",
        data={
            "session_date": "2026-11-21",
            "entries-0-student_id": str(unenrolled_student.id),
            "entries-0-status": "Present",
        },
    )

    assert response.status_code == 200
    assert b"Attendance entries are invalid" in response.data

    assert Attendance.query.filter_by(
        student_id=unenrolled_student.id,
        course_id=course.id,
    ).count() == 0
def test_teacher_can_record_present_late(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/attendance",
        data={
            "session_date": "2026-11-21",
            "entries-0-student_id": str(student.id),
            "entries-0-status": "Present (Late)",
        },
    )

    assert response.status_code == 302

    record = Attendance.query.filter_by(
        student_id=student.id,
        course_id=course.id,
        session_date=date(2026, 11, 21),
    ).one()

    assert record.status == "Present (Late)"


def test_teacher_can_change_present_late_to_absent(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    build.attendance(
        student,
        course,
        day=date(2026, 11, 21),
        status="Present (Late)",
    )

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/attendance",
        data={
            "session_date": "2026-11-21",
            "entries-0-student_id": str(student.id),
            "entries-0-status": "Absent",
        },
    )

    assert response.status_code == 302

    records = Attendance.query.filter_by(
        student_id=student.id,
        course_id=course.id,
        session_date=date(2026, 11, 21),
    ).all()

    assert len(records) == 1
    assert records[0].status == "Absent"


def test_old_late_status_is_rejected(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/attendance",
        data={
            "session_date": "2026-11-21",
            "entries-0-student_id": str(student.id),
            "entries-0-status": "Late",
        },
    )

    assert response.status_code == 200

    assert Attendance.query.filter_by(
        student_id=student.id,
        course_id=course.id,
    ).count() == 0