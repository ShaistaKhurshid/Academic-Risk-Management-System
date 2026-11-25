
class RiskClassificationService:
    """Classifies overall academic risk and identifies interventions."""

    LOW_RISK_MAX = 30.0
    HIGH_RISK_MIN = 60.0

    @classmethod
    def classify(cls, scoring_result, attendance, performance, assignments):
        """Classify overall risk and generate explanations."""

        if not scoring_result["available"]:
            return {
                "classification": "Pending",
                "explanations": [],
                "interventions": [],
            }

        score = scoring_result["overall_risk_score"]

        if score < cls.LOW_RISK_MAX:
            classification = "Low Risk"
        elif score < cls.HIGH_RISK_MIN:
            classification = "Medium Risk"
        else:
            classification = "High Risk"

        indicators = {
            "attendance": (
                attendance,
                "Attendance risk",
                "Review attendance and arrange counselling if needed.",
            ),
            "performance": (
                performance,
                "Academic performance risk",
                "Provide additional academic support and review assessment performance.",
            ),
            "assignments": (
                assignments,
                "Assignment completion risk",
                "Create an assignment completion plan and review pending work.",
            ),
        }

        explanations = []
        interventions = []

        for name, (result, explanation, intervention) in indicators.items():
            if not result["available"]:
                continue

            if result["risk_flag"]:
                explanations.append(explanation)
                interventions.append(intervention)

        if len(explanations) >= 2:
            interventions.append(
                "Consider an individual academic intervention meeting."
            )

        return {
            "classification": classification,
            "explanations": explanations,
            "interventions": interventions,
        }
