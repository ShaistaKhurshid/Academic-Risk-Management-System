"""Phase 11: the individual student risk detail page and its service.

Route tests check security first (login, role, course ownership, enrolment) and
then the content of the page. Service tests check that the detail service reuses
the existing risk engine and only reads the requested course's data.

Remember (see conftest.py): use only ONE logged-in client per test.
"""
from datetime import date

import pytest

from app.models import User
from app.services.academic_risk_service import AcademicRiskService
from app.services.student_risk_detail_service import StudentRiskDetailService


# ------------------------------------------------------------------ helpers
def my_teacher():
    """The active teacher created by conftest.py (the one teacher_client logs in as)."""
    return User.query.filter_by(email="teacher@test.local").first()


def detail_url(course, student):
    return f"/teacher/courses/{course.id}/students/{student.id}/risk"


def add_full_data(build, student, course):
    """Attendance 3/4 attended (75%), one graded + one ungraded quiz (50%),
    five assignments with a mix of statuses (60% complete). Expected overall
    risk score is 8.0 -> Low Risk."""
    sessions = [(1, "Present"), (2, "Present"), (3, "Present (Late)"), (4, "Absent")]
    for day, status in sessions:
        build.attendance(student, course, date(2026, 11, day), status)

    graded = build.assessment(course, max_marks=20, title="Quiz 1")
    build.marks(graded, student, 10)
    build.assessment(course, max_marks=30, title="Quiz 2 Ungraded")   # no marks row

    statuses = ["Submitted", "Late Submission", "Not Submitted", "Excused", "Submitted"]
    for number, status in enumerate(statuses, start=1):
        assignment = build.assignment(course, title=f"Assignment {number}")
        build.submission(assignment, student, status)


def owned_course_with_student(build, **student_kwargs):
    course = build.course(teacher=my_teacher())
    student = build.student(**student_kwargs)
    build.enrol(student, course)
    return course, student


# ------------------------------------------------------------- access control
def test_anonymous_user_is_redirected_to_login(client, build):
    course = build.course()
    student = build.student()
    build.enrol(student, course)
    response = client.get(detail_url(course, student))
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_administrator_cannot_open_student_risk_details(admin_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    assert admin_client.get(detail_url(course, student)).status_code == 403


def test_owner_teacher_can_open_the_page(teacher_client, build):
    course, student = owned_course_with_student(build, name="Visible Student")
    response = teacher_client.get(detail_url(course, student))
    assert response.status_code == 200
    assert b"Visible Student" in response.data
    assert course.code.encode() in response.data


def test_teacher_cannot_open_details_for_another_teachers_course(teacher_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student(name="Secret Student")
    build.enrol(student, course)
    response = teacher_client.get(detail_url(course, student))
    assert response.status_code == 403
    assert b"Secret Student" not in response.data       # no data leaks in the error page


def test_course_with_no_teacher_is_not_accessible(teacher_client, build):
    course = build.course()                               # unassigned
    student = build.student()
    build.enrol(student, course)
    assert teacher_client.get(detail_url(course, student)).status_code == 403


def test_unknown_course_gives_404(teacher_client, build):
    student = build.student()
    assert teacher_client.get(f"/teacher/courses/99999/students/{student.id}/risk").status_code == 404


def test_student_not_enrolled_in_the_course_gives_404(teacher_client, build):
    course = build.course(teacher=my_teacher())
    outsider = build.student(name="Outsider Student")
    response = teacher_client.get(detail_url(course, outsider))
    assert response.status_code == 404
    assert b"Outsider Student" not in response.data


def test_student_enrolled_only_in_a_different_owned_course_gives_404(teacher_client, build):
    teacher = my_teacher()
    course_a, course_b = build.course(teacher=teacher), build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course_b)                       # enrolled in B only
    assert teacher_client.get(detail_url(course_a, student)).status_code == 404


def test_unknown_student_gives_404(teacher_client, build):
    course = build.course(teacher=my_teacher())
    assert teacher_client.get(f"/teacher/courses/{course.id}/students/99999/risk").status_code == 404


def test_non_numeric_or_injected_ids_give_404(teacher_client):
    for url in ["/teacher/courses/abc/students/1/risk",
                "/teacher/courses/1/students/abc/risk",
                "/teacher/courses/1/students/1%27%20OR%201=1--/risk"]:
        assert teacher_client.get(url).status_code == 404, url


def test_student_details_are_html_escaped(teacher_client, build):
    course, student = owned_course_with_student(build, name="<b>Bold</b>")
    response = teacher_client.get(detail_url(course, student))
    assert response.status_code == 200
    assert b"&lt;b&gt;Bold&lt;/b&gt;" in response.data
    assert b"<b>Bold</b>" not in response.data


# --------------------------------------------------------------- page content
def test_page_shows_the_complete_breakdown(teacher_client, build):
    course, student = owned_course_with_student(build, name="Full Data Student")
    add_full_data(build, student, course)
    text = teacher_client.get(detail_url(course, student)).get_data(as_text=True)

    assert "Attendance Breakdown" in text
    assert "Present (Late)" in text
    assert "Assessment Marks" in text
    assert "Quiz 1" in text and "Quiz 2 Ungraded" in text
    assert "Not graded" in text
    assert "Assignment Status" in text
    assert "Late Submission" in text
    assert "Risk Calculation" in text
    assert "Risk Explanations" in text
    assert "Recommended Interventions" in text
    assert "75.0%" in text and "50.0%" in text and "60.0%" in text
    assert "Low Risk" in text


def test_partial_data_uses_only_available_indicators(teacher_client, build):
    course, student = owned_course_with_student(build)
    for day, status in [(1, "Present"), (2, "Absent"), (3, "Present"), (4, "Absent")]:
        build.attendance(student, course, date(2026, 11, day), status)   # 50% only
    text = teacher_client.get(detail_url(course, student)).get_data(as_text=True)

    assert "Medium Risk" in text                        # 33.3 with weights rescaled to 100%
    assert "performance, assignments" in text           # unavailable indicators listed
    assert "No assessments have been created" in text
    assert "Assignment Pending" in text


def test_student_with_no_data_is_pending(teacher_client, build):
    course, student = owned_course_with_student(build)
    response = teacher_client.get(detail_url(course, student))
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Pending" in text
    assert "No attendance has been recorded" in text


def test_fewer_than_five_assignments_shows_assignment_pending(teacher_client, build):
    course, student = owned_course_with_student(build)
    for number in range(1, 4):
        build.submission(build.assignment(course, title=f"A{number}"), student, "Submitted")
    text = teacher_client.get(detail_url(course, student)).get_data(as_text=True)
    assert "3 of 5 required" in text


def test_missing_submission_record_is_not_shown_as_not_submitted(teacher_client, build):
    course, student = owned_course_with_student(build)
    for number in range(1, 6):
        assignment = build.assignment(course, title=f"A{number}")
        if number != 3:                                  # no record for assignment 3
            build.submission(assignment, student, "Submitted")
    text = teacher_client.get(detail_url(course, student)).get_data(as_text=True)
    assert "No record" in text
    assert "not recorded for 1 of 5" in text
    assert "Not Submitted: 0" in text


# ------------------------------------------------------------------- service
def test_service_report_is_exactly_the_existing_engine_output(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    detail = StudentRiskDetailService.generate_detail(student.id, course.id)
    assert detail["report"] == AcademicRiskService.generate_report(student.id, course.id)


def test_service_breakdown_counts_for_the_full_scenario(build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    detail = StudentRiskDetailService.generate_detail(student.id, course.id)

    attendance = detail["attendance"]
    assert (attendance["present_count"], attendance["late_count"],
            attendance["absent_count"], attendance["total_sessions"]) == (2, 1, 1, 4)

    assessments = detail["assessments"]
    assert (assessments["total_assessments"], assessments["graded_count"],
            assessments["ungraded_count"]) == (2, 1, 1)

    assignments = detail["assignments"]
    assert (assignments["submitted_count"], assignments["late_count"],
            assignments["not_submitted_count"], assignments["excused_count"]) == (2, 1, 1, 1)
    assert assignments["pending_message"] is None

    report = detail["report"]
    assert report["overall"]["overall_risk_score"] == pytest.approx(8.0)
    assert report["classification"] == "Low Risk"


def test_service_only_reads_the_requested_courses_records(build):
    teacher = my_teacher()
    course_a, course_b = build.course(teacher=teacher), build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course_a)
    build.enrol(student, course_b)

    build.attendance(student, course_a, date(2026, 11, 1), "Present")
    for day in (1, 2, 3):                                 # three absences, course B only
        build.attendance(student, course_b, date(2026, 11, day), "Absent")
    build.marks(build.assessment(course_b, max_marks=10), student, 1)

    detail = StudentRiskDetailService.generate_detail(student.id, course_a.id)

    assert detail["attendance"]["total_sessions"] == 1
    assert detail["attendance"]["absent_count"] == 0
    assert detail["assessments"]["total_assessments"] == 0
    assert detail["report"]["performance"]["available"] is False


def test_service_rejects_a_student_who_is_not_enrolled(build):
    course = build.course(teacher=my_teacher())
    student = build.student()
    with pytest.raises(ValueError):
        StudentRiskDetailService.generate_detail(student.id, course.id)


def test_service_rejects_unknown_ids(build):
    course, student = owned_course_with_student(build)
    with pytest.raises(ValueError):
        StudentRiskDetailService.generate_detail(99999, course.id)
    with pytest.raises(ValueError):
        StudentRiskDetailService.generate_detail(student.id, 99999)
