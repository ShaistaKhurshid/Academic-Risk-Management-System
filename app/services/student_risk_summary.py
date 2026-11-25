"""Pure helper functions that prepare the breakdowns shown on the student risk
detail page (and, later, in the PDF/Excel exports).

IMPORTANT: nothing in this file recalculates a risk score. Scores, percentages and
classifications always come from the existing analyzers through
AcademicRiskService. These helpers only organise raw records for display and
count them.

There are no database or Flask imports here on purpose, so the functions can be
unit tested with plain Python objects.
"""
from app.services.attendance_analyzer import AttendanceAnalyzer
from app.services.performance_analyzer import PerformanceAnalyzer
from app.services.assignment_analyzer import AssignmentAnalyzer
from app.services.risk_scoring_service import RiskScoringService

# AssignmentAnalyzer flags risk whenever completion is below 100%.
ASSIGNMENT_COMPLETION_TARGET = 100.0

NO_RECORD_LABEL = "No record"


def summarise_attendance(records):
    """Session-by-session attendance plus counts for each status.

    `records` are objects with .session_date and .status. Sessions are returned
    in date order. "Attended" uses the same rule as AttendanceAnalyzer
    (Present and Present (Late) both count as attended).
    """
    ordered = sorted(records, key=lambda record: record.session_date)
    attended_statuses = AttendanceAnalyzer.ATTENDED_STATUSES

    sessions = [
        {
            "date": record.session_date,
            "status": record.status,
            "attended": record.status in attended_statuses,
        }
        for record in ordered
    ]

    return {
        "sessions": sessions,
        "total_sessions": len(ordered),
        "present_count": sum(1 for r in ordered if r.status == "Present"),
        "late_count": sum(1 for r in ordered if r.status == "Present (Late)"),
        "absent_count": sum(1 for r in ordered if r.status == "Absent"),
        "attended_count": sum(1 for r in ordered if r.status in attended_statuses),
    }


def summarise_assessments(assessments, marks_by_assessment_id):
    """One row per assessment in the course, in the order given.

    `marks_by_assessment_id` maps assessment id -> a record with .marks_obtained.
    An assessment with no marks row, or with marks_obtained = None, is
    "not graded". Not graded is NEVER treated as zero. A real 0 is graded.
    """
    rows = []

    for assessment in assessments:
        record = marks_by_assessment_id.get(assessment.id)
        obtained = record.marks_obtained if record is not None else None
        graded = obtained is not None

        if graded and assessment.max_marks:
            percentage = (obtained / assessment.max_marks) * 100
        else:
            percentage = None

        rows.append({
            "title": assessment.title,
            "date": assessment.assessment_date,
            "max_marks": assessment.max_marks,
            "marks_obtained": obtained,
            "percentage": percentage,
            "graded": graded,
        })

    graded_count = sum(1 for row in rows if row["graded"])

    return {
        "rows": rows,
        "total_assessments": len(rows),
        "graded_count": graded_count,
        "ungraded_count": len(rows) - graded_count,
    }


def summarise_assignments(assignments, submissions_by_assignment_id):
    """One row per assignment with this student's status, plus status counts.

    A missing submission row is shown as "No record". It is NOT counted as Not
    Submitted (the business rule: missing records are not assumed incomplete).
    `pending_message` explains why assignment completion is unavailable, using
    the same rule as AssignmentAnalyzer (exactly five assignments, and a saved
    status for each).
    """
    required = AssignmentAnalyzer.REQUIRED_ASSIGNMENTS
    rows = []

    for assignment in assignments:
        submission = submissions_by_assignment_id.get(assignment.id)
        status = submission.status if submission is not None else None
        rows.append({
            "title": assignment.title,
            "deadline": assignment.deadline,
            "status": status,
            "status_label": status if status is not None else NO_RECORD_LABEL,
        })

    created = len(rows)
    statuses = [row["status"] for row in rows]
    no_record_count = statuses.count(None)

    if created < required:
        pending_message = (
            f"Assignment Pending: {created} of {required} required "
            "assignments have been created."
        )
    elif created > required:
        pending_message = (
            f"Assignment Pending: {created} assignments exist, but exactly "
            f"{required} are required."
        )
    elif no_record_count:
        pending_message = (
            "Assignment Pending: submission status is not recorded for "
            f"{no_record_count} of {required} assignments."
        )
    else:
        pending_message = None

    return {
        "rows": rows,
        "required": required,
        "created_count": created,
        "recorded_count": created - no_record_count,
        "submitted_count": statuses.count("Submitted"),
        "late_count": statuses.count("Late Submission"),
        "not_submitted_count": statuses.count("Not Submitted"),
        "excused_count": statuses.count("Excused"),
        "no_record_count": no_record_count,
        "pending_message": pending_message,
    }


def build_components(report):
    """The three risk components, ready for a table.

    Every number is taken from the report produced by AcademicRiskService.
    contribution = component risk score x effective weight, so the
    contributions of the available indicators add up to the overall score.
    """
    spec = [
        ("attendance", "Attendance", "attendance_percentage",
         AttendanceAnalyzer.RISK_THRESHOLD),
        ("performance", "Academic performance", "performance_percentage",
         PerformanceAnalyzer.RISK_THRESHOLD),
        ("assignments", "Assignment completion", "completion_percentage",
         ASSIGNMENT_COMPLETION_TARGET),
    ]

    effective_weights = report["overall"].get("effective_weights", {})
    components = []

    for key, label, value_key, threshold in spec:
        result = report[key]
        available = result["available"]
        weight = effective_weights.get(key)

        if available and weight is not None:
            contribution = result["risk_score"] * weight
        else:
            contribution = None

        components.append({
            "key": key,
            "label": label,
            "available": available,
            "value": result[value_key] if available else None,
            "threshold": threshold,
            "risk_score": result["risk_score"] if available else None,
            "risk_flag": result["risk_flag"] if available else False,
            "base_weight": RiskScoringService.WEIGHTS[key],
            "effective_weight": weight,
            "contribution": contribution,
        })

    return components
