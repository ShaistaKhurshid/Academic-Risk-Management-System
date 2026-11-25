
from types import SimpleNamespace

from app.services.performance_analyzer import PerformanceAnalyzer


def make_record(marks_obtained, max_marks):
    assessment = SimpleNamespace(max_marks=max_marks)

    return SimpleNamespace(
        marks_obtained=marks_obtained,
        assessment=assessment,
    )


def test_normal_performance_calculation():
    records = [
        make_record(80, 100),
        make_record(40, 50),
    ]

    result = PerformanceAnalyzer.analyze(records)

    assert result["available"] is True
    assert result["graded_assessments"] == 2
    assert result["total_marks_obtained"] == 120
    assert result["total_max_marks"] == 150
    assert result["performance_percentage"] == 80.0
    assert result["risk_flag"] is False


def test_weighted_aggregate_with_different_max_marks():
    records = [
        make_record(90, 100),
        make_record(5, 10),
    ]

    result = PerformanceAnalyzer.analyze(records)

    assert result["performance_percentage"] == (
        95 / 110 * 100
    )


def test_ungraded_assessments_are_excluded():
    records = [
        make_record(80, 100),
        make_record(None, 50),
    ]

    result = PerformanceAnalyzer.analyze(records)

    assert result["graded_assessments"] == 1
    assert result["total_marks_obtained"] == 80
    assert result["total_max_marks"] == 100
    assert result["performance_percentage"] == 80.0


def test_zero_marks_count_as_graded():
    records = [
        make_record(0, 100),
    ]

    result = PerformanceAnalyzer.analyze(records)

    assert result["available"] is True
    assert result["graded_assessments"] == 1
    assert result["performance_percentage"] == 0.0
    assert result["risk_flag"] is True
    assert result["risk_score"] == 100.0


def test_performance_below_40_percent_triggers_risk():
    records = [
        make_record(30, 100),
    ]

    result = PerformanceAnalyzer.analyze(records)

    assert result["performance_percentage"] == 30.0
    assert result["risk_flag"] is True
    assert result["risk_score"] == 25.0


def test_no_graded_assessments_returns_pending():
    records = [
        make_record(None, 100),
        make_record(None, 50),
    ]

    result = PerformanceAnalyzer.analyze(records)

    assert result["available"] is False
    assert result["status"] == "Pending"
    assert result["graded_assessments"] == 0
    assert result["performance_percentage"] is None
    assert result["risk_score"] is None
    assert result["risk_flag"] is False

