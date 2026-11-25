"""The course-level Risk Report page (a route that previously had no direct tests)."""
from datetime import date

from app.models import User


def my_teacher():
    return User.query.filter_by(email="teacher@test.local").first()


def report_url(course):
    return f"/teacher/courses/{course.id}/risk-report"


def test_anonymous_user_is_redirected_to_login(client, build):
    course = build.course()
    response = client.get(report_url(course))
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_administrator_cannot_open_the_risk_report(admin_client, build):
    course = build.course(teacher=build.teacher())
    assert admin_client.get(report_url(course)).status_code == 403


def test_teacher_cannot_open_another_teachers_risk_report(teacher_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student(name="Hidden Student")
    build.enrol(student, course)
    response = teacher_client.get(report_url(course))
    assert response.status_code == 403
    assert b"Hidden Student" not in response.data


def test_unknown_course_gives_404(teacher_client):
    assert teacher_client.get("/teacher/courses/99999/risk-report").status_code == 404


def test_report_lists_only_students_enrolled_in_the_course(teacher_client, build):
    course = build.course(teacher=my_teacher())
    enrolled = build.student(name="Alpha Enrolled")
    build.student(name="Beta Outsider")
    build.enrol(enrolled, course)
    text = teacher_client.get(report_url(course)).get_data(as_text=True)
    assert "Alpha Enrolled" in text
    assert "Beta Outsider" not in text


def test_course_without_students_shows_the_empty_state(teacher_client, build):
    course = build.course(teacher=my_teacher())
    text = teacher_client.get(report_url(course)).get_data(as_text=True)
    assert "No students are enrolled in this course yet" in text


def test_each_student_links_to_the_detail_page(teacher_client, build):
    course = build.course(teacher=my_teacher())
    first, second = build.student(), build.student()
    build.enrol(first, course)
    build.enrol(second, course)
    text = teacher_client.get(report_url(course)).get_data(as_text=True)
    assert f"/teacher/courses/{course.id}/students/{first.id}/risk" in text
    assert f"/teacher/courses/{course.id}/students/{second.id}/risk" in text


def test_every_student_has_four_rows_tagged_for_the_filters(teacher_client, build):
    """Server-side half of the filter feature: all four rows of a student carry the
    same data-risk value. (The JavaScript itself is not covered by these tests.)"""
    course = build.course(teacher=my_teacher())
    pending_student, high_student = build.student(), build.student()
    build.enrol(pending_student, course)
    build.enrol(high_student, course)
    build.attendance(high_student, course, date(2026, 11, 1), "Present")        # 1 of 4 = 25%
    for day in (2, 3, 4):
        build.attendance(high_student, course, date(2026, 11, day), "Absent")

    text = teacher_client.get(report_url(course)).get_data(as_text=True)

    assert text.count('data-risk="Pending"') == 4
    assert text.count('data-risk="High Risk"') == 4
    assert text.count('data-risk="Low Risk"') == 0
