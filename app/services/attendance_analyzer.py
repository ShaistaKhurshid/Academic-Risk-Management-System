
class AttendanceAnalyzer:
    """Calculates attendance percentage and attendance risk for a student."""

    ATTENDED_STATUSES = {"Present", "Present (Late)"}
    RISK_THRESHOLD = 75.0

    @classmethod
    def analyze(cls, attendance_records):
        """
        Analyze a student's attendance records for one course.

        Returns Pending when no attendance records are available.
        """

        records = list(attendance_records)
        total_sessions = len(records)

        if total_sessions == 0:
            return {
                "available": False,
                "status": "Pending",
                "total_sessions": 0,
                "classes_attended": 0,
                "attendance_percentage": None,
                "risk_score": None,
                "risk_flag": False,
            }

        classes_attended = sum(
            1
            for record in records
            if record.status in cls.ATTENDED_STATUSES
        )

        attendance_percentage = (
            classes_attended / total_sessions
        ) * 100

        risk_flag = attendance_percentage < cls.RISK_THRESHOLD

        risk_score = max(
            0.0,
            min(
                100.0,
                (
                    (cls.RISK_THRESHOLD - attendance_percentage)
                    / cls.RISK_THRESHOLD
                ) * 100,
            ),
        )

        return {
            "available": True,
            "status": "Calculated",
            "total_sessions": total_sessions,
            "classes_attended": classes_attended,
            "attendance_percentage": attendance_percentage,
            "risk_score": risk_score,
            "risk_flag": risk_flag,
        }
