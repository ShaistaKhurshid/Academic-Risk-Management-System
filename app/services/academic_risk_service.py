from app.models import (
    Attendance,
    StudentAssessment,
    Assessment,
    Assignment,
    Enrolment,
    Student,
    Course,
)
from app.services.attendance_analyzer import AttendanceAnalyzer
from app.services.performance_analyzer import PerformanceAnalyzer
from app.services.assignment_analyzer import AssignmentAnalyzer
from app.services.risk_scoring_service import RiskScoringService
from app.services.risk_classification_service import (
    RiskClassificationService,
)

class AcademicRiskService:
    """Builds a complete academic risk report for one student and course."""

    @staticmethod
    def generate_report(student_id, course_id):
        """Calculate and return an explainable academic risk report."""

                # Verify that the student exists.
        student = Student.query.filter_by(id=student_id).first()

        if student is None:
            raise ValueError("Student not found.")

        # Verify that the course exists.
        course = Course.query.filter_by(id=course_id).first()

        if course is None:
            raise ValueError("Course not found.")

        # Verify that the student is enrolled in this course.
        enrolment = Enrolment.query.filter_by(
            student_id=student_id,
            course_id=course_id,
        ).first()

        if enrolment is None:
            raise ValueError(
                "The student is not enrolled in this course."
            )

        # 1. Fetch attendance records for this student and course.
        attendance_records = Attendance.query.filter_by(
            student_id=student_id,
            course_id=course_id,
        ).all()

        # 2. Fetch graded and ungraded assessment records.
        student_assessment_records = (
            StudentAssessment.query
            .join(Assessment)
            .filter(
                StudentAssessment.student_id == student_id,
                Assessment.course_id == course_id,
            )
            .all()
        )

        # 3. Fetch assignments for this course.
        assignments = (
            Assignment.query
            .filter_by(course_id=course_id)
            .order_by(Assignment.id)
            .all()
        )

        # 4. Analyze each academic indicator.
        attendance_result = AttendanceAnalyzer.analyze(
            attendance_records
        )

        performance_result = PerformanceAnalyzer.analyze(
            student_assessment_records
        )

        assignment_result = AssignmentAnalyzer.analyze(
            assignments,
            student_id,
        )

        # 5. Calculate the weighted overall risk score.
        scoring_result = RiskScoringService.calculate(
            attendance=attendance_result,
            performance=performance_result,
            assignments=assignment_result,
        )

        # 6. Classify risk and generate explanations.
        classification_result = RiskClassificationService.classify(
            scoring_result,
            attendance_result,
            performance_result,
            assignment_result,
        )

        # 7. Return one consolidated report.
        return {
            "student_id": student_id,
            "course_id": course_id,
            "attendance": attendance_result,
            "performance": performance_result,
            "assignments": assignment_result,
            "overall": scoring_result,
            "classification": classification_result["classification"],
            "risk_explanations": classification_result["explanations"],
            "interventions": classification_result["interventions"],
        }
