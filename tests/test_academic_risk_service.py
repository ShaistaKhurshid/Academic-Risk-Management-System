
from datetime import date

from app.services.academic_risk_service import AcademicRiskService


def test_generates_complete_risk_report(app, build):
    with app.app_context():
        student = build.student()
        teacher = build.teacher()
        course = build.course(teacher=teacher)
        build.enrol(student, course)

        # Attendance: 2 attended out of 3 sessions.
        build.attendance(student, course, date(2026, 11, 1), "Present")
        build.attendance(student, course, date(2026, 11, 2), "Present (Late)")
        build.attendance(student, course, date(2026, 11, 3), "Absent")

        # Performance: 10 out of 20 marks.
        assessment = build.assessment(course, max_marks=20)
        build.marks(assessment, student, marks_obtained=10)

        # Assignments: 4 completed and 1 not submitted.
        for number in range(5):
            assignment = build.assignment(
                course,
                title=f"Assignment {number + 1}",
            )
            status = "Submitted" if number < 4 else "Not Submitted"
            build.submission(assignment, student, status)

        report = AcademicRiskService.generate_report(
            student.id,
            course.id,
        )

        assert report["student_id"] == student.id
        assert report["course_id"] == course.id

        assert report["attendance"]["available"] is True
        assert abs(
            report["attendance"]["attendance_percentage"] - 66.6666667
        ) < 0.001

        assert report["performance"]["available"] is True
        assert report["performance"]["performance_percentage"] == 50.0

        assert report["assignments"]["available"] is True
        assert report["assignments"]["completion_percentage"] == 80.0

        assert report["overall"]["available"] is True
        assert report["classification"] == "Low Risk"

        assert "Attendance risk" in report["risk_explanations"]
        assert "Assignment completion risk" in report["risk_explanations"]


def test_report_returns_pending_when_no_academic_data_exists(app, build):
    with app.app_context():
        student = build.student()
        teacher = build.teacher()
        course = build.course(teacher=teacher)
        build.enrol(student, course)

        report = AcademicRiskService.generate_report(
            student.id,
            course.id,
        )

        assert report["attendance"]["status"] == "Pending"
        assert report["performance"]["status"] == "Pending"
        assert report["assignments"]["status"] == "Pending"

        assert report["overall"]["status"] == "Pending"
        assert report["classification"] == "Pending"
        assert report["risk_explanations"] == []
        assert report["interventions"] == []


def test_report_normalizes_weights_when_assignment_data_is_pending(app, build):
    with app.app_context():
        student = build.student()
        teacher = build.teacher()
        course = build.course(teacher=teacher)
        build.enrol(student, course)

        # Attendance: 50%.
        build.attendance(student, course, date(2026, 11, 1), "Present")
        build.attendance(student, course, date(2026, 11, 2), "Absent")

        # Performance: 30%.
        assessment = build.assessment(course, max_marks=20)
        build.marks(assessment, student, marks_obtained=6)

        # No assignments: assignment indicator should remain Pending.
        report = AcademicRiskService.generate_report(
            student.id,
            course.id,
        )

        assert report["assignments"]["available"] is False
        assert report["overall"]["available"] is True

        weights = report["overall"]["effective_weights"]
        assert abs(weights["attendance"] - 0.5) < 0.000001
        assert abs(weights["performance"] - 0.5) < 0.000001

        assert "assignments" in report["overall"]["unavailable_indicators"]

import pytest


def test_rejects_student_not_enrolled_in_course(app, build):
    with app.app_context():
        student = build.student()
        teacher = build.teacher()
        course = build.course(teacher=teacher)

        with pytest.raises(
            ValueError,
            match="The student is not enrolled in this course.",
        ):
            AcademicRiskService.generate_report(
                student.id,
                course.id,
            )

def test_rejects_nonexistent_student(app, build):
    with app.app_context():
        teacher = build.teacher()
        course = build.course(teacher=teacher)

        with pytest.raises(ValueError, match="Student not found."):
            AcademicRiskService.generate_report(
                99999,
                course.id,
            )


def test_rejects_nonexistent_course(app, build):
    with app.app_context():
        student = build.student()

        with pytest.raises(ValueError, match="Course not found."):
            AcademicRiskService.generate_report(
                student.id,
                99999,
            )
