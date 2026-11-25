"""Course-wide risk report data (shared by the report page and the exports).

Phase 13: this is the logic that used to live inside the ``risk_report`` view.
It was moved here unchanged so the web page, the PDF and the Excel file always
show exactly the same students, numbers and counts.

Nothing here calculates risk: every report comes from AcademicRiskService.
This module only reads data. It never writes to the database.
"""
from app.models import Student, Enrolment
from app.services.academic_risk_service import AcademicRiskService


def build_course_risk_data(course):
    """Return ``(student_reports, risk_summary)`` for every enrolled student.

    * ``student_reports`` is a list of ``{"student": Student, "report": dict}``
      ordered by student name.
    * ``risk_summary`` holds the total and the Low / Medium / High / Pending
      counts. Anything that is not Low, Medium or High is counted as Pending.
    """
    students = (
        Student.query
        .join(Enrolment, Enrolment.student_id == Student.id)
        .filter(Enrolment.course_id == course.id)
        .order_by(Student.name)
        .all()
    )

    student_reports = []

    risk_summary = {
        "total_students": len(students),
        "low_risk": 0,
        "medium_risk": 0,
        "high_risk": 0,
        "pending": 0,
    }

    for student in students:
        report = AcademicRiskService.generate_report(student.id, course.id)

        if report["classification"] == "Low Risk":
            risk_summary["low_risk"] += 1
        elif report["classification"] == "Medium Risk":
            risk_summary["medium_risk"] += 1
        elif report["classification"] == "High Risk":
            risk_summary["high_risk"] += 1
        else:
            risk_summary["pending"] += 1

        student_reports.append({
            "student": student,
            "report": report,
        })

    return student_reports, risk_summary
