
from app.services.risk_scoring_service import RiskScoringService


def make_indicator(available, risk_score=None):
    return {
        "available": available,
        "risk_score": risk_score,
    }


def test_all_three_indicators_use_original_weights():
    result = RiskScoringService.calculate(
        attendance=make_indicator(True, 20),
        performance=make_indicator(True, 40),
        assignments=make_indicator(True, 60),
    )

    assert result["available"] is True
    assert result["overall_risk_score"] == 36.0

    assert result["effective_weights"] == {
        "attendance": 0.40,
        "performance": 0.40,
        "assignments": 0.20,
    }


def test_missing_assignments_normalizes_remaining_weights():
    result = RiskScoringService.calculate(
        attendance=make_indicator(True, 20),
        performance=make_indicator(True, 40),
        assignments=make_indicator(False),
    )

    assert result["overall_risk_score"] == 30.0

    assert result["effective_weights"] == {
        "attendance": 0.5,
        "performance": 0.5,
    }

    assert result["unavailable_indicators"] == ["assignments"]


def test_only_attendance_available_gets_100_percent_weight():
    result = RiskScoringService.calculate(
        attendance=make_indicator(True, 50),
        performance=make_indicator(False),
        assignments=make_indicator(False),
    )

    assert result["overall_risk_score"] == 50.0

    assert result["effective_weights"] == {
        "attendance": 1.0,
    }


def test_no_available_indicators_returns_pending():
    result = RiskScoringService.calculate(
        attendance=make_indicator(False),
        performance=make_indicator(False),
        assignments=make_indicator(False),
    )

    assert result["available"] is False
    assert result["status"] == "Pending"
    assert result["overall_risk_score"] is None
    assert result["effective_weights"] == {}
    assert set(result["unavailable_indicators"]) == {
        "attendance",
        "performance",
        "assignments",
    }
def test_missing_performance_normalizes_attendance_and_assignments():
    result = RiskScoringService.calculate(
        attendance=make_indicator(True, 20),
        performance=make_indicator(False),
        assignments=make_indicator(True, 60),
    )

    assert abs(result["overall_risk_score"] - (100 / 3)) < 0.000001

    assert result["effective_weights"] == {
        "attendance": 2 / 3,
        "assignments": 1 / 3,
    }

