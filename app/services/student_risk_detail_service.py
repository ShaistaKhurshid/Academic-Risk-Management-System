"""Builds everything the student risk detail page needs for ONE student in ONE course."""
from app.models import (
    Student,
    Course,
    Attendance,
    Assessment,
    StudentAssessment,
    Assignment,
    AssignmentSubmission,
)
from app.services.academic_risk_service import AcademicRiskService
from app.services.student_risk_summary import (
    summarise_attendance,
    summarise_assessments,
    summarise_assignments,
    build_components,
)


class StudentRiskDetailService:
    """Combines the existing risk report with record-level breakdowns."""

    @staticmethod
    def generate_detail(student_id, course_id):
        """Return a dictionary describing one student's risk in one course.

        Raises ValueError (from AcademicRiskService) if the student or course
        does not exist or the student is not enrolled in the course.
        """
        # The existing engine does all risk calculations and also validates
        # that the student exists and is enrolled in this course.
        report = AcademicRiskService.generate_report(student_id, course_id)

        student = Student.query.filter_by(id=student_id).first()
        course = Course.query.filter_by(id=course_id).first()

        # Attendance for this student in THIS course only.
        attendance_records = (
            Attendance.query
            .filter_by(student_id=student_id, course_id=course_id)
            .all()
        )

        # Every assessment in the course (graded or not) and this student's marks.
        assessments = (
            Assessment.query
            .filter_by(course_id=course_id)
            .order_by(Assessment.id)
            .all()
        )
        marks_by_assessment_id = {
            record.assessment_id: record
            for record in (
                StudentAssessment.query
                .join(Assessment, StudentAssessment.assessment_id == Assessment.id)
                .filter(
                    StudentAssessment.student_id == student_id,
                    Assessment.course_id == course_id,
                )
                .all()
            )
        }

        # Every assignment in the course and this student's submission statuses.
        assignments = (
            Assignment.query
            .filter_by(course_id=course_id)
            .order_by(Assignment.id)
            .all()
        )
        submissions_by_assignment_id = {
            submission.assignment_id: submission
            for submission in (
                AssignmentSubmission.query
                .join(Assignment,
                      AssignmentSubmission.assignment_id == Assignment.id)
                .filter(
                    AssignmentSubmission.student_id == student_id,
                    Assignment.course_id == course_id,
                )
                .all()
            )
        }

        return {
            "student": student,
            "course": course,
            "report": report,
            "components": build_components(report),
            "attendance": summarise_attendance(attendance_records),
            "assessments": summarise_assessments(
                assessments, marks_by_assessment_id),
            "assignments": summarise_assignments(
                assignments, submissions_by_assignment_id),
        }
