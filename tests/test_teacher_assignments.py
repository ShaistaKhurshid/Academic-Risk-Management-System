from datetime import date

from app.models import Assignment, AssignmentSubmission, User


def test_teacher_can_create_assignment(app, teacher_client, build):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    course = build.course(teacher=teacher)

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/assignments/create",
        data={
            "title": "Assignment 1",
            "deadline": "2026-11-30",
        },
    )

    assert response.status_code == 302

    assignment = Assignment.query.filter_by(
        course_id=course.id,
        title="Assignment 1",
    ).one()

    assert assignment.deadline == date(2026, 11, 30)
    assert assignment.original_deadline == date(2026, 11, 30)
def test_teacher_cannot_create_more_than_five_assignments(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    course = build.course(teacher=teacher)

    from app import db

    for number in range(1, 6):
        assignment = Assignment(
            course_id=course.id,
            title=f"Assignment {number}",
            original_deadline=date(2026, 11, 30),
            deadline=date(2026, 11, 30),
        )
        db.session.add(assignment)

    db.session.commit()

    response = teacher_client.post(
        f"/teacher/courses/{course.id}/assignments/create",
        data={
            "title": "Assignment 6",
            "deadline": "2026-12-05",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert Assignment.query.filter_by(course_id=course.id).count() == 5
    assert b"already has five assignments" in response.data
def test_teacher_can_update_deadline_without_changing_original(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    course = build.course(teacher=teacher)

    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        original_deadline=date(2026, 11, 30),
        deadline=date(2026, 11, 30),
    )

    from app import db
    db.session.add(assignment)
    db.session.commit()

    response = teacher_client.post(
        f"/teacher/assignments/{assignment.id}/edit-deadline",
        data={"deadline": "2026-12-10"},
    )

    assert response.status_code == 302

    db.session.refresh(assignment)

    assert assignment.original_deadline == date(2026, 11, 30)
    assert assignment.deadline == date(2026, 12, 10) 
def test_teacher_can_update_deadline_without_changing_original(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    course = build.course(teacher=teacher)

    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        original_deadline=date(2026, 11, 30),
        deadline=date(2026, 11, 30),
    )

    from app import db

    db.session.add(assignment)
    db.session.commit()

    response = teacher_client.post(
        f"/teacher/assignments/{assignment.id}/edit-deadline",
        data={"deadline": "2026-12-10"},
    )

    assert response.status_code == 302

    db.session.refresh(assignment)

    assert assignment.original_deadline == date(2026, 11, 30)
    assert assignment.deadline == date(2026, 12, 10)
def test_teacher_can_save_assignment_submission_status(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        original_deadline=date(2026, 11, 30),
        deadline=date(2026, 11, 30),
    )

    from app import db
    db.session.add(assignment)
    db.session.commit()

    response = teacher_client.post(
        f"/teacher/assignments/{assignment.id}/submissions",
        data={
            "submissions-0-student_id": str(student.id),
            "submissions-0-status": "Submitted",
            "submit": "Save Submission Statuses",
        },
    )

    assert response.status_code == 302

    submission = AssignmentSubmission.query.filter_by(
        assignment_id=assignment.id,
        student_id=student.id,
    ).one()

    assert submission.status == "Submitted"     
def test_teacher_can_update_existing_submission(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(student, course)

    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        original_deadline=date(2026, 11, 30),
        deadline=date(2026, 11, 30),
    )

    from app import db

    db.session.add(assignment)
    db.session.commit()

    existing = AssignmentSubmission(
        assignment_id=assignment.id,
        student_id=student.id,
        status="Submitted",
    )
    db.session.add(existing)
    db.session.commit()

    response = teacher_client.post(
        f"/teacher/assignments/{assignment.id}/submissions",
        data={
            "submissions-0-student_id": str(student.id),
            "submissions-0-status": "Excused",
            "submit": "Save Submission Statuses",
        },
    )

    assert response.status_code == 302

    records = AssignmentSubmission.query.filter_by(
        assignment_id=assignment.id,
        student_id=student.id,
    ).all()

    assert len(records) == 1
    assert records[0].status == "Excused"      
def test_teacher_cannot_access_another_teachers_assignment_submissions(
    app, teacher_client, build
):
    other_teacher = build.teacher()
    course = build.course(teacher=other_teacher)

    assignment = Assignment(
        course_id=course.id,
        title="Other Teacher Assignment",
        original_deadline=date(2026, 11, 30),
        deadline=date(2026, 11, 30),
    )

    from app import db
    db.session.add(assignment)
    db.session.commit()

    response = teacher_client.get(
        f"/teacher/assignments/{assignment.id}/submissions"
    )

    assert response.status_code == 403        
def test_unenrolled_student_submission_is_rejected(
    app, teacher_client, build
):
    teacher = User.query.filter_by(email="teacher@test.local").one()
    enrolled_student = build.student()
    unenrolled_student = build.student()
    course = build.course(teacher=teacher)
    build.enrol(enrolled_student, course)

    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        original_deadline=date(2026, 11, 30),
        deadline=date(2026, 11, 30),
    )

    from app import db
    db.session.add(assignment)
    db.session.commit()

    response = teacher_client.post(
        f"/teacher/assignments/{assignment.id}/submissions",
        data={
            "submissions-0-student_id": str(unenrolled_student.id),
            "submissions-0-status": "Submitted",
            "submit": "Save Submission Statuses",
        },
    )

    assert response.status_code == 400

    assert AssignmentSubmission.query.filter_by(
        assignment_id=assignment.id,
        student_id=unenrolled_student.id,
    ).count() == 0    