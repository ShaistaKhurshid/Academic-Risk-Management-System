"""Database models (10 tables). This file is shared by the whole team:
agree changes here BEFORE editing it, and tell everyone when you merge.

Delete rules used in this file (read once, then they are easy to remember):
  * Child rows that make no sense without their parent are deleted with the
    parent (ondelete="CASCADE" + cascade="all, delete-orphan").
      Example: deleting a Course deletes its enrolments, attendance, ...
  * Course.teacher_id uses SET NULL: deleting a teacher leaves the course
    in place, with no teacher assigned.
  * FollowUp.teacher_id uses RESTRICT: a teacher who wrote follow-ups cannot be
    deleted, so history is never lost. In the app we DEACTIVATE teachers
    (is_active = False) instead of deleting them.
  * RiskSnapshot rows (Phase 12) are immutable history. They use RESTRICT, so a
    student, course or teacher that has snapshots cannot be deleted, and database
    triggers refuse any UPDATE or DELETE on a snapshot row.
"""
import sqlite3
from datetime import date, datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, DDL, Index, UniqueConstraint, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash

from app import db

# ---------------------------------------------------------------------------
# Constants shared with the rest of the app
# ---------------------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"

ATTENDANCE_STATUSES = ["Present", "Absent", "Present (Late)"]
SUBMISSION_STATUSES = ["Submitted", "Not Submitted", "Late Submission", "Excused"]
RISK_CLASSIFICATIONS = ["Low Risk", "Medium Risk", "High Risk", "Pending"]


def _in_list(column_name, values):
    """Builds the SQL text:  column IN ('A', 'B', ...)  for a CheckConstraint."""
    quoted = ", ".join("'" + value + "'" for value in values)
    return f"{column_name} IN ({quoted})"


def normalize_email(value):
    """Emails are always stored stripped and in lower case, so
    "  Asha@College.EDU " and "asha@college.edu" are the same address."""
    if isinstance(value, str):
        return value.strip().lower()
    return value


# SQLite ignores foreign keys unless this is switched on for every connection.
@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ---------------------------------------------------------------------------
# 1. User (administrators AND teachers)
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_TEACHER)
    # False = account switched off (cannot log in) but history is kept.
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Courses this user teaches (empty for admins).
    courses = db.relationship("Course", back_populates="teacher")

    __table_args__ = (
        CheckConstraint(_in_list("role", [ROLE_ADMIN, ROLE_TEACHER]), name="ck_user_role"),
    )

    @validates("email")
    def _normalise_email(self, key, value):
        """Runs every time .email is set (forms, seed script, tests...)."""
        return normalize_email(value)

    def set_password(self, plain_password):
        # pbkdf2:sha256 works on every Python build (including Windows).
        self.password_hash = generate_password_hash(plain_password, method="pbkdf2:sha256")

    def check_password(self, plain_password):
        return check_password_hash(self.password_hash, plain_password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


# ---------------------------------------------------------------------------
# 2. Student
# ---------------------------------------------------------------------------
class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)                     # database key
    student_id = db.Column(db.String(20), nullable=False, unique=True)  # college ID, e.g. "S2026001"
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    semester = db.Column(db.String(20), nullable=False)             # e.g. "Semester 3"

    enrolments = db.relationship("Enrolment", back_populates="student",
                                 cascade="all, delete-orphan")
    attendance_records = db.relationship("Attendance", back_populates="student",
                                         cascade="all, delete-orphan")
    assessment_marks = db.relationship("StudentAssessment", back_populates="student",
                                       cascade="all, delete-orphan")
    submissions = db.relationship("AssignmentSubmission", back_populates="student",
                                  cascade="all, delete-orphan")
    follow_ups = db.relationship("FollowUp", back_populates="student",
                                 cascade="all, delete-orphan")

    @validates("email")
    def _normalise_email(self, key, value):
        return normalize_email(value)

    def dependent_record_counts(self):
        """How many rows depend on this student. Used to block deletion:
        a student with ANY of these must not be deleted (history is kept)."""
        return {
            "course enrolments": len(self.enrolments),
            "attendance records": len(self.attendance_records),
            "marks entries": len(self.assessment_marks),
            "assignment submissions": len(self.submissions),
            "follow-up records": len(self.follow_ups),
            "risk history snapshots": RiskSnapshot.query.filter_by(
                student_id=self.id).count(),
        }

    def __repr__(self):
        return f"<Student {self.student_id} {self.name}>"


# ---------------------------------------------------------------------------
# 3. Course  (the teacher is assigned HERE, not in Enrolment)
# ---------------------------------------------------------------------------
class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)     # e.g. "CS201"
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True)                           # one teacher per course

    teacher = db.relationship("User", back_populates="courses")
    enrolments = db.relationship("Enrolment", back_populates="course",
                                 cascade="all, delete-orphan")
    attendance_records = db.relationship("Attendance", back_populates="course",
                                         cascade="all, delete-orphan")
    assessments = db.relationship("Assessment", back_populates="course",
                                  cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="course",
                                  cascade="all, delete-orphan")
    follow_ups = db.relationship("FollowUp", back_populates="course",
                                 cascade="all, delete-orphan")

    def dependent_record_counts(self):
        """How many rows depend on this course. Used to block deletion."""
        return {
            "student enrolments": len(self.enrolments),
            "attendance records": len(self.attendance_records),
            "assessments": len(self.assessments),
            "assignments": len(self.assignments),
            "follow-up records": len(self.follow_ups),
            "risk history snapshots": RiskSnapshot.query.filter_by(
                course_id=self.id).count(),
        }

    def __repr__(self):
        return f"<Course {self.code}>"


# ---------------------------------------------------------------------------
# 4. Enrolment  (links one Student to one Course)
# ---------------------------------------------------------------------------
class Enrolment(db.Model):
    __tablename__ = "enrolments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)

    student = db.relationship("Student", back_populates="enrolments")
    course = db.relationship("Course", back_populates="enrolments")

    __table_args__ = (
        # A student can be enrolled in a course only once.
        UniqueConstraint("student_id", "course_id", name="uq_enrolment_student_course"),
    )

    def record_counts(self):
        """Academic records this student has IN THIS COURSE ONLY.
        If any count is above zero, the student must not be unenrolled."""
        sid, cid = self.student_id, self.course_id
        return {
            "attendance records": Attendance.query.filter_by(
                student_id=sid, course_id=cid).count(),
            "marks entries": StudentAssessment.query.join(
                Assessment, StudentAssessment.assessment_id == Assessment.id
            ).filter(StudentAssessment.student_id == sid,
                     Assessment.course_id == cid).count(),
            "assignment submissions": AssignmentSubmission.query.join(
                Assignment, AssignmentSubmission.assignment_id == Assignment.id
            ).filter(AssignmentSubmission.student_id == sid,
                     Assignment.course_id == cid).count(),
            "follow-up records": FollowUp.query.filter_by(
                student_id=sid, course_id=cid).count(),
        }


# ---------------------------------------------------------------------------
# 5. Attendance  (one row = one student, one course, one date)
# ---------------------------------------------------------------------------
class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)

    student = db.relationship("Student", back_populates="attendance_records")
    course = db.relationship("Course", back_populates="attendance_records")

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "session_date",
                         name="uq_attendance_student_course_date"),
        CheckConstraint(_in_list("status", ATTENDANCE_STATUSES), name="ck_attendance_status"),
    )
    # App rule (checked in the route, not the database): only record attendance
    # for a student who is enrolled in that course.


# ---------------------------------------------------------------------------
# 6. Assessment  (a test/quiz/exam created for a course)
# ---------------------------------------------------------------------------
class Assessment(db.Model):
    __tablename__ = "assessments"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    title = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    assessment_date = db.Column(db.Date, nullable=True)

    course = db.relationship("Course", back_populates="assessments")
    student_marks = db.relationship("StudentAssessment", back_populates="assessment",
                                    cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("max_marks > 0", name="ck_assessment_max_marks_positive"),
    )


# ---------------------------------------------------------------------------
# 7. StudentAssessment  (one student's marks in one assessment)
# ---------------------------------------------------------------------------
class StudentAssessment(db.Model):
    __tablename__ = "student_assessments"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id", ondelete="CASCADE"),
                              nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False)
    # NULL (None) means "not graded yet". It is NOT the same as 0 marks.
    marks_obtained = db.Column(db.Float, nullable=True)

    assessment = db.relationship("Assessment", back_populates="student_marks")
    student = db.relationship("Student", back_populates="assessment_marks")

    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", name="uq_marks_assessment_student"),
        CheckConstraint("marks_obtained IS NULL OR marks_obtained >= 0",
                        name="ck_marks_not_negative"),
    )
    # App rule: marks_obtained must also be <= assessment.max_marks. A database
    # CHECK cannot look at another table, so the route validates this.


# ---------------------------------------------------------------------------
# 8. Assignment
# ---------------------------------------------------------------------------
class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    title = db.Column(db.String(100), nullable=False)

    # Original deadline is retained when the teacher extends it.
    original_deadline = db.Column(db.Date, nullable=True)

    # Current deadline (can be extended by the teacher).
    deadline = db.Column(db.Date, nullable=False)
    course = db.relationship("Course", back_populates="assignments")
    submissions = db.relationship("AssignmentSubmission", back_populates="assignment",
                                  cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 9. AssignmentSubmission  (one student's status for one assignment)
# ---------------------------------------------------------------------------
class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submissions"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id", ondelete="CASCADE"),
                              nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Not Submitted")

    assignment = db.relationship("Assignment", back_populates="submissions")
    student = db.relationship("Student", back_populates="submissions")

    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
        CheckConstraint(_in_list("status", SUBMISSION_STATUSES), name="ck_submission_status"),
    )


# ---------------------------------------------------------------------------
# 10. FollowUp  (a teacher's note about one student in one course)
# ---------------------------------------------------------------------------
class FollowUp(db.Model):
    __tablename__ = "follow_ups"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"),
                          nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"),
                           nullable=False)
    follow_up_date = db.Column(db.Date, nullable=False, default=date.today)
    action_taken = db.Column(db.String(200), nullable=False)
    remarks = db.Column(db.Text, nullable=True)

    student = db.relationship("Student", back_populates="follow_ups")
    course = db.relationship("Course", back_populates="follow_ups")
    teacher = db.relationship("User")
    # App rule: the student must be enrolled in the course, and the teacher must
    # be the course's teacher. The follow-up route checks both.


# ---------------------------------------------------------------------------
# 11. RiskSnapshot  (Phase 12: an IMMUTABLE record of one risk calculation)
# ---------------------------------------------------------------------------
def _now():
    """Local server time, naive. Same convention as date.today() used elsewhere."""
    return datetime.now()


class RiskSnapshot(db.Model):
    """What the risk engine calculated for ONE student in ONE course at ONE moment.

    * Rows are only ever INSERTED. Nothing updates or deletes them: the app has no
      such code, and the SQLite triggers below refuse it even if someone tries.
    * A value of NULL means "this indicator was not available at the time"
      (for example no graded assessment yet). It is never the same as 0.
    * classification "Pending" always goes with overall_risk_score NULL.
    * *_percentage is the indicator value (attendance %, marks %, completion %).
      *_risk_score is that indicator's 0-100 risk. *_weight is the weight that was
      actually used after rescaling for unavailable indicators.
    * Snapshots are stored per student+course; they are NOT linked to Enrolment,
      so unenrolling a student never deletes history.
    """
    __tablename__ = "risk_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"),
                           nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="RESTRICT"),
                          nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"),
                               nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)

    overall_risk_score = db.Column(db.Float, nullable=True)
    classification = db.Column(db.String(20), nullable=False)

    attendance_percentage = db.Column(db.Float, nullable=True)
    attendance_risk_score = db.Column(db.Float, nullable=True)
    attendance_weight = db.Column(db.Float, nullable=True)

    performance_percentage = db.Column(db.Float, nullable=True)
    performance_risk_score = db.Column(db.Float, nullable=True)
    performance_weight = db.Column(db.Float, nullable=True)

    assignment_percentage = db.Column(db.Float, nullable=True)
    assignment_risk_score = db.Column(db.Float, nullable=True)
    assignment_weight = db.Column(db.Float, nullable=True)

    # JSON list of the explanation strings, e.g. ["Attendance risk"]
    explanations_json = db.Column(db.Text, nullable=False, default="[]")

    student = db.relationship("Student")
    course = db.relationship("Course")
    recorded_by = db.relationship("User")

    __table_args__ = (
        CheckConstraint(_in_list("classification", RISK_CLASSIFICATIONS),
                        name="ck_risk_snapshot_classification"),
        CheckConstraint("overall_risk_score IS NULL OR overall_risk_score >= 0",
                        name="ck_risk_snapshot_score_not_negative"),
        CheckConstraint("(classification = 'Pending') = (overall_risk_score IS NULL)",
                        name="ck_risk_snapshot_pending_has_no_score"),
        Index("ix_risk_snapshots_student_course_time",
              "student_id", "course_id", "recorded_at"),
        Index("ix_risk_snapshots_course", "course_id"),
    )

    def __repr__(self):
        return f"<RiskSnapshot student={self.student_id} course={self.course_id} {self.classification}>"


# SQLite triggers that make snapshots read-only at the DATABASE level. They are
# created together with the table (db.create_all) and by migrate_risk_snapshots.py.
RISK_SNAPSHOT_TRIGGER_SQL = {
    "trg_risk_snapshots_no_update": (
        "CREATE TRIGGER IF NOT EXISTS trg_risk_snapshots_no_update "
        "BEFORE UPDATE ON risk_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'risk_snapshots rows are immutable'); END"
    ),
    "trg_risk_snapshots_no_delete": (
        "CREATE TRIGGER IF NOT EXISTS trg_risk_snapshots_no_delete "
        "BEFORE DELETE ON risk_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'risk_snapshots rows are immutable'); END"
    ),
}

for _trigger_sql in RISK_SNAPSHOT_TRIGGER_SQL.values():
    event.listen(RiskSnapshot.__table__, "after_create",
                 DDL(_trigger_sql).execute_if(dialect="sqlite"))
