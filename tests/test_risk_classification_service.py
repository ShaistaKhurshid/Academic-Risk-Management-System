
from app.services.risk_classification_service import (
    RiskClassificationService,
)


def make_indicator(available=True, risk_flag=False):
    return {
        "available": available,
        "risk_flag": risk_flag,
    }


def make_scoring_result(score):
    return {
        "available": True,
        "overall_risk_score": score,
    }


def test_low_risk_classification():
    result = RiskClassificationService.classify(
        make_scoring_result(20),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )

    assert result["classification"] == "Low Risk"


def test_medium_risk_classification():
    result = RiskClassificationService.classify(
        make_scoring_result(45),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )

    assert result["classification"] == "Medium Risk"


def test_high_risk_classification():
    result = RiskClassificationService.classify(
        make_scoring_result(70),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )

    assert result["classification"] == "High Risk"


def test_risk_classification_boundaries():
    assert RiskClassificationService.classify(
        make_scoring_result(29.99),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )["classification"] == "Low Risk"

    assert RiskClassificationService.classify(
        make_scoring_result(30),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )["classification"] == "Medium Risk"

    assert RiskClassificationService.classify(
        make_scoring_result(59.99),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )["classification"] == "Medium Risk"

    assert RiskClassificationService.classify(
        make_scoring_result(60),
        make_indicator(),
        make_indicator(),
        make_indicator(),
    )["classification"] == "High Risk"


def test_no_available_indicators_returns_pending():
    result = RiskClassificationService.classify(
        {
            "available": False,
            "overall_risk_score": None,
        },
        make_indicator(False),
        make_indicator(False),
        make_indicator(False),
    )

    assert result["classification"] == "Pending"
    assert result["explanations"] == []
    assert result["interventions"] == []


def test_individual_risk_flags_are_reported():
    result = RiskClassificationService.classify(
        make_scoring_result(20),
        make_indicator(risk_flag=True),
        make_indicator(risk_flag=False),
        make_indicator(risk_flag=True),
    )

    assert result["classification"] == "Low Risk"
    assert len(result["explanations"]) == 2
    assert len(result["interventions"]) == 3


def test_multiple_risks_recommend_intervention_meeting():
    result = RiskClassificationService.classify(
        make_scoring_result(70),
        make_indicator(risk_flag=True),
        make_indicator(risk_flag=True),
        make_indicator(risk_flag=False),
    )

    assert any(
        "individual academic intervention meeting" in item.lower()
        for item in result["interventions"]
    )


def test_unavailable_indicator_is_not_flagged():
    result = RiskClassificationService.classify(
        make_scoring_result(20),
        make_indicator(available=False, risk_flag=True),
        make_indicator(risk_flag=False),
        make_indicator(risk_flag=False),
    )

    assert result["explanations"] == []
    assert result["interventions"] == []
