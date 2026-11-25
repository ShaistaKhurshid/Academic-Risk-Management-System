
class PerformanceAnalyzer:
    """Calculates weighted assessment performance and academic risk."""

    RISK_THRESHOLD = 40.0

    @classmethod
    def analyze(cls, student_assessment_records):
        """
        Analyze a student's marks across assessments in one course.

        Ungraded assessments (None marks) are excluded.
        """

        records = list(student_assessment_records)

        graded_records = [
            record
            for record in records
            if record.marks_obtained is not None
        ]

        if not graded_records:
            return {
                "available": False,
                "status": "Pending",
                "graded_assessments": 0,
                "total_marks_obtained": 0.0,
                "total_max_marks": 0.0,
                "performance_percentage": None,
                "risk_score": None,
                "risk_flag": False,
            }

        total_marks_obtained = sum(
            record.marks_obtained
            for record in graded_records
        )

        total_max_marks = sum(
            record.assessment.max_marks
            for record in graded_records
        )

        performance_percentage = (
            total_marks_obtained / total_max_marks
        ) * 100

        risk_flag = performance_percentage < cls.RISK_THRESHOLD

        risk_score = max(
            0.0,
            min(
                100.0,
                (
                    (cls.RISK_THRESHOLD - performance_percentage)
                    / cls.RISK_THRESHOLD
                ) * 100,
            ),
        )

        return {
            "available": True,
            "status": "Calculated",
            "graded_assessments": len(graded_records),
            "total_marks_obtained": total_marks_obtained,
            "total_max_marks": total_max_marks,
            "performance_percentage": performance_percentage,
            "risk_score": risk_score,
            "risk_flag": risk_flag,
        }
