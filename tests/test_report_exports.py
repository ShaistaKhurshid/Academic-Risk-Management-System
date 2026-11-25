"""Phase 13: PDF and Excel exports (course PDF, course Excel, student PDF).

Remember (see conftest.py): use only ONE logged-in client per test.
Every test uses real generated files: PDFs are read back with pypdf and the
workbook is re-opened with OpenPyXL.
"""
import re
from datetime import date, datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook
from pypdf import PdfReader

from app import db
from app.models import (Attendance, Assessment, Assignment, AssignmentSubmission,
                        Enrolment, RiskSnapshot, Student, StudentAssessment, User)
from app.services import report_export_service as exports
from app.services.risk_history_service import RiskHistoryService


# ------------------------------------------------------------------ helpers
def my_teacher():
    return User.query.filter_by(email="teacher@test.local").first()


def course_pdf_url(course):
    return f"/teacher/courses/{course.id}/risk-report/export.pdf"


def course_xlsx_url(course):
    return f"/teacher/courses/{course.id}/risk-report/export.xlsx"


def student_pdf_url(course, student):
    return f"/teacher/courses/{course.id}/students/{student.id}/risk/export.pdf"


def pdf_pages(response):
    reader = PdfReader(BytesIO(response.data))
    return [page.extract_text() or "" for page in reader.pages]


def pdf_text(response):
    return "\n".join(pdf_pages(response))


def workbook(response):
    return load_workbook(BytesIO(response.data))


def full_assignments(build, course, student, statuses):
    """Create the five compulsory assignments with the given statuses (None = no record)."""
    for number, status in enumerate(statuses, start=1):
        assignment = build.assignment(course, title=f"Assignment {number}")
        if status is not None:
            build.submission(assignment, student, status)


def make_course(build):
    """A course owned by the logged-in teacher with three very different students:

    Alice  - full data: attendance 3/4 = 75.0%, marks 15/20 = 75.0%, assignments 4/5 = 80.0%
    Bob    - nothing recorded at all  -> Pending
    Carol  - only attendance (1/2 = 50.0%) -> partial data
    """
    course = build.course(teacher=my_teacher(), code="CS201", name="Data Structures")
    quiz = build.assessment(course, max_marks=20, title="Quiz 1")
    mid = build.assessment(course, max_marks=50, title="Midterm")   # nobody graded

    alice = build.student(student_id="S001", name="Alice Anand")
    bob = build.student(student_id="S002", name="Bob Bose")
    carol = build.student(student_id="S003", name="Carol Das")
    for student in (alice, bob, carol):
        build.enrol(student, course)

    for day, status in enumerate(["Present", "Present (Late)", "Present", "Absent"], 1):
        build.attendance(alice, course, day=date(2026, 11, day), status=status)
    build.marks(quiz, alice, 15)
    full_assignments(build, course, alice,
                     ["Submitted", "Late Submission", "Submitted", "Excused", "Submitted"])

    build.attendance(carol, course, day=date(2026, 11, 1), status="Present")
    build.attendance(carol, course, day=date(2026, 11, 2), status="Absent")
    return course, alice, bob, carol, mid


ZERO_PERCENT = re.compile(r"(?<![\d.])0\.0%")


# =========================================================================
# 1. Course Risk Report - PDF
# =========================================================================
def test_course_pdf_is_generated_with_correct_headers(teacher_client, build):
    course, *_ = make_course(build)
    response = teacher_client.get(course_pdf_url(course))
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 1500
    disposition = response.headers["Content-Disposition"]
    assert "attachment" in disposition
    assert re.search(r"course_risk_report_CS201_\d{8}\.pdf", disposition)
    assert response.headers["Cache-Control"] == "no-store"


def test_course_pdf_contains_heading_course_summary_and_students(teacher_client, build):
    course, *_ = make_course(build)
    text = pdf_text(teacher_client.get(course_pdf_url(course)))
    assert "Academic Risk Management System" in text
    assert "Course Risk Report" in text
    assert "Generated on" in text
    assert "Data Structures" in text and "CS201" in text
    assert "Total enrolled" in text
    for label in ("Low Risk", "Medium Risk", "High Risk", "Pending"):
        assert label in text
    for name, sid in (("Alice Anand", "S001"), ("Bob Bose", "S002"), ("Carol Das", "S003")):
        assert name in text and sid in text
    assert "75.0%" in text                      # Alice's attendance
    assert "Page 1 of 1" in text


def test_course_pdf_includes_explanations_and_interventions(teacher_client, build):
    course, *_ = make_course(build)
    text = pdf_text(teacher_client.get(course_pdf_url(course)))
    assert "Risk explanations and recommended interventions" in text
    assert "Recommended interventions" in text


def test_course_pdf_pending_and_partial_students_never_show_zero(teacher_client, build):
    course, *_ = make_course(build)
    text = pdf_text(teacher_client.get(course_pdf_url(course)))
    assert "Pending" in text
    assert not ZERO_PERCENT.search(text)
    assert "Unavailable indicators" in text


def test_course_pdf_empty_course_does_not_crash(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="EMPTY1")
    response = teacher_client.get(course_pdf_url(course))
    assert response.status_code == 200
    assert "No students are enrolled" in pdf_text(response)


def test_course_pdf_multiple_pages_repeat_header_and_number_pages(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="BIG1")
    for index in range(70):
        student = build.student(student_id=f"B{index:04d}", name=f"Big Student {index:02d}")
        build.enrol(student, course)
    response = teacher_client.get(course_pdf_url(course))
    pages = pdf_pages(response)
    assert len(pages) >= 2
    assert f"Page 1 of {len(pages)}" in pages[0]
    assert f"Page {len(pages)} of {len(pages)}" in pages[-1]
    # the table header repeats on the second page
    assert "Student ID" in pages[1] or "Student name" in pages[1]
    assert "Student name" in pages[1]


def test_course_pdf_odd_characters_in_names_do_not_crash(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="ODD1")
    for sid, name in (("O1", "Tom <b>&</b> Jerry"), ("O2", "Priya प्रिया")):
        build.enrol(build.student(student_id=sid, name=name), course)
    response = teacher_client.get(course_pdf_url(course))
    assert response.status_code == 200
    assert "Tom <b>&</b> Jerry" in pdf_text(response)


# =========================================================================
# 2. Course Risk Report - Excel
# =========================================================================
def sheet_rows(response):
    sheet = workbook(response)[exports.EXCEL_SHEET_NAME]
    return [[cell.value for cell in row] for row in sheet.iter_rows()]


def test_course_excel_download_response(teacher_client, build):
    course, *_ = make_course(build)
    response = teacher_client.get(course_xlsx_url(course))
    assert response.status_code == 200
    assert response.mimetype == exports.XLSX_MIME
    assert re.search(r"course_risk_report_CS201_\d{8}\.xlsx",
                     response.headers["Content-Disposition"])
    assert response.data[:2] == b"PK"            # xlsx is a zip file


def test_course_excel_sheet_headers_filter_and_frozen_row(teacher_client, build):
    course, *_ = make_course(build)
    wb = workbook(teacher_client.get(course_xlsx_url(course)))
    assert "Course Risk Report" in wb.sheetnames
    assert wb.active.title == "Course Risk Report"
    sheet = wb["Course Risk Report"]
    headers = [cell.value for cell in sheet[1]]
    assert headers == [title for title, _width in exports.EXCEL_HEADERS]
    for expected in ("Student ID", "Student Name", "Course Code", "Course Name",
                     "Attendance (%)", "Academic Performance (%)",
                     "Assignment Completion (%)", "Overall Risk Score",
                     "Risk Classification", "Risk Explanations",
                     "Recommended Interventions"):
        assert expected in headers
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:L4"
    assert all(sheet.column_dimensions[c].width > 8 for c in "ABCDEFGHIJKL")


def test_course_excel_values_are_correct(teacher_client, build):
    course, *_ = make_course(build)
    rows = sheet_rows(teacher_client.get(course_xlsx_url(course)))
    by_id = {row[0]: row for row in rows[1:]}
    alice = by_id["S001"]
    assert alice[1] == "Alice Anand"
    assert alice[2:4] == ["CS201", "Data Structures"]
    assert alice[4] == 75.0 and alice[5] == 75.0 and alice[6] == 80.0
    # 40% / 40% / 20% weights: attendance risk 0, performance risk 0, assignment risk 20
    assert abs(alice[7] - 4.0) < 0.01
    assert alice[8] == "Low Risk"
    assert alice[9] == "None"
    assert alice[10] and alice[11]


def test_course_excel_null_indicators_and_pending_are_not_zero(teacher_client, build):
    course, *_ = make_course(build)
    rows = sheet_rows(teacher_client.get(course_xlsx_url(course)))
    by_id = {row[0]: row for row in rows[1:]}
    bob = by_id["S002"]
    assert bob[4:9] == ["Pending", "Pending", "Pending", "Pending", "Pending"]
    assert all(value != 0 for value in bob[4:8])
    assert "Attendance" in bob[9] and "Assignment completion" in bob[9]
    carol = by_id["S003"]
    assert carol[4] == 50.0                       # attendance is available
    assert carol[5] == "Pending" and carol[6] == "Pending"
    assert isinstance(carol[7], float) and carol[8] != "Pending"
    assert carol[9] == "Academic performance, Assignment completion"


def test_course_excel_has_no_extra_rows_or_columns_and_number_format(teacher_client, build):
    course, *_ = make_course(build)
    wb = workbook(teacher_client.get(course_xlsx_url(course)))
    sheet = wb["Course Risk Report"]
    assert sheet.max_row == 4                      # header + 3 students
    assert sheet.max_column == len(exports.EXCEL_HEADERS)
    assert sheet["E2"].number_format == "0.0"
    assert sheet["H2"].number_format == "0.0"


def test_course_excel_summary_sheet_counts(teacher_client, build):
    course, *_ = make_course(build)
    wb = workbook(teacher_client.get(course_xlsx_url(course)))
    summary = {row[0].value: row[1].value for row in wb["Summary"].iter_rows()}
    assert summary["Total enrolled students"] == 3
    assert summary["Pending"] == 1
    assert summary["Low Risk"] + summary["Medium Risk"] + summary["High Risk"] + summary["Pending"] == 3
    assert summary["Course name"] == "Data Structures"


def test_course_excel_empty_course_has_only_header(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="EMPTY2")
    response = teacher_client.get(course_xlsx_url(course))
    assert response.status_code == 200
    sheet = workbook(response)["Course Risk Report"]
    assert sheet.max_row == 1
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref


def test_course_excel_text_that_looks_like_a_formula_stays_text(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="INJ1")
    build.enrol(build.student(student_id="F1", name="=1+1"), course)
    sheet = workbook(teacher_client.get(course_xlsx_url(course)))["Course Risk Report"]
    assert sheet["B2"].value == "=1+1"
    assert sheet["B2"].data_type == "s"


# =========================================================================
# 3. Individual Student Risk Report - PDF
# =========================================================================
def test_student_pdf_is_generated_with_correct_headers(teacher_client, build):
    course, alice, *_ = make_course(build)
    response = teacher_client.get(student_pdf_url(course, alice))
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF") and len(response.data) > 1500
    assert re.search(r"student_risk_report_CS201_S001_\d{8}\.pdf",
                     response.headers["Content-Disposition"])


def test_student_pdf_contains_all_sections_and_values(teacher_client, build):
    course, alice, *_ = make_course(build)
    text = pdf_text(teacher_client.get(student_pdf_url(course, alice)))
    for expected in ("Individual Student Risk Report", "Alice Anand", "S001",
                     "Data Structures", "CS201", "Current risk assessment",
                     "Overall risk score", "Low Risk", "Attendance details",
                     "Assessment details", "Assignment details", "Risk analysis",
                     "Risk explanations", "Recommended interventions",
                     "Unavailable indicators", "Historical risk progression",
                     "Weight used", "Contribution"):
        assert expected in text, expected
    assert "Sessions recorded: 4" in text
    assert "Present (Late)" in text and "Absent" in text
    assert "75.0%" in text and "80.0%" in text


def test_student_pdf_null_marks_are_not_graded_and_statuses_are_preserved(teacher_client, build):
    course, alice, *_ = make_course(build)
    text = pdf_text(teacher_client.get(student_pdf_url(course, alice)))
    assert "Quiz 1" in text and "Midterm" in text
    assert "Not graded" in text                    # Midterm has no marks
    assert "15" in text and "20" in text
    for status in ("Submitted", "Late Submission", "Excused"):
        assert status in text
    assert "Excused count as incomplete" in text
    assert "Late Submission count as completed" in text


def test_student_pdf_explicit_null_marks_row_is_not_graded_never_zero(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="NULL1")
    student = build.student(student_id="N1", name="Nina Null")
    build.enrol(student, course)
    build.marks(build.assessment(course, max_marks=30, title="Lab Test"), student, None)
    text = pdf_text(teacher_client.get(student_pdf_url(course, student)))
    assert "Lab Test" in text and "Not graded" in text
    assert not ZERO_PERCENT.search(text)


def test_student_pdf_pending_student_with_no_data(teacher_client, build):
    course, _alice, bob, *_ = make_course(build)
    response = teacher_client.get(student_pdf_url(course, bob))
    assert response.status_code == 200
    text = pdf_text(response)
    assert "Pending" in text and "Unavailable" in text
    assert "No attendance has been recorded" in text
    assert not ZERO_PERCENT.search(text)


def test_student_pdf_missing_assignment_record_is_no_record(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="NOREC")
    student = build.student(student_id="NR1", name="Nora Norecord")
    build.enrol(student, course)
    full_assignments(build, course, student, ["Submitted", None, None, None, None])
    text = pdf_text(teacher_client.get(student_pdf_url(course, student)))
    assert "No record" in text
    assert "Assignment Pending" in text


def test_student_pdf_without_history_shows_clear_message(teacher_client, build):
    course, alice, *_ = make_course(build)
    text = pdf_text(teacher_client.get(student_pdf_url(course, alice)))
    assert "No historical risk assessments have been recorded" in text


def test_student_pdf_with_history_shows_progression(teacher_client, build):
    course, alice, *_ = make_course(build)
    teacher = my_teacher()
    RiskHistoryService.record_snapshot(alice.id, course.id, teacher.id)
    # Alice then misses another class: attendance drops, risk rises.
    build.attendance(alice, course, day=date(2026, 11, 10), status="Absent")
    build.attendance(alice, course, day=date(2026, 11, 11), status="Absent")
    response = teacher_client.get(student_pdf_url(course, alice))
    text = pdf_text(response)
    assert "Historical risk progression" in text
    assert "Previous score" in text and "Current score" in text and "Difference" in text
    assert "Deteriorated" in text
    assert "Snapshot history (1 recorded" in text
    assert datetime.now().strftime("%d %b %Y") in text
    assert "Last recorded" in text and "Trend" in text


def test_student_pdf_improved_direction(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="IMP1")
    student = build.student(student_id="IM1", name="Ian Improver")
    build.enrol(student, course)
    build.attendance(student, course, day=date(2026, 11, 1), status="Absent")
    RiskHistoryService.record_snapshot(student.id, course.id, my_teacher().id)
    for day in (2, 3, 4):
        build.attendance(student, course, day=date(2026, 11, day), status="Present")
    text = pdf_text(teacher_client.get(student_pdf_url(course, student)))
    assert "Improved" in text


def test_student_pdf_pending_comparison_claims_no_direction(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="PEND1")
    student = build.student(student_id="PE1", name="Pat Pending")
    build.enrol(student, course)
    RiskHistoryService.record_snapshot(student.id, course.id, my_teacher().id)  # Pending snapshot
    text = pdf_text(teacher_client.get(student_pdf_url(course, student)))
    assert "Not enough comparable data" in text
    assert "Improved" not in text and "Deteriorated" not in text


def test_student_pdf_long_attendance_spans_pages(teacher_client, build):
    course = build.course(teacher=my_teacher(), code="LONG1")
    student = build.student(student_id="L1", name="Long Attendance")
    build.enrol(student, course)
    start = date(2026, 1, 1)
    for index in range(90):
        build.attendance(student, course, day=start + timedelta(days=index),
                         status="Present" if index % 3 else "Absent")
    pages = pdf_pages(teacher_client.get(student_pdf_url(course, student)))
    assert len(pages) >= 2
    assert "Session date" in pages[1]               # header repeats


# =========================================================================
# Security
# =========================================================================
def all_export_urls(course, student):
    return [course_pdf_url(course), course_xlsx_url(course), student_pdf_url(course, student)]


def test_anonymous_users_are_redirected_to_login(client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    for url in all_export_urls(course, student):
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/login" in response.headers["Location"]


def test_administrator_cannot_export(admin_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    for url in all_export_urls(course, student):
        assert admin_client.get(url).status_code == 403, url


def test_teacher_cannot_export_another_teachers_course(teacher_client, build):
    course = build.course(teacher=build.teacher(), code="OTHER1")
    student = build.student(student_id="SECRET1", name="Secret Student")
    build.enrol(student, course)
    for url in all_export_urls(course, student):
        response = teacher_client.get(url)
        assert response.status_code == 403, url
        assert b"Secret Student" not in response.data
        assert b"%PDF" not in response.data[:5]


def test_course_without_a_teacher_cannot_be_exported(teacher_client, build):
    course = build.course(teacher=None)
    assert teacher_client.get(course_pdf_url(course)).status_code == 403
    assert teacher_client.get(course_xlsx_url(course)).status_code == 403


def test_invalid_course_ids_give_404(teacher_client):
    assert teacher_client.get("/teacher/courses/99999/risk-report/export.pdf").status_code == 404
    assert teacher_client.get("/teacher/courses/99999/risk-report/export.xlsx").status_code == 404
    assert teacher_client.get("/teacher/courses/99999/students/1/risk/export.pdf").status_code == 404
    assert teacher_client.get("/teacher/courses/abc/risk-report/export.pdf").status_code == 404


def test_student_must_be_enrolled_in_the_requested_course(teacher_client, build):
    teacher = my_teacher()
    course_a = build.course(teacher=teacher)
    course_b = build.course(teacher=teacher)          # also owned by this teacher
    student = build.student(name="Only In B")
    build.enrol(student, course_b)
    assert teacher_client.get(student_pdf_url(course_a, student)).status_code == 404
    assert teacher_client.get(student_pdf_url(course_b, student)).status_code == 200


def test_unknown_student_gives_404(teacher_client, build):
    course = build.course(teacher=my_teacher())
    assert teacher_client.get(f"/teacher/courses/{course.id}/students/99999/risk/export.pdf").status_code == 404


def test_export_routes_are_get_only(teacher_client, build):
    course, alice, *_ = make_course(build)
    for url in all_export_urls(course, alice):
        assert teacher_client.post(url).status_code == 405, url


def test_existing_pages_still_enforce_ownership(teacher_client, build):
    course = build.course(teacher=build.teacher())
    student = build.student()
    build.enrol(student, course)
    assert teacher_client.get(f"/teacher/courses/{course.id}/risk-report").status_code == 403
    assert teacher_client.get(f"/teacher/courses/{course.id}/students/{student.id}/risk").status_code == 403


# =========================================================================
# Read-only guarantee
# =========================================================================
def table_counts():
    db.session.expire_all()
    return tuple(model.query.count() for model in (
        RiskSnapshot, Attendance, Assessment, StudentAssessment, Assignment,
        AssignmentSubmission, Student, Enrolment))


def test_exports_do_not_modify_data_or_create_snapshots(teacher_client, build):
    course, alice, *_ = make_course(build)
    RiskHistoryService.record_snapshot(alice.id, course.id, my_teacher().id)
    before = table_counts()
    snapshot_before = [(s.id, s.recorded_at, s.overall_risk_score)
                       for s in RiskSnapshot.query.order_by(RiskSnapshot.id)]
    for url in all_export_urls(course, alice) * 2:
        assert teacher_client.get(url).status_code == 200
    assert table_counts() == before
    assert [(s.id, s.recorded_at, s.overall_risk_score)
            for s in RiskSnapshot.query.order_by(RiskSnapshot.id)] == snapshot_before


# =========================================================================
# Buttons and regression of the existing pages
# =========================================================================
def test_risk_report_page_has_export_buttons_and_is_unchanged_otherwise(teacher_client, build):
    course, *_ = make_course(build)
    page = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").data.decode()
    assert "Export PDF" in page and "Export Excel" in page
    assert course_pdf_url(course) in page and course_xlsx_url(course) in page
    assert "Record Risk Assessments" in page
    assert "Student Academic Risk Summary" in page
    assert "Alice Anand" in page and "riskDistributionChart" in page


def test_risk_report_page_counts_match_the_exports(teacher_client, build):
    course, *_ = make_course(build)
    page = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").data.decode()
    assert "Total Students" in page
    wb = workbook(teacher_client.get(course_xlsx_url(course)))
    summary = {row[0].value: row[1].value for row in wb["Summary"].iter_rows()}
    assert summary["Total enrolled students"] == 3
    # three students listed on the page, and three rows in the workbook
    assert page.count('class="fw-bold text-decoration-none"') == 3


def test_empty_course_page_has_no_export_buttons(teacher_client, build):
    course = build.course(teacher=my_teacher())
    page = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").data.decode()
    assert "No students are enrolled" in page
    assert "Export PDF" not in page


def test_student_detail_page_has_download_button_and_history_still_works(teacher_client, build):
    course, alice, *_ = make_course(build)
    page = teacher_client.get(f"/teacher/courses/{course.id}/students/{alice.id}/risk").data.decode()
    assert "Download Student PDF" in page
    assert student_pdf_url(course, alice) in page
    assert "Risk History" in page and "Record Risk Assessment" in page


# =========================================================================
# Service helpers
# =========================================================================
def test_safe_filename_part_removes_unsafe_characters():
    assert exports.safe_filename_part("CS 201/../x") == "CS_201_x"
    cleaned = exports.safe_filename_part('A b/c\\d"e;f\r\n')
    assert re.fullmatch(r"[A-Za-z0-9_-]+", cleaned)
    assert exports.safe_filename_part("") == "report"
    assert exports.safe_filename_part(None) == "report"


def test_download_filename_is_safe_for_strange_course_codes(teacher_client, build):
    course = build.course(teacher=my_teacher(), code='X/Y "Z"')
    response = teacher_client.get(course_pdf_url(course))
    assert response.status_code == 200
    assert 'course_risk_report_X_Y_Z_' in response.headers["Content-Disposition"]
