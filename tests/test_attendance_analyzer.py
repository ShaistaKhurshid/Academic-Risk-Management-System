
from types import SimpleNamespace

from app.services.attendance_analyzer import AttendanceAnalyzer


def make_records(statuses):
    return [
        SimpleNamespace(status=status)
        for status in statuses
    ]


def test_present_and_late_count_as_attended():
    records = make_records([
        "Present",
        "Present (Late)",
        "Absent",
        "Present",
    ])

    result = AttendanceAnalyzer.analyze(records)

    assert result["available"] is True
    assert result["total_sessions"] == 4
    assert result["classes_attended"] == 3
    assert result["attendance_percentage"] == 75.0
    assert result["risk_flag"] is False


def test_attendance_below_75_percent_triggers_risk():
    records = make_records([
        "Present",
        "Present",
        "Absent",
        "Absent",
    ])

    result = AttendanceAnalyzer.analyze(records)

    assert result["attendance_percentage"] == 50.0
    assert result["risk_flag"] is True
    assert abs(result["risk_score"] - (100 / 3)) < 0.000001


def test_zero_attendance_has_100_risk_score():
    records = make_records([
        "Absent",
        "Absent",
        "Absent",
    ])

    result = AttendanceAnalyzer.analyze(records)

    assert result["attendance_percentage"] == 0.0
    assert result["risk_flag"] is True
    assert result["risk_score"] == 100.0


def test_no_attendance_records_returns_pending():
    result = AttendanceAnalyzer.analyze([])

    assert result["available"] is False
    assert result["status"] == "Pending"
    assert result["attendance_percentage"] is None
    assert result["risk_score"] is None
    assert result["risk_flag"] is False
