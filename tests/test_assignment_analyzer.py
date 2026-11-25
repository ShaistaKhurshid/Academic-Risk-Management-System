
from types import SimpleNamespace

from app.services.assignment_analyzer import AssignmentAnalyzer


def make_assignments(statuses, student_id=1):
    assignments = []

    for index, status in enumerate(statuses):
        submissions = []

        if status is not None:
            submissions.append(
                SimpleNamespace(
                    student_id=student_id,
                    status=status,
                )
            )

        assignments.append(
            SimpleNamespace(
                id=index + 1,
                submissions=submissions,
            )
        )

    return assignments


def test_all_submitted_means_100_percent_completion():
    assignments = make_assignments(["Submitted"] * 5)

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["available"] is True
    assert result["completed_count"] == 5
    assert result["incomplete_count"] == 0
    assert result["completion_percentage"] == 100.0
    assert result["risk_score"] == 0.0
    assert result["risk_flag"] is False


def test_late_submissions_count_as_completed():
    assignments = make_assignments([
        "Submitted",
        "Late Submission",
        "Submitted",
        "Late Submission",
        "Submitted",
    ])

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["completed_count"] == 5
    assert result["late_submission_count"] == 2
    assert result["completion_percentage"] == 100.0
    assert result["risk_flag"] is False


def test_not_submitted_and_excused_count_as_incomplete():
    assignments = make_assignments([
        "Submitted",
        "Late Submission",
        "Not Submitted",
        "Excused",
        "Submitted",
    ])

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["completed_count"] == 3
    assert result["incomplete_count"] == 2
    assert result["not_submitted_count"] == 1
    assert result["excused_count"] == 1
    assert result["completion_percentage"] == 60.0
    assert result["risk_score"] == 40.0
    assert result["risk_flag"] is True


def test_fewer_than_five_assignments_returns_pending():
    assignments = make_assignments([
        "Submitted",
        "Submitted",
        "Submitted",
        "Submitted",
    ])

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["available"] is False
    assert result["status"] == "Pending"
    assert result["completion_percentage"] is None
    assert result["risk_score"] is None


def test_missing_submission_status_returns_pending():
    assignments = make_assignments([
        "Submitted",
        "Submitted",
        None,
        "Submitted",
        "Submitted",
    ])

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["available"] is False
    assert result["status"] == "Pending"
    assert result["completion_percentage"] is None


def test_student_id_is_checked_for_each_submission():
    assignments = make_assignments(
        ["Submitted"] * 5,
        student_id=2,
    )

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["available"] is False
    assert result["status"] == "Pending"


def test_zero_completed_assignments_means_full_risk():
    assignments = make_assignments(["Not Submitted"] * 5)

    result = AssignmentAnalyzer.analyze(assignments, 1)

    assert result["completed_count"] == 0
    assert result["completion_percentage"] == 0.0
    assert result["risk_score"] == 100.0
    assert result["risk_flag"] is True
