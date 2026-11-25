"""Phase 12: pure logic for historical risk tracking (no database needed)."""
import json
from datetime import datetime
from types import SimpleNamespace as NS

from app.services.attendance_analyzer import AttendanceAnalyzer
from app.services.performance_analyzer import PerformanceAnalyzer
from app.services.assignment_analyzer import AssignmentAnalyzer
from app.services.risk_scoring_service import RiskScoringService
from app.services.risk_classification_service import RiskClassificationService
from app.services.risk_history_summary import (
    CHANGE_TOLERANCE,
    VALUE_FIELDS,
    build_history_view,
    compare_indicator,
    compare_values,
    explanations_from_json,
    snapshot_to_values,
    snapshot_values_from_report,
    values_are_identical,
)


# ------------------------------------------------------------------ helpers
def make_report(attendance_statuses=(), marks=(), assignment_statuses=None, student_id=1):
    """The same pipeline as AcademicRiskService.generate_report, without a database.

    marks: list of (obtained, max_marks). assignment_statuses: list of five statuses.
    """
    att = [NS(status=status) for status in attendance_statuses]
    marks_records = [NS(marks_obtained=got, assessment=NS(max_marks=mx)) for got, mx in marks]
    assignments = []
    for index, status in enumerate(assignment_statuses or [], start=1):
        assignment = NS(id=index, submissions=[])
        assignment.submissions.append(NS(student_id=student_id, status=status))
        assignments.append(assignment)

    attendance = AttendanceAnalyzer.analyze(att)
    performance = PerformanceAnalyzer.analyze(marks_records)
    assignment_result = AssignmentAnalyzer.analyze(assignments, student_id)
    overall = RiskScoringService.calculate(
        attendance=attendance, performance=performance, assignments=assignment_result)
    classified = RiskClassificationService.classify(
        overall, attendance, performance, assignment_result)
    return {"attendance": attendance, "performance": performance,
            "assignments": assignment_result, "overall": overall,
            "classification": classified["classification"],
            "risk_explanations": classified["explanations"],
            "interventions": classified["interventions"]}


FULL = dict(
    attendance_statuses=["Present", "Present", "Present (Late)", "Absent"],          # 75%
    marks=[(10, 20)],                                                                 # 50%
    assignment_statuses=["Submitted", "Late Submission", "Not Submitted", "Excused", "Submitted"],  # 60%
)


def values(score, classification=None, attendance=None, performance=None, assignments=None,
           explanations="[]"):
    """Hand-made snapshot values for comparison tests."""
    if classification is None:
        classification = "Pending" if score is None else "Low Risk"
    data = {field: None for field in VALUE_FIELDS}
    data.update(overall_risk_score=score, classification=classification,
                attendance_percentage=attendance, performance_percentage=performance,
                assignment_percentage=assignments, explanations_json=explanations)
    return data


def snapshot(day, hour=9, **overrides):
    """A stored-snapshot stand-in: any object with the value attributes + recorded_at."""
    data = values(overrides.pop("score", 10.0), **overrides)
    return NS(recorded_at=datetime(2026, 11, day, hour, 30), **data)


# ----------------------------------------------------- engine report -> values
def test_full_report_is_converted_to_snapshot_values():
    report = make_report(**FULL)
    stored = snapshot_values_from_report(report)

    assert stored["overall_risk_score"] == report["overall"]["overall_risk_score"]
    assert stored["classification"] == "Low Risk"
    assert stored["attendance_percentage"] == 75.0
    assert stored["performance_percentage"] == 50.0
    assert stored["assignment_percentage"] == 60.0
    assert stored["attendance_weight"] == 0.4
    assert stored["performance_weight"] == 0.4
    assert stored["assignment_weight"] == 0.2
    assert set(stored) == set(VALUE_FIELDS)


def test_component_risk_scores_are_copied_from_the_engine():
    report = make_report(**FULL)
    stored = snapshot_values_from_report(report)
    assert stored["attendance_risk_score"] == report["attendance"]["risk_score"]
    assert stored["performance_risk_score"] == report["performance"]["risk_score"]
    assert stored["assignment_risk_score"] == report["assignments"]["risk_score"]


def test_partial_report_stores_none_for_unavailable_indicators():
    report = make_report(attendance_statuses=["Present", "Absent", "Absent", "Absent"])   # only attendance
    stored = snapshot_values_from_report(report)

    assert stored["attendance_percentage"] == 25.0
    assert stored["attendance_weight"] == 1.0              # weights rescaled to 100%
    for field in ("performance_percentage", "performance_risk_score", "performance_weight",
                  "assignment_percentage", "assignment_risk_score", "assignment_weight"):
        assert stored[field] is None, field


def test_pending_report_stores_pending_with_no_score_or_values():
    stored = snapshot_values_from_report(make_report())
    assert stored["classification"] == "Pending"
    assert stored["overall_risk_score"] is None
    assert [stored[f] for f in VALUE_FIELDS if f not in ("classification", "explanations_json")] \
        == [None] * (len(VALUE_FIELDS) - 2)
    assert stored["explanations_json"] == "[]"


def test_a_real_zero_percentage_is_kept_as_zero_not_none():
    report = make_report(attendance_statuses=["Absent", "Absent", "Absent"], marks=[(0, 20)])
    stored = snapshot_values_from_report(report)
    assert stored["attendance_percentage"] == 0.0 and stored["attendance_percentage"] is not None
    assert stored["performance_percentage"] == 0.0 and stored["performance_percentage"] is not None


def test_explanations_are_stored_as_json_list():
    report = make_report(attendance_statuses=["Present", "Absent", "Absent", "Absent"])
    stored = snapshot_values_from_report(report)
    assert json.loads(stored["explanations_json"]) == report["risk_explanations"]
    assert "Attendance risk" in explanations_from_json(stored["explanations_json"])


def test_explanations_decoding_never_raises():
    assert explanations_from_json('["A", "B"]') == ["A", "B"]
    assert explanations_from_json("[]") == []
    assert explanations_from_json("") == []
    assert explanations_from_json(None) == []
    assert explanations_from_json("not json") == []
    assert explanations_from_json('{"a": 1}') == []


def test_snapshot_to_values_round_trips():
    stored = snapshot_values_from_report(make_report(**FULL))
    restored = snapshot_to_values(NS(**stored))
    assert restored == stored


# ------------------------------------------------------ duplicate detection
def test_identical_values_are_identical():
    first = snapshot_values_from_report(make_report(**FULL))
    second = snapshot_values_from_report(make_report(**FULL))
    assert values_are_identical(first, second)


def test_tiny_float_noise_is_ignored():
    first = values(12.5, attendance=75.0)
    second = values(12.5 + 1e-9, attendance=75.0 - 1e-9)
    assert values_are_identical(first, second)


def test_any_real_change_makes_values_different():
    base = values(12.5, attendance=75.0, performance=50.0, assignments=60.0)
    assert not values_are_identical(base, values(12.6, attendance=75.0, performance=50.0, assignments=60.0))
    assert not values_are_identical(base, values(12.5, attendance=74.0, performance=50.0, assignments=60.0))
    assert not values_are_identical(base, values(12.5, attendance=75.0, performance=50.0, assignments=80.0))
    assert not values_are_identical(base, values(12.5, "Medium Risk", 75.0, 50.0, 60.0))
    assert not values_are_identical(base, values(12.5, attendance=75.0, performance=50.0,
                                                 assignments=60.0, explanations='["Attendance risk"]'))


def test_none_and_zero_are_not_the_same_value():
    assert not values_are_identical(values(10.0, attendance=None), values(10.0, attendance=0.0))


def test_report_before_and_after_a_data_change_is_different():
    before = snapshot_values_from_report(make_report(**FULL))
    changed = dict(FULL, attendance_statuses=["Present"] * 4)
    after = snapshot_values_from_report(make_report(**changed))
    assert not values_are_identical(before, after)


# ---------------------------------------------------- overall score comparison
def test_lower_score_is_improvement():
    result = compare_values(values(50.0, "Medium Risk"), values(30.0, "Medium Risk"))
    assert result["sufficient"] is True
    assert result["direction"] == "improved"
    assert result["difference"] == -20.0


def test_higher_score_is_deterioration():
    result = compare_values(values(20.0, "Low Risk"), values(45.0, "Medium Risk"))
    assert result["direction"] == "deteriorated"
    assert result["difference"] == 25.0


def test_identical_score_is_unchanged():
    result = compare_values(values(33.3, "Medium Risk"), values(33.3, "Medium Risk"))
    assert result["direction"] == "unchanged"
    assert result["difference"] == 0.0


def test_difference_below_the_displayed_precision_is_unchanged():
    assert CHANGE_TOLERANCE == 0.05
    assert compare_values(values(10.0), values(10.04))["direction"] == "unchanged"
    assert compare_values(values(10.0), values(9.96))["direction"] == "unchanged"
    assert compare_values(values(10.0), values(10.06))["direction"] == "deteriorated"
    assert compare_values(values(10.0), values(9.94))["direction"] == "improved"


def test_classification_change_is_reported_with_both_labels():
    result = compare_values(values(20.0, "Low Risk"), values(35.0, "Medium Risk"))
    assert result["classification_changed"] is True
    assert result["previous_classification"] == "Low Risk"
    assert result["current_classification"] == "Medium Risk"


def test_same_classification_is_not_reported_as_changed():
    result = compare_values(values(20.0, "Low Risk"), values(25.0, "Low Risk"))
    assert result["classification_changed"] is False


def test_pending_on_either_side_makes_no_claim():
    for previous, current in [(values(None), values(40.0, "Medium Risk")),
                              (values(40.0, "Medium Risk"), values(None)),
                              (values(None), values(None))]:
        result = compare_values(previous, current)
        assert result["sufficient"] is False
        assert result["direction"] is None
        assert result["difference"] is None
        assert result["reason"]


def test_pending_to_scored_classification_change_is_still_reported_but_no_direction():
    result = compare_values(values(None), values(15.0, "Low Risk"))
    assert result["classification_changed"] is True
    assert result["direction"] is None


# ------------------------------------------------------ indicator comparison
def test_higher_percentage_is_improving_and_lower_is_declining():
    up = compare_indicator(60.0, 80.0)
    assert up["direction"] == "improving" and up["difference"] == 20.0
    down = compare_indicator(80.0, 60.0)
    assert down["direction"] == "declining" and down["difference"] == -20.0


def test_equal_percentage_is_stable():
    assert compare_indicator(70.0, 70.0)["direction"] == "stable"
    assert compare_indicator(70.0, 70.04)["direction"] == "stable"


def test_unavailable_indicator_is_not_comparable_and_not_zero():
    for previous, current in [(None, 50.0), (50.0, None), (None, None)]:
        result = compare_indicator(previous, current)
        assert result["direction"] is None and result["difference"] is None
    assert compare_indicator(0.0, 40.0)["direction"] == "improving"     # a real zero IS comparable


def test_indicators_are_compared_even_when_overall_score_is_not_comparable():
    result = compare_values(values(None, attendance=50.0), values(20.0, "Low Risk", attendance=80.0))
    assert result["sufficient"] is False
    assert result["indicators"]["attendance"]["direction"] == "improving"
    assert result["indicators"]["performance"]["direction"] is None


# ------------------------------------------------------------ history view
def test_empty_history_has_no_rows_no_comparison_and_empty_chart():
    view = build_history_view([], make_report(**FULL))
    assert view["count"] == 0 and view["has_history"] is False
    assert view["rows"] == [] and view["since_last"] is None
    assert view["chart"]["labels"] == [] and view["chart"]["overall"] == []


def test_single_snapshot_has_a_row_without_change_but_a_live_comparison():
    live = make_report(**FULL)                                  # score 8.0
    stored = [snapshot(10, score=20.0, classification="Low Risk")]
    view = build_history_view(stored, live)

    assert view["count"] == 1 and len(view["rows"]) == 1
    assert view["rows"][0]["change"] is None
    assert view["since_last"]["sufficient"] is True
    assert view["since_last"]["previous_score"] == 20.0
    assert view["since_last"]["direction"] == "improved"        # 20.0 -> 8.0
    assert view["since_last"]["last_recorded_at"] == stored[0].recorded_at


def test_rows_are_newest_first_with_change_against_the_previous_snapshot():
    stored = [snapshot(1, score=50.0, classification="Medium Risk"),
              snapshot(8, score=35.0, classification="Medium Risk"),
              snapshot(15, score=20.0, classification="Low Risk")]
    view = build_history_view(stored, make_report(**FULL))

    assert [row["overall_risk_score"] for row in view["rows"]] == [20.0, 35.0, 50.0]
    assert view["rows"][0]["change"]["direction"] == "improved"
    assert view["rows"][0]["change"]["classification_changed"] is True
    assert view["rows"][1]["change"]["direction"] == "improved"
    assert view["rows"][2]["change"] is None                    # oldest has nothing before it


def test_chart_series_are_chronological_and_keep_none_for_unavailable():
    stored = [snapshot(1, score=None, attendance=None),
              snapshot(8, score=30.0, classification="Medium Risk", attendance=0.0, performance=55.0),
              snapshot(15, score=20.0, classification="Low Risk", attendance=80.0)]
    chart = build_history_view(stored, make_report(**FULL))["chart"]

    assert chart["labels"] == ["01 Nov 2026 09:30", "08 Nov 2026 09:30", "15 Nov 2026 09:30"]
    assert chart["overall"] == [None, 30.0, 20.0]               # Pending is a gap, not 0
    assert chart["attendance"] == [None, 0.0, 80.0]             # unavailable None vs real 0.0
    assert chart["performance"] == [None, 55.0, None]
    assert chart["assignments"] == [None, None, None]


def test_chart_data_can_be_serialised_to_json():
    stored = [snapshot(1, score=None), snapshot(2, score=12.0, classification="Low Risk")]
    chart = build_history_view(stored, make_report())["chart"]
    assert json.loads(json.dumps(chart)) == chart


def test_pending_snapshot_row_is_shown_as_pending_with_no_score():
    view = build_history_view([snapshot(1, score=None)], make_report())
    row = view["rows"][0]
    assert row["classification"] == "Pending" and row["overall_risk_score"] is None


def test_live_pending_gives_no_improvement_claim_against_a_scored_snapshot():
    view = build_history_view([snapshot(1, score=40.0, classification="Medium Risk")], make_report())
    assert view["since_last"]["sufficient"] is False
    assert view["since_last"]["direction"] is None


def test_history_rows_include_decoded_explanations():
    stored = [snapshot(1, score=40.0, classification="Medium Risk",
                       explanations='["Attendance risk", "Assignment completion risk"]')]
    view = build_history_view(stored, make_report(**FULL))
    assert view["rows"][0]["explanations"] == ["Attendance risk", "Assignment completion risk"]


def test_building_the_view_does_not_modify_the_stored_snapshots():
    stored = [snapshot(1, score=40.0, classification="Medium Risk", attendance=50.0)]
    before = [snapshot_to_values(s) for s in stored]
    build_history_view(stored, make_report(**FULL))
    assert [snapshot_to_values(s) for s in stored] == before


def test_live_change_does_not_alter_what_the_history_rows_show():
    stored = [snapshot(1, score=40.0, classification="Medium Risk", attendance=50.0)]
    first = build_history_view(stored, make_report(**FULL))["rows"]
    second = build_history_view(stored, make_report())["rows"]       # live now Pending
    assert first == second
