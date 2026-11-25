"""Records and reads historical risk snapshots (Phase 12).

Rules this service follows:
  * It only INSERTS snapshot rows. It never updates or deletes them.
  * The risk values come from the existing AcademicRiskService; no calculation is
    repeated here.
  * A new snapshot is skipped when it would be identical to the most recent one
    (so double clicks or repeated recording add nothing).
  * Recording nothing is not an error: the caller is told whether a row was created.
"""
from app import db
from app.models import Enrolment, RiskSnapshot
from app.services.academic_risk_service import AcademicRiskService
from app.services.risk_history_summary import (
    snapshot_values_from_report,
    snapshot_to_values,
    values_are_identical,
)


class RiskHistoryService:
    """Snapshot creation and retrieval for one student/course pair or a whole course."""

    @staticmethod
    def get_history(student_id, course_id):
        """All snapshots for this student in this course, oldest first."""
        return (
            RiskSnapshot.query
            .filter_by(student_id=student_id, course_id=course_id)
            .order_by(RiskSnapshot.recorded_at, RiskSnapshot.id)
            .all()
        )

    @staticmethod
    def get_latest(student_id, course_id):
        """The most recent snapshot, or None."""
        return (
            RiskSnapshot.query
            .filter_by(student_id=student_id, course_id=course_id)
            .order_by(RiskSnapshot.recorded_at.desc(), RiskSnapshot.id.desc())
            .first()
        )

    @staticmethod
    def _add_snapshot_if_changed(student_id, course_id, recorded_by_id):
        """Add (but do not commit) a snapshot unless it duplicates the latest one.

        Returns (snapshot, created). Raises ValueError, from AcademicRiskService,
        when the student or course does not exist or the student is not enrolled.
        """
        report = AcademicRiskService.generate_report(student_id, course_id)
        values = snapshot_values_from_report(report)

        latest = RiskHistoryService.get_latest(student_id, course_id)
        if latest is not None and values_are_identical(snapshot_to_values(latest), values):
            return latest, False

        snapshot = RiskSnapshot(
            student_id=student_id,
            course_id=course_id,
            recorded_by_id=recorded_by_id,
            **values,
        )
        db.session.add(snapshot)
        return snapshot, True

    @staticmethod
    def record_snapshot(student_id, course_id, recorded_by_id):
        """Record the student's CURRENT risk as a new snapshot.

        Returns (snapshot, created). created is False when nothing has changed
        since the most recent snapshot; `snapshot` is then that existing row.
        """
        try:
            snapshot, created = RiskHistoryService._add_snapshot_if_changed(
                student_id, course_id, recorded_by_id)
            if created:
                db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return snapshot, created

    @staticmethod
    def record_course_snapshots(course_id, recorded_by_id):
        """Record current risk for every student enrolled in the course, in ONE commit.

        Returns {"recorded": n, "unchanged": n, "total": n}. If anything fails
        nothing is saved.
        """
        enrolments = (
            Enrolment.query
            .filter_by(course_id=course_id)
            .order_by(Enrolment.student_id)
            .all()
        )
        recorded = unchanged = 0

        try:
            for enrolment in enrolments:
                _snapshot, created = RiskHistoryService._add_snapshot_if_changed(
                    enrolment.student_id, course_id, recorded_by_id)
                if created:
                    recorded += 1
                else:
                    unchanged += 1
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return {"recorded": recorded, "unchanged": unchanged, "total": len(enrolments)}
