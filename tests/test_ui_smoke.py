"""Phase 14: UI / UX smoke tests.

These check structure and safety of the new interface (navigation, accessibility
hooks, risk badges, the Pending card, details still reachable). They do NOT test
business logic: that is covered by the existing test files.
"""
import re
from datetime import date

from app.models import User


def my_teacher():
    return User.query.filter_by(email="teacher@test.local").first()


def sidebar_hrefs(html):
    """Every link inside the main-navigation <nav>."""
    nav = re.search(r'<nav id="sidebarNav".*?</nav>', html, re.S).group(0)
    return re.findall(r'href="([^"]+)"', nav)


def flagged_course(build):
    """Course with one High-risk, one Low-risk and one Pending student."""
    course = build.course(teacher=my_teacher(), code="UI101", name="Interface Design")
    high, low, pending = (build.student(student_id="H1", name="Hugo High"),
                          build.student(student_id="L1", name="Lena Low"),
                          build.student(student_id="P1", name="Pia Pending"))
    for student in (high, low, pending):
        build.enrol(student, course)
    build.attendance(high, course, date(2026, 11, 1), "Present")
    for day in (2, 3, 4):
        build.attendance(high, course, date(2026, 11, day), "Absent")
    for day in (1, 2, 3, 4):
        build.attendance(low, course, date(2026, 11, day), "Present")
    return course, high, low, pending


# ---------------------------------------------------------------- navigation
def test_teacher_sidebar_links_all_work_and_belong_to_the_teacher(teacher_client, build):
    mine = build.course(teacher=my_teacher(), code="MINE1", name="Mine")
    other = build.course(teacher=build.teacher(), code="THEIRS9", name="Theirs")
    html = teacher_client.get("/teacher/dashboard").get_data(as_text=True)
    assert "MINE1" in html and "THEIRS9" not in html
    hrefs = sidebar_hrefs(html)
    assert f"/teacher/courses/{mine.id}/risk-report" in hrefs
    assert not any(f"/courses/{other.id}/" in href for href in hrefs)
    assert len(hrefs) == 1 + 4                      # dashboard + 4 links for the one course
    for href in hrefs:
        assert teacher_client.get(href).status_code == 200, href


def test_admin_sidebar_links_all_work_and_has_no_placeholders(admin_client):
    html = admin_client.get("/admin/dashboard").get_data(as_text=True)
    hrefs = sidebar_hrefs(html)
    assert len(hrefs) == 4
    for href in hrefs:
        assert admin_client.get(href).status_code == 200, href
    assert "disabled" not in re.search(r'<nav id="sidebarNav".*?</nav>', html, re.S).group(0)


def test_no_developer_milestone_text_on_dashboards(admin_client):
    html = admin_client.get("/admin/dashboard").get_data(as_text=True)
    assert "Milestone" not in html


def test_teacher_dashboard_has_no_milestone_text_and_course_cards(teacher_client, build):
    build.course(teacher=my_teacher(), code="CARD1", name="Card Course")
    html = teacher_client.get("/teacher/dashboard").get_data(as_text=True)
    assert "Milestone" not in html
    for label in ("View Risk Report", "Manage Attendance", "Manage Assessments",
                  "Manage Assignments", "CARD1", "Card Course"):
        assert label in html


def test_teacher_dashboard_empty_state_kept(teacher_client):
    html = teacher_client.get("/teacher/dashboard").get_data(as_text=True)
    assert "No courses are assigned to you yet" in html


def test_sidebar_marks_the_current_page(teacher_client, build):
    course = build.course(teacher=my_teacher())
    html = teacher_client.get(f"/teacher/courses/{course.id}/attendance").get_data(as_text=True)
    assert html.count('aria-current="page"') >= 1
    assert re.search(r'class="nav-link active"[^>]*aria-current="page">Attendance<', html)


# ------------------------------------------------------------- accessibility
def test_pages_have_skip_link_main_landmark_and_single_h1(teacher_client, build):
    course, high, *_ = flagged_course(build)
    for url in ("/teacher/dashboard",
                f"/teacher/courses/{course.id}/risk-report",
                f"/teacher/courses/{course.id}/students/{high.id}/risk",
                f"/teacher/courses/{course.id}/attendance",
                f"/teacher/courses/{course.id}/assessments",
                f"/teacher/courses/{course.id}/assignments"):
        html = teacher_client.get(url).get_data(as_text=True)
        assert 'class="skip-link" href="#main-content"' in html, url
        assert 'id="main-content"' in html, url
        assert html.count("<h1") == 1, url
        assert '<html lang="en">' in html


def test_login_page_is_accessible_and_keeps_its_form(client):
    html = client.get("/login").get_data(as_text=True)
    assert "Log in" in html and 'name="email"' in html and 'name="password"' in html
    assert html.count("<h1") == 1
    assert "sidebarNav" not in html                 # no menu before login


def test_logout_stays_a_post_form(teacher_client):
    html = teacher_client.get("/teacher/dashboard").get_data(as_text=True)
    assert re.search(r'<form method="post" action="/logout"', html)


# ------------------------------------------------------------------ risk report
def test_risk_report_shows_all_five_summary_cards_including_pending(teacher_client, build):
    course, *_ = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    for label in ("Total Students", "Low Risk", "Medium Risk", "High Risk", "Pending"):
        assert re.search(rf'stat-label">[^<]*(<span[^>]*>[^<]*</span>)?\s*{label}', html), label
    assert html.count('class="card stat-card') == 5


def test_risk_report_badges_use_text_not_just_colour(teacher_client, build):
    course, *_ = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    assert re.search(r'risk-badge risk-high"><span[^>]*>[^<]*</span>High Risk</span>', html)
    assert re.search(r'risk-badge risk-low"><span[^>]*>[^<]*</span>Low Risk</span>', html)
    assert re.search(r'risk-badge risk-pending"><span[^>]*>[^<]*</span>Pending</span>', html)


def test_risk_report_details_rows_keep_every_explanation_and_intervention(teacher_client, build):
    course, high, *_ = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    assert "Why is this student flagged?" in html
    assert "Recommended Interventions" in html
    assert "Attendance risk" in html
    assert "Review attendance and arrange counselling" in html
    assert "Unavailable indicators:" in html
    # the details are reachable by a toggle that points at the three detail rows
    assert f'aria-controls="why-{high.id} act-{high.id} data-{high.id}"' in html
    for prefix in ("why", "act", "data"):
        assert f'id="{prefix}-{high.id}"' in html


def test_risk_report_filters_are_buttons_with_counts_and_a_no_match_row(teacher_client, build):
    course, *_ = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    for value in ("All", "Low Risk", "Medium Risk", "High Risk", "Pending"):
        assert f'data-filter="{value}"' in html
    assert 'aria-pressed="true"' in html and "No students match this filter." in html


def test_risk_report_export_and_record_actions_still_present(teacher_client, build):
    course, *_ = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    for text in ("Export PDF", "Export Excel", "Record Risk Assessments"):
        assert text in html
    assert f"/teacher/courses/{course.id}/risk-report/export.pdf" in html
    assert f"/teacher/courses/{course.id}/risk-report/export.xlsx" in html
    assert f"/teacher/courses/{course.id}/risk-report/record" in html


# -------------------------------------------------------------- student details
def test_student_detail_keeps_all_sections_and_adds_indicator_cards(teacher_client, build):
    course, high, *_ = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/students/{high.id}/risk").get_data(as_text=True)
    for section in ("Student Information", "Overall Risk Score", "Classification",
                    "Risk Calculation", "Risk Explanations", "Recommended Interventions",
                    "Attendance Breakdown", "Assessment Marks", "Assignment Status",
                    "Risk History", "Download Student PDF", "Record Risk Assessment"):
        assert section in html, section
    assert html.count("indicator-card") >= 3
    assert "At risk" in html                        # text, not only colour
    for anchor in ("risk-calculation", "attendance-details", "assessment-details",
                   "assignment-details", "risk-history"):
        assert f'id="{anchor}"' in html


def test_student_detail_pending_student_shows_unavailable_not_zero(teacher_client, build):
    course, _high, _low, pending = flagged_course(build)
    html = teacher_client.get(f"/teacher/courses/{course.id}/students/{pending.id}/risk").get_data(as_text=True)
    assert "Unavailable" in html and "risk-pending" in html
    assert "0.0%" not in html


# ------------------------------------------------------------- admin and forms
def test_admin_pages_render_with_consistent_header_and_empty_states(admin_client):
    for url, empty in (("/admin/students", "No students yet."),
                       ("/admin/courses", "No courses yet.")):
        html = admin_client.get(url).get_data(as_text=True)
        assert html.count("<h1") == 1 and "page-header" in html and empty in html
    teachers = admin_client.get("/admin/teachers").get_data(as_text=True)
    assert teachers.count("<h1") == 1 and "page-header" in teachers


def test_admin_forms_use_shared_form_layout(admin_client):
    for url in ("/admin/students/add", "/admin/teachers/add", "/admin/courses/add"):
        html = admin_client.get(url).get_data(as_text=True)
        assert "form-card" in html and "form-actions" in html and "Cancel" in html


def test_error_pages_use_the_new_layout(teacher_client):
    response = teacher_client.get("/teacher/courses/99999/risk-report")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "empty-state" in html and "Back to my dashboard" in html


def test_chart_libraries_are_still_loaded_from_the_cdn(teacher_client, build):
    course, high, *_ = flagged_course(build)
    report = teacher_client.get(f"/teacher/courses/{course.id}/risk-report").get_data(as_text=True)
    assert "cdn.jsdelivr.net/npm/chart.js" in report and "riskDistributionChart" in report
    assert "cdn.jsdelivr.net/npm/bootstrap@5.3.3" in report
