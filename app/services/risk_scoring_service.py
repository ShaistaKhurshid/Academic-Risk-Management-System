
class RiskScoringService:
    """Combines available academic risk indicators using weighted scoring."""

    WEIGHTS = {
        "attendance": 0.40,
        "performance": 0.40,
        "assignments": 0.20,
    }

    @classmethod
    def calculate(cls, attendance, performance, assignments):
        """
        Calculate overall risk using available indicators only.

        Each analyzer result must contain:
        - available
        - risk_score
        """

        indicators = {
            "attendance": attendance,
            "performance": performance,
            "assignments": assignments,
        }

        available_indicators = {
            name: result
            for name, result in indicators.items()
            if result["available"]
        }

        if not available_indicators:
            return {
                "available": False,
                "status": "Pending",
                "overall_risk_score": None,
                "effective_weights": {},
                "unavailable_indicators": list(indicators.keys()),
            }

        available_weight_total = sum(
            cls.WEIGHTS[name]
            for name in available_indicators
        )

        effective_weights = {
            name: cls.WEIGHTS[name] / available_weight_total
            for name in available_indicators
        }

        overall_risk_score = sum(
            result["risk_score"] * effective_weights[name]
            for name, result in available_indicators.items()
        )

        unavailable_indicators = [
            name
            for name in indicators
            if name not in available_indicators
        ]

        return {
            "available": True,
            "status": "Calculated",
            "overall_risk_score": overall_risk_score,
            "effective_weights": effective_weights,
            "unavailable_indicators": unavailable_indicators,
        }
