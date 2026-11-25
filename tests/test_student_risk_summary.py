"""Unit tests for the pure helpers behind the student risk detail page.

These need no database. They also check that the helpers reuse the existing
analyzers' rules instead of inventing new ones.
"""
from datetime import date
from types import SimpleNamespace as NS

from app.services.attendance_analyzer import AttendanceAnalyzer
from app.services.performance_analyzer import PerformanceAnalyzer
from app.services.assignment_analyzer import AssignmentAnalyzer
from app.services.risk_scoring_service import RiskScoringService
from app.services.risk_classification_service import RiskClassificationService
from app.services.student_risk_summary import (
    summarise_attendance,
    summarise_assessments,
    summarise_assignments,
    build_components,
    NO_RECORD_LABEL,
)


# ---------------------------------------------------------------- helpers
def attendance(day, status):
    return NS(session_date=date(2026, 11, day), status=status)


def assignments_with_statuses(statuses, student_id=1):
    """Build assignment objects and the {id: submission} dict used by the helper."""
    assignments, submissions = [], {}
    for index, status in enumerate(statuses, start=1):
        assignment = NS(id=index, title=f"Assignment {index}",
                        deadline=date(2026, 12, 1), submissions=[])
        if status is not None:
            submission = NS(assignment_id=index, student_id=student_id, status=status)
            assignment.submissions.append(submission)
            submissions[index] = submission
        assignments.append(assignment)
    return assignments, submissions


def make_report(att_records, marks_records, assignments, student_id=1):
    """Same pipeline as AcademicRiskService.generate_report, without the database."""
    attendance_result = AttendanceAnalyzer.analyze(att_records)
    performance_result = PerformanceAnalyzer.analyze(marks_records)
    assignment_result = AssignmentAnalyzer.analyze(assignments, student_id)
    overall = RiskScoringService.calculate(
        attendance=attendance_result, performance=performance_result,
        assignments=assignment_result)
    classified = RiskClassificationService.classify(
        overall, attendance_result, performance_result, assignment_result)
    return {"attendance": attendance_result, "performance": performance_result,
            "assignments": assignment_result, "overall": overall,
            "classification": classified["classification"]}


# ------------------------------------------------------------- attendance
def test_attendance_counts_each_status_separately():
    records = [attendance(1, "Present"), attendance(2, "Present (Late)"),
               attendance(3, "Absent"), attendance(4, "Present")]
    summary = summarise_attendance(records)
    assert summary["total_sessions"] == 4
    assert summary["present_count"] == 2
    assert summary["late_count"] == 1
    assert summary["absent_count"] == 1


def test_present_and_late_both_count_as_attended():
    records = [attendance(1, "Present"), attendance(2, "Present (Late)"),
               attendance(3, "Absent")]
    summary = summarise_attendance(records)
    assert summary["attended_count"] == 2
    assert [s["attended"] for s in summary["sessions"]] == [True, True, False]


def test_attendance_sessions_are_sorted_by_date():
    records = [attendance(9, "Absent"), attendance(2, "Present"), attendance(5, "Present")]
    days = [s["date"].day for s in summarise_attendance(records)["sessions"]]
    assert days == [2, 5, 9]


def test_no_attendance_records_gives_empty_summary():
    summary = summarise_attendance([])
    assert summary["total_sessions"] == 0
    assert summary["sessions"] == []
    assert summary["attended_count"] == 0


# ------------------------------------------------------------ assessments
def assessment(assessment_id, max_marks, title=None):
    return NS(id=assessment_id, title=title or f"Quiz {assessment_id}",
              max_marks=max_marks, assessment_date=date(2026, 11, 5))


def test_graded_assessment_row_has_marks_and_percentage():
    quiz = assessment(1, 20)
    summary = summarise_assessments([quiz], {1: NS(marks_obtained=15)})
    row = summary["rows"][0]
    assert row["graded"] is True
    assert row["marks_obtained"] == 15
    assert row["max_marks"] == 20
    assert row["percentage"] == 75.0


def test_assessment_without_marks_row_is_not_graded_and_not_zero():
    summary = summarise_assessments([assessment(1, 20)], {})
    row = summary["rows"][0]
    assert row["graded"] is False
    assert row["marks_obtained"] is None
    assert row["percentage"] is None
    assert summary["ungraded_count"] == 1


def test_assessment_with_null_marks_is_not_graded():
    summary = summarise_assessments([assessment(1, 20)], {1: NS(marks_obtained=None)})
    assert summary["rows"][0]["graded"] is False
    assert summary["graded_count"] == 0


def test_a_real_zero_is_graded_and_not_treated_as_missing():
    summary = summarise_assessments([assessment(1, 20)], {1: NS(marks_obtained=0)})
    row = summary["rows"][0]
    assert row["graded"] is True
    assert row["percentage"] == 0.0
    assert summary["graded_count"] == 1


def test_assessment_counts_mix_graded_and_ungraded():
    quizzes = [assessment(1, 10), assessment(2, 10), assessment(3, 10)]
    summary = summarise_assessments(quizzes, {1: NS(marks_obtained=5)})
    assert summary["total_assessments"] == 3
    assert summary["graded_count"] == 1
    assert summary["ungraded_count"] == 2


def test_zero_max_marks_never_causes_division_by_zero():
    broken = assessment(1, 0)
    summary = summarise_assessments([broken], {1: NS(marks_obtained=0)})
    assert summary["rows"][0]["percentage"] is None


# ------------------------------------------------------------ assignments
def test_assignment_status_counts():
    assignments, subs = assignments_with_statuses(
        ["Submitted", "Submitted", "Late Submission", "Not Submitted", "Excused"])
    summary = summarise_assignments(assignments, subs)
    assert summary["submitted_count"] == 2
    assert summary["late_count"] == 1
    assert summary["not_submitted_count"] == 1
    assert summary["excused_count"] == 1
    assert summary["no_record_count"] == 0
    assert summary["pending_message"] is None


def test_missing_submission_is_no_record_not_not_submitted():
    assignments, subs = assignments_with_statuses(
        ["Submitted", None, "Submitted", "Submitted", "Submitted"])
    summary = summarise_assignments(assignments, subs)
    assert summary["no_record_count"] == 1
    assert summary["not_submitted_count"] == 0
    assert summary["rows"][1]["status"] is None
    assert summary["rows"][1]["status_label"] == NO_RECORD_LABEL
    assert "not recorded for 1 of 5" in summary["pending_message"]


def test_fewer_than_five_assignments_is_pending():
    assignments, subs = assignments_with_statuses(["Submitted", "Submitted", "Submitted"])
    summary = summarise_assignments(assignments, subs)
    assert summary["created_count"] == 3
    assert "3 of 5 required" in summary["pending_message"]


def test_more_than_five_assignments_is_pending():
    assignments, subs = assignments_with_statuses(["Submitted"] * 6)
    summary = summarise_assignments(assignments, subs)
    assert "exactly 5 are required" in summary["pending_message"]


def test_pending_message_agrees_with_the_assignment_analyzer():
    """The page's 'pending' wording must match when the engine says unavailable."""
    cases = [["Submitted"] * 5, ["Submitted"] * 4, ["Submitted"] * 6,
             ["Submitted", None, "Submitted", "Submitted", "Submitted"]]
    for statuses in cases:
        assignments, subs = assignments_with_statuses(statuses)
        engine = AssignmentAnalyzer.analyze(assignments, 1)
        summary = summarise_assignments(assignments, subs)
        assert (summary["pending_message"] is None) == engine["available"], statuses


# ------------------------------------------------------------- components
def test_components_come_from_the_report_and_contributions_sum_to_overall():
    att = [attendance(1, "Present"), attendance(2, "Absent"),
           attendance(3, "Absent"), attendance(4, "Present")]            # 50%
    marks = [NS(marks_obtained=10, assessment=NS(max_marks=40))]           # 25%
    assignments, subs = assignments_with_statuses(
        ["Submitted", "Submitted", "Submitted", "Not Submitted", "Not Submitted"])  # 60%
    report = make_report(att, marks, assignments)

    components = build_components(report)

    assert [c["key"] for c in components] == ["attendance", "performance", "assignments"]
    assert all(c["available"] for c in components)
    assert abs(sum(c["contribution"] for c in components)
               - report["overall"]["overall_risk_score"]) < 1e-9
    assert components[0]["value"] == 50.0
    assert components[1]["value"] == 25.0
    assert components[2]["value"] == 60.0


def test_component_thresholds_are_the_analyzer_constants():
    report = make_report([], [], [])
    thresholds = {c["key"]: c["threshold"] for c in build_components(report)}
    assert thresholds["attendance"] == AttendanceAnalyzer.RISK_THRESHOLD == 75.0
    assert thresholds["performance"] == PerformanceAnalyzer.RISK_THRESHOLD == 40.0
    assert thresholds["assignments"] == 100.0


def test_unavailable_indicator_has_no_value_score_or_contribution():
    att = [attendance(1, "Present"), attendance(2, "Absent")]              # only attendance
    report = make_report(att, [], [])
    attendance_c, performance_c, assignments_c = build_components(report)

    assert attendance_c["available"] is True
    assert attendance_c["effective_weight"] == 1.0          # weights rescaled to 100%
    for unavailable in (performance_c, assignments_c):
        assert unavailable["available"] is False
        assert unavailable["value"] is None
        assert unavailable["risk_score"] is None
        assert unavailable["contribution"] is None
        assert unavailable["effective_weight"] is None


def test_components_when_nothing_is_available():
    report = make_report([], [], [])
    assert report["classification"] == "Pending"
    assert all(c["available"] is False for c in build_components(report))


def test_base_weights_are_the_approved_40_40_20():
    report = make_report([], [], [])
    weights = {c["key"]: c["base_weight"] for c in build_components(report)}
    assert weights == {"attendance": 0.40, "performance": 0.40, "assignments": 0.20}
