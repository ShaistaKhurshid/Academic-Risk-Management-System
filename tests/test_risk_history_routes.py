"""Phase 12: Risk History on the student detail page, and the record routes.

Security first (login, role, course ownership, enrolment, CSRF), then page content.
Remember (see conftest.py): use only ONE logged-in client per test.
"""
import re
from datetime import date, datetime

import pytest

from app import create_app, db
from app.models import Course, Enrolment, RiskSnapshot, Student, User, ROLE_TEACHER
from app.services.risk_history_service import RiskHistoryService
from config import TestConfig


# ------------------------------------------------------------------ helpers
def my_teacher():
    return User.query.filter_by(email="teacher@test.local").first()


def detail_url(course, student):
    return f"/teacher/courses/{course.id}/students/{student.id}/risk"


def record_url(course, student):
    return f"/teacher/courses/{course.id}/students/{student.id}/risk/record"


def bulk_url(course):
    return f"/teacher/courses/{course.id}/risk-report/record"


def owned_course_with_student(build, **student_kwargs):
    course = build.course(teacher=my_teacher())
    student = build.student(**student_kwargs)
    build.enrol(student, course)
    return course, student


def add_full_data(build, student, course):
    """Live result: attendance 75%, marks 50%, assignments 60% -> score 8.0, Low Risk."""
    for day, status in [(1, "Present"), (2, "Present"), (3, "Present (Late)"), (4, "Absent")]:
        build.attendance(student, course, date(2026, 11, day), status)
    build.marks(build.assessment(course, max_marks=20, title="Quiz 1"), student, 10)
    statuses = ["Submitted", "Late Submission", "Not Submitted", "Excused", "Submitted"]
    for number, status in enumerate(statuses, start=1):
        build.submission(build.assignment(course, title=f"A{number}"), student, status)


def make_snapshot(student, course, score=20.0, classification="Low Risk",
                  recorded_by=None, **columns):
    values = dict(student_id=student.id, course_id=course.id,
                  recorded_by_id=(recorded_by or my_teacher()).id,
                  overall_risk_score=score, classification=classification,
                  explanations_json="[]")
    values.update(columns)
    row = RiskSnapshot(**values)
    db.session.add(row)
    db.session.commit()
    return row


def page_text(client, course, student):
    response = client.get(detail_url(course, student))
    assert response.status_code == 200
    return response.get_data(as_text=True)


# ---------------------------------------- access control: the record action
def test_anonymous_cannot_record(client, build):
    course, student = owned_course_with_student(build)
    response = client.post(record_url(course, student))
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    assert RiskSnapshot.query.count() == 0


def test_administrator_cannot_record(admin_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    assert admin_client.post(record_url(course, student)).status_code == 403
    assert RiskSnapshot.query.count() == 0


def test_teacher_cannot_record_for_another_teachers_course(teacher_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    assert teacher_client.post(record_url(course, student)).status_code == 403
    assert RiskSnapshot.query.count() == 0


def test_teacher_cannot_record_for_an_unassigned_course(teacher_client, build):
    course = build.course()
    student = build.student()
    build.enrol(student, course)
    assert teacher_client.post(record_url(course, student)).status_code == 403


def test_recording_for_unknown_course_is_404(teacher_client, build):
    student = build.student()
    assert teacher_client.post(f"/teacher/courses/99999/students/{student.id}/risk/record").status_code == 404


def test_recording_for_a_student_not_enrolled_is_404(teacher_client, build):
    course = build.course(teacher=my_teacher())
    outsider = build.student()
    assert teacher_client.post(record_url(course, outsider)).status_code == 404
    assert RiskSnapshot.query.count() == 0


def test_recording_for_a_student_enrolled_only_elsewhere_is_404(teacher_client, build):
    teacher = my_teacher()
    course_a, course_b = build.course(teacher=teacher), build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course_b)
    assert teacher_client.post(record_url(course_a, student)).status_code == 404
    assert RiskSnapshot.query.count() == 0


def test_recording_with_unknown_student_is_404(teacher_client, build):
    course = build.course(teacher=my_teacher())
    assert teacher_client.post(f"/teacher/courses/{course.id}/students/99999/risk/record").status_code == 404


def test_record_url_does_not_accept_get(teacher_client, build):
    course, student = owned_course_with_student(build)
    assert teacher_client.get(record_url(course, student)).status_code == 405
    assert RiskSnapshot.query.count() == 0


def test_viewing_the_page_never_creates_a_snapshot(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    for _ in range(3):                                    # refreshing the page
        teacher_client.get(detail_url(course, student))
    assert RiskSnapshot.query.count() == 0


def test_non_numeric_ids_on_record_urls_are_404(teacher_client):
    for url in ["/teacher/courses/abc/students/1/risk/record",
                "/teacher/courses/1/students/1%27%20OR%201=1--/risk/record"]:
        assert teacher_client.post(url).status_code == 404, url


# ---------------------------------------------------- record action behaviour
def test_owner_can_record_and_is_redirected_back_to_the_history(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)

    response = teacher_client.post(record_url(course, student))

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.endswith(detail_url(course, student) + "#risk-history")
    snapshot = RiskSnapshot.query.one()
    assert snapshot.student_id == student.id and snapshot.course_id == course.id
    assert snapshot.recorded_by_id == my_teacher().id
    assert snapshot.classification == "Low Risk"


def test_refreshing_after_recording_does_not_add_another(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)

    teacher_client.post(record_url(course, student), follow_redirects=True)
    for _ in range(3):                                    # refresh the page after the redirect
        teacher_client.get(detail_url(course, student))

    assert RiskSnapshot.query.count() == 1


def test_recording_twice_without_changes_reports_nothing_new(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    teacher_client.post(record_url(course, student))

    response = teacher_client.post(record_url(course, student), follow_redirects=True)

    assert b"Nothing has changed" in response.data
    assert RiskSnapshot.query.count() == 1


def test_recording_after_a_data_change_adds_a_second_snapshot(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    teacher_client.post(record_url(course, student))
    build.attendance(student, course, date(2026, 11, 9), "Absent")

    response = teacher_client.post(record_url(course, student), follow_redirects=True)

    assert b"Risk assessment recorded" in response.data
    assert RiskSnapshot.query.count() == 2


def test_a_pending_student_can_be_recorded(teacher_client, build):
    course, student = owned_course_with_student(build)
    teacher_client.post(record_url(course, student))
    snapshot = RiskSnapshot.query.one()
    assert snapshot.classification == "Pending" and snapshot.overall_risk_score is None


# ------------------------------------------------ access control: whole course
def test_anonymous_cannot_record_for_the_whole_course(client, build):
    course = build.course(teacher=my_teacher())
    assert client.post(bulk_url(course)).status_code == 302


def test_administrator_cannot_record_for_the_whole_course(admin_client, build):
    course = build.course(teacher=build.teacher())
    assert admin_client.post(bulk_url(course)).status_code == 403


def test_teacher_cannot_record_for_another_teachers_whole_course(teacher_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    assert teacher_client.post(bulk_url(course)).status_code == 403
    assert RiskSnapshot.query.count() == 0


def test_whole_course_recording_for_unknown_course_is_404(teacher_client):
    assert teacher_client.post("/teacher/courses/99999/risk-report/record").status_code == 404


def test_whole_course_url_does_not_accept_get(teacher_client, build):
    course = build.course(teacher=my_teacher())
    assert teacher_client.get(bulk_url(course)).status_code == 405


def test_owner_records_every_enrolled_student_and_nobody_else(teacher_client, build):
    teacher = my_teacher()
    course, other_course = build.course(teacher=teacher), build.course(teacher=teacher)
    enrolled = [build.student(), build.student()]
    outsider = build.student()
    for student in enrolled:
        build.enrol(student, course)
    build.enrol(outsider, other_course)

    response = teacher_client.post(bulk_url(course), follow_redirects=True)

    assert b"Recorded 2 new risk assessment" in response.data
    assert RiskSnapshot.query.filter_by(course_id=course.id).count() == 2
    assert RiskSnapshot.query.filter_by(student_id=outsider.id).count() == 0


def test_whole_course_recording_twice_reports_unchanged(teacher_client, build):
    course, _student = owned_course_with_student(build)
    teacher_client.post(bulk_url(course))
    response = teacher_client.post(bulk_url(course), follow_redirects=True)
    assert b"Recorded 0 new risk assessment" in response.data
    assert RiskSnapshot.query.count() == 1


def test_whole_course_recording_with_no_students_says_so(teacher_client, build):
    course = build.course(teacher=my_teacher())
    response = teacher_client.post(bulk_url(course), follow_redirects=True)
    assert b"No students are enrolled" in response.data
    assert RiskSnapshot.query.count() == 0


def test_risk_report_shows_the_record_button_only_with_students(teacher_client, build):
    empty_course = build.course(teacher=my_teacher())
    text = teacher_client.get(f"/teacher/courses/{empty_course.id}/risk-report").get_data(as_text=True)
    assert "Record Risk Assessments" not in text

    course, _student = owned_course_with_student(build)
    text = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    assert "Record Risk Assessments" in text
    assert bulk_url(course) in text


# ---------------------------------------------- the Risk History section
def test_detail_page_shows_the_empty_history_state(teacher_client, build):
    course, student = owned_course_with_student(build)
    text = page_text(teacher_client, course, student)
    assert "Risk History" in text
    assert "No risk assessments have been recorded yet" in text
    assert "Record Risk Assessment" in text
    assert record_url(course, student) in text
    assert "chart.umd.min.js" not in text                  # no chart without history


def test_existing_current_risk_sections_are_still_present(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    text = page_text(teacher_client, course, student)
    for heading in ("Attendance Breakdown", "Assessment Marks", "Assignment Status",
                    "Risk Calculation", "Risk Explanations", "Recommended Interventions"):
        assert heading in text


def test_history_table_lists_recorded_assessments(teacher_client, build):
    course, student = owned_course_with_student(build)
    make_snapshot(student, course, score=50.0, classification="Medium Risk",
                  attendance_percentage=60.0, recorded_at=datetime(2026, 11, 1, 10, 30))
    make_snapshot(student, course, score=20.0, classification="Low Risk",
                  attendance_percentage=80.0, recorded_at=datetime(2026, 11, 15, 14, 45))

    text = page_text(teacher_client, course, student)

    assert "Recorded assessments" in text
    assert "01 Nov 2026 10:30" in text and "15 Nov 2026 14:45" in text
    assert text.index("15 Nov 2026 14:45") < text.index("01 Nov 2026 10:30")     # newest first
    assert "First assessment" in text
    assert "chart.umd.min.js" in text and "riskTrendChart" in text
    assert "indicatorTrendChart" in text


def test_unavailable_values_are_shown_as_unavailable_not_zero(teacher_client, build):
    course, student = owned_course_with_student(build)
    make_snapshot(student, course, score=40.0, classification="Medium Risk",
                  attendance_percentage=0.0, performance_percentage=None)
    text = page_text(teacher_client, course, student)
    assert "0.0%" in text                                   # the real zero
    assert "Unavailable" in text                            # the missing indicator


def test_pending_snapshot_is_shown_as_pending(teacher_client, build):
    course, student = owned_course_with_student(build)
    make_snapshot(student, course, score=None, classification="Pending")
    text = page_text(teacher_client, course, student)
    assert "Recorded assessments" in text and "Pending" in text


def test_lower_score_than_last_snapshot_is_shown_as_improved(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)                  # live score 8.0
    make_snapshot(student, course, score=50.0, classification="Medium Risk",
                  recorded_at=datetime(2026, 11, 1, 9, 0))
    text = page_text(teacher_client, course, student)
    assert "Improved (risk decreased)" in text
    assert "-42.0" in text                                 # 8.0 - 50.0
    assert "Medium Risk" in text and "Low Risk" in text


def test_higher_score_than_last_snapshot_is_shown_as_deteriorated(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)                  # live score 8.0
    make_snapshot(student, course, score=2.0, classification="Low Risk",
                  recorded_at=datetime(2026, 11, 1, 9, 0))
    text = page_text(teacher_client, course, student)
    assert "Deteriorated (risk increased)" in text
    assert "+6.0" in text


def test_same_score_as_last_snapshot_is_shown_as_unchanged(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    RiskHistoryService.record_snapshot(student.id, course.id, my_teacher().id)
    text = page_text(teacher_client, course, student)
    assert "Unchanged" in text
    assert "Improved (risk decreased)" not in text
    assert "Deteriorated (risk increased)" not in text


def test_no_claim_is_made_when_current_risk_is_pending(teacher_client, build):
    course, student = owned_course_with_student(build)     # live: Pending (no data)
    make_snapshot(student, course, score=40.0, classification="Medium Risk")
    text = page_text(teacher_client, course, student)
    assert "Not enough comparable data" in text
    assert "Improved (risk decreased)" not in text
    assert "Deteriorated (risk increased)" not in text


def test_indicator_trends_use_higher_is_better(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)                  # live attendance 75, perf 50, assign 60
    make_snapshot(student, course, score=30.0, classification="Medium Risk",
                  attendance_percentage=50.0, performance_percentage=70.0,
                  assignment_percentage=60.0)
    text = page_text(teacher_client, course, student)
    assert "Improving" in text                              # attendance 50 -> 75
    assert "Declining" in text                              # performance 70 -> 50
    assert "Stable" in text                                 # assignments 60 -> 60


def test_stored_explanations_are_html_escaped(teacher_client, build):
    course, student = owned_course_with_student(build)
    make_snapshot(student, course, explanations_json='["<script>alert(1)</script>"]')
    text = page_text(teacher_client, course, student)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "<script>alert(1)</script>" not in text


def test_chart_data_marks_unavailable_values_as_null(teacher_client, build):
    course, student = owned_course_with_student(build)
    make_snapshot(student, course, score=None, classification="Pending")
    text = page_text(teacher_client, course, student)
    match = re.search(r"var riskHistory = (\{.*?\});", text, re.S)
    assert match, "chart data not found"
    assert '"overall": [null]' in match.group(1) or '"overall":[null]' in match.group(1)


def test_page_history_rows_do_not_change_after_data_is_edited(teacher_client, build):
    course, student = owned_course_with_student(build)
    add_full_data(build, student, course)
    RiskHistoryService.record_snapshot(student.id, course.id, my_teacher().id)
    before = RiskSnapshot.query.one().overall_risk_score

    build.attendance(student, course, date(2026, 11, 20), "Absent")        # live data changes
    page_text(teacher_client, course, student)

    db.session.expire_all()
    assert RiskSnapshot.query.one().overall_risk_score == before


# -------------------------------------------- data leakage and authorization
def test_history_of_one_course_is_not_shown_in_another(teacher_client, build):
    teacher = my_teacher()
    course_a, course_b = build.course(teacher=teacher), build.course(teacher=teacher)
    student = build.student()
    build.enrol(student, course_a)
    build.enrol(student, course_b)
    make_snapshot(student, course_a, score=33.0, classification="Medium Risk",
                  recorded_at=datetime(2026, 11, 3, 8, 15))

    text = page_text(teacher_client, course_b, student)
    assert "No risk assessments have been recorded yet" in text
    assert "03 Nov 2026 08:15" not in text


def test_history_page_is_forbidden_for_another_teachers_course(teacher_client, build):
    other = build.teacher()
    course = build.course(teacher=other)
    student = build.student(name="Leak Check Student")
    build.enrol(student, course)
    make_snapshot(student, course, recorded_by=other, recorded_at=datetime(2026, 11, 3, 8, 15))
    response = teacher_client.get(detail_url(course, student))
    assert response.status_code == 403
    assert b"Leak Check Student" not in response.data
    assert b"03 Nov 2026" not in response.data


def test_history_page_for_unenrolled_student_is_404_even_with_old_snapshots(teacher_client, build):
    course, student = owned_course_with_student(build)
    make_snapshot(student, course)
    Enrolment.query.filter_by(student_id=student.id, course_id=course.id).delete()
    db.session.commit()
    assert teacher_client.get(detail_url(course, student)).status_code == 404


def test_administrator_cannot_view_history_page(admin_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    assert admin_client.get(detail_url(course, student)).status_code == 403


# ---------------------------------------------- admin deletion guards
def test_admin_cannot_delete_a_student_who_has_risk_history(admin_client, build):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    student = build.student()
    make_snapshot(student, course, recorded_by=teacher)     # no enrolment, only history

    response = admin_client.post(f"/admin/students/{student.id}/delete", follow_redirects=True)

    assert b"Cannot delete" in response.data
    assert b"risk history snapshots" in response.data
    assert Student.query.count() == 1 and RiskSnapshot.query.count() == 1


def test_admin_cannot_delete_a_course_that_has_risk_history(admin_client, build):
    teacher = build.teacher()
    course = build.course(teacher=teacher)
    student = build.student()
    make_snapshot(student, course, recorded_by=teacher)

    response = admin_client.post(f"/admin/courses/{course.id}/delete", follow_redirects=True)

    assert b"Cannot delete" in response.data
    assert Course.query.count() == 1 and RiskSnapshot.query.count() == 1


# ------------------------------------------------------------------- CSRF
@pytest.fixture()
def csrf_history_env():
    """An app with CSRF ON, one teacher who owns a course with one enrolled student."""
    class CsrfOnConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfOnConfig)
    with app.app_context():
        db.create_all()
        teacher = User(full_name="CSRF Teacher", email="csrfteacher@test.local", role=ROLE_TEACHER)
        teacher.set_password("CsrfPass123")
        db.session.add(teacher)
        db.session.commit()
        course = Course(code="CSRF1", name="CSRF Course", teacher_id=teacher.id)
        student = Student(student_id="S900", name="CSRF Student",
                          email="s900@test.local", semester="Semester 3")
        db.session.add_all([course, student])
        db.session.commit()
        db.session.add(Enrolment(student_id=student.id, course_id=course.id))
        db.session.commit()
        yield app, course.id, student.id
        db.session.remove()
        db.drop_all()


def _csrf_token(client, url):
    html = client.get(url).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "no CSRF token on " + url
    return match.group(1)


def _log_in(client):
    token = _csrf_token(client, "/login")
    response = client.post("/login", data={"email": "csrfteacher@test.local",
                                           "password": "CsrfPass123", "csrf_token": token})
    assert response.status_code == 302


def test_recording_without_a_csrf_token_is_refused(csrf_history_env):
    app, course_id, student_id = csrf_history_env
    client = app.test_client()
    _log_in(client)

    refused = client.post(f"/teacher/courses/{course_id}/students/{student_id}/risk/record")

    assert refused.status_code == 400
    assert RiskSnapshot.query.count() == 0


def test_recording_with_a_csrf_token_works(csrf_history_env):
    app, course_id, student_id = csrf_history_env
    client = app.test_client()
    _log_in(client)
    detail = f"/teacher/courses/{course_id}/students/{student_id}/risk"
    token = _csrf_token(client, detail)                    # token from the record form

    accepted = client.post(detail + "/record", data={"csrf_token": token})

    assert accepted.status_code == 302
    assert RiskSnapshot.query.count() == 1


def test_whole_course_recording_without_a_csrf_token_is_refused(csrf_history_env):
    app, course_id, _student_id = csrf_history_env
    client = app.test_client()
    _log_in(client)
    assert client.post(f"/teacher/courses/{course_id}/risk-report/record").status_code == 400
    assert RiskSnapshot.query.count() == 0


def test_record_forms_carry_a_csrf_token(csrf_history_env):
    app, course_id, student_id = csrf_history_env
    client = app.test_client()
    _log_in(client)
    html = client.get(f"/teacher/courses/{course_id}/students/{student_id}/risk").get_data(as_text=True)
    form = re.search(r'<form[^>]*risk/record.*?</form>', html, re.S)
    assert form and 'name="csrf_token"' in form.group(0)
