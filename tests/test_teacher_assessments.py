from datetime import date

from app.models import Assessment, StudentAssessment, User


def test_teacher_can_create_assessment(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    course = build.course(teacher=teacher)

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/assessments/create",
        data={
            "title": "Unit Test 1",
            "max_marks": "50",
            "assessment_date": "2026-11-21",
        },
    )

    assert response.status_code == 302

    assessment = Assessment.query.filter_by(
        course_id=course.id,
        title="Unit Test 1",
    ).one()

    assert assessment.max_marks == 50
    assert assessment.assessment_date == date(2026, 11, 21)


def test_teacher_can_save_marks_for_enrolled_student(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)
    assessment = build.assessment(course, max_marks=20)

    response = teacher_client.post(
        f"/teacher/assessments/{assessment.id}/marks",
        data={
            "entries-0-student_id": str(student.id),
            "entries-0-marks_obtained": "15",
        },
    )

    assert response.status_code == 302

    record = StudentAssessment.query.filter_by(
        assessment_id=assessment.id,
        student_id=student.id,
    ).one()

    assert record.marks_obtained == 15


def test_teacher_can_update_existing_marks(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)
    assessment = build.assessment(course, max_marks=20)
    build.marks(assessment, student, marks_obtained=10)

    response = teacher_client.post(
        f"/teacher/assessments/{assessment.id}/marks",
        data={
            "entries-0-student_id": str(student.id),
            "entries-0-marks_obtained": "17",
        },
    )

    assert response.status_code == 302

    records = StudentAssessment.query.filter_by(
        assessment_id=assessment.id,
        student_id=student.id,
    ).all()

    assert len(records) == 1
    assert records[0].marks_obtained == 17


def test_marks_above_maximum_are_rejected(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)
    assessment = build.assessment(course, max_marks=20)

    response = teacher_client.post(
        f"/teacher/assessments/{assessment.id}/marks",
        data={
            "entries-0-student_id": str(student.id),
            "entries-0-marks_obtained": "25",
        },
    )

    assert response.status_code == 200
    assert b"Marks cannot exceed 20" in response.data

    assert StudentAssessment.query.filter_by(
        assessment_id=assessment.id,
        student_id=student.id,
    ).count() == 0


def test_unenrolled_student_marks_are_rejected(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    enrolled_student = build.student()
    unenrolled_student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(enrolled_student, course)
    assessment = build.assessment(course, max_marks=20)

    response = teacher_client.post(
        f"/teacher/assessments/{assessment.id}/marks",
        data={
            "entries-0-student_id": str(unenrolled_student.id),
            "entries-0-marks_obtained": "15",
        },
    )

    assert response.status_code == 302

    assert StudentAssessment.query.filter_by(
        assessment_id=assessment.id,
        student_id=unenrolled_student.id,
    ).count() == 0


def test_teacher_cannot_access_another_teachers_assessment_marks(
    app, teacher_client, build
):
    other_teacher = build.teacher()
    course = build.course(teacher=other_teacher)
    assessment = build.assessment(course, max_marks=20)

    response = teacher_client.get(
        f"/teacher/assessments/{assessment.id}/marks"
    )

    assert response.status_code == 403


def test_blank_marks_are_not_saved_as_zero(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)
    assessment = build.assessment(course, max_marks=20)

    response = teacher_client.post(
        f"/teacher/assessments/{assessment.id}/marks",
        data={
            "entries-0-student_id": str(student.id),
            "entries-0-marks_obtained": "",
        },
    )

    assert response.status_code == 302

    assert StudentAssessment.query.filter_by(
        assessment_id=assessment.id,
        student_id=student.id,
    ).count() == 0