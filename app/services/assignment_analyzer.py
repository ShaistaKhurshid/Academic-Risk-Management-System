
class AssignmentAnalyzer:
    """Calculates assignment completion and assignment risk."""

    REQUIRED_ASSIGNMENTS = 5
    COMPLETED_STATUSES = {"Submitted", "Late Submission"}

    @classmethod
    def analyze(cls, assignments, student_id):
        """
        Analyze assignment completion for one student in one course.

        Assignment data is available only when exactly five assignments
        exist and every assignment has a saved status for the student.
        """

        assignments = list(assignments)

        if len(assignments) != cls.REQUIRED_ASSIGNMENTS:
            return cls._pending_result()

        statuses = []

        for assignment in assignments:
            submission = next(
                (
                    record
                    for record in assignment.submissions
                    if record.student_id == student_id
                ),
                None,
            )

            if submission is None:
                return cls._pending_result()

            statuses.append(submission.status)

        completed_count = sum(
            1
            for status in statuses
            if status in cls.COMPLETED_STATUSES
        )

        incomplete_count = cls.REQUIRED_ASSIGNMENTS - completed_count

        completion_percentage = (
            completed_count / cls.REQUIRED_ASSIGNMENTS
        ) * 100

        risk_score = 100.0 - completion_percentage

        return {
            "available": True,
            "status": "Calculated",
            "total_assignments": cls.REQUIRED_ASSIGNMENTS,
            "completed_count": completed_count,
            "incomplete_count": incomplete_count,
            "late_submission_count": statuses.count("Late Submission"),
            "excused_count": statuses.count("Excused"),
            "not_submitted_count": statuses.count("Not Submitted"),
            "completion_percentage": completion_percentage,
            "risk_score": risk_score,
            "risk_flag": completion_percentage < 100.0,
        }

    @staticmethod
    def _pending_result():
        """Return a consistent result when assignment data is incomplete."""

        return {
            "available": False,
            "status": "Pending",
            "total_assignments": 0,
            "completed_count": 0,
            "incomplete_count": 0,
            "late_submission_count": 0,
            "excused_count": 0,
            "not_submitted_count": 0,
            "completion_percentage": None,
            "risk_score": None,
            "risk_flag": False,
        }
