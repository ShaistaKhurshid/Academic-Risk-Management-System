
"""Teacher pages: assigned courses and attendance management."""

from datetime import date, datetime

from flask import (
    Blueprint, render_template, abort, flash, redirect, url_for, request,
    send_file,
)
from flask_login import current_user
from app import db, login_manager
from app.services.academic_risk_service import AcademicRiskService
from app.services.student_risk_detail_service import StudentRiskDetailService
from app.services.risk_history_service import RiskHistoryService
from app.services.risk_history_summary import build_history_view
from app.services.course_risk_report_service import build_course_risk_data
from app.services import report_export_service as exports

from app.forms import (
    AttendanceForm,
    AssessmentForm,
    MarksForm,
    AssignmentForm,
    AssignmentDeadlineForm,
    AssignmentSubmissionsForm,
)
from app.models import (
    Course,
    Student,
    Enrolment,
    Attendance,
    Assessment,
    StudentAssessment,
    Assignment,
    AssignmentSubmission,
    ROLE_TEACHER,
    ATTENDANCE_STATUSES,
)

bp = Blueprint("teacher", __name__, url_prefix="/teacher")


@bp.before_request
def only_teachers():
    """Runs before every route in this blueprint."""
    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    if current_user.role != ROLE_TEACHER:
        abort(403)


def get_owned_course(course_id):
    """Return a course only if it belongs to the logged-in teacher."""
    course = Course.query.get_or_404(course_id)

    if course.teacher_id != current_user.id:
        abort(403)

    return course


@bp.route("/dashboard")
def dashboard():
    """Show only courses assigned to the logged-in teacher."""
    courses = (
        Course.query
        .filter_by(teacher_id=current_user.id)
        .order_by(Course.code)
        .all()
    )

    return render_template("teacher/dashboard.html", courses=courses)

@bp.route("/courses/<int:course_id>/risk-report")
def risk_report(course_id):
    """Show academic risk reports for students in an owned course."""

    # Verify that this course belongs to the logged-in teacher.
    course = get_owned_course(course_id)

    # Phase 13: the per-student reports and summary counts are built by a
    # shared helper so the page and the PDF/Excel exports always agree.
    student_reports, risk_summary = build_course_risk_data(course)

    return render_template(
        "teacher/risk_report.html",
        course=course,
        student_reports=student_reports,
        risk_summary=risk_summary,
    )

@bp.route("/courses/<int:course_id>/students/<int:student_id>/risk")
def student_risk_detail(course_id, student_id):
    """Detailed risk profile for ONE student in ONE owned course.

    Access checks, in this order:
      1. logged in + teacher role   (blueprint before_request)
      2. the course belongs to the logged-in teacher (403 otherwise)
      3. the student is enrolled in THAT course (404 otherwise)
    Step 3 stops a teacher from reading any student by guessing ids (IDOR).
    """
    course = get_owned_course(course_id)

    enrolment = Enrolment.query.filter_by(
        course_id=course.id,
        student_id=student_id,
    ).first_or_404()

    try:
        detail = StudentRiskDetailService.generate_detail(
            enrolment.student_id,
            course.id,
        )
    except ValueError:
        abort(404)

    # Phase 12: stored snapshots (history) compared with the live calculation.
    snapshots = RiskHistoryService.get_history(enrolment.student_id, course.id)
    history = build_history_view(snapshots, detail["report"])

    return render_template(
        "teacher/student_risk_detail.html",
        detail=detail,
        course=course,
        student=enrolment.student,
        history=history,
    )


# --------------------------------------------------------------------------
# Phase 13: PDF / Excel exports. All three are READ-ONLY GET routes: they reuse
# the existing risk services, never write to the database and never create
# risk snapshots. They sit behind the same teacher/ownership checks as the pages.
# --------------------------------------------------------------------------
def _download(buffer, mimetype, filename):
    response = send_file(buffer, mimetype=mimetype, as_attachment=True,
                         download_name=filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"     # personal student data
    return response


@bp.route("/courses/<int:course_id>/risk-report/export.pdf")
def export_course_risk_pdf(course_id):
    """Download the Course Risk Report as a PDF (owned course only)."""
    course = get_owned_course(course_id)
    now = datetime.now()
    student_reports, risk_summary = build_course_risk_data(course)
    buffer = exports.build_course_pdf(course, student_reports, risk_summary, now)
    return _download(buffer, exports.PDF_MIME,
                     exports.course_report_filename(course, "pdf", now))


@bp.route("/courses/<int:course_id>/risk-report/export.xlsx")
def export_course_risk_excel(course_id):
    """Download the Course Risk Report as an Excel workbook (owned course only)."""
    course = get_owned_course(course_id)
    now = datetime.now()
    student_reports, risk_summary = build_course_risk_data(course)
    buffer = exports.build_course_xlsx(course, student_reports, risk_summary, now)
    return _download(buffer, exports.XLSX_MIME,
                     exports.course_report_filename(course, "xlsx", now))


@bp.route("/courses/<int:course_id>/students/<int:student_id>/risk/export.pdf")
def export_student_risk_pdf(course_id, student_id):
    """Download one student's risk report as a PDF.

    Same checks as the detail page: owned course (403), student enrolled in
    THAT course (404).
    """
    course = get_owned_course(course_id)

    enrolment = Enrolment.query.filter_by(
        course_id=course.id,
        student_id=student_id,
    ).first_or_404()

    try:
        detail = StudentRiskDetailService.generate_detail(
            enrolment.student_id,
            course.id,
        )
    except ValueError:
        abort(404)

    snapshots = RiskHistoryService.get_history(enrolment.student_id, course.id)
    history = build_history_view(snapshots, detail["report"])

    now = datetime.now()
    buffer = exports.build_student_pdf(detail, history, now)
    return _download(buffer, exports.PDF_MIME,
                     exports.student_report_filename(course, enrolment.student, now))


@bp.route(
    "/courses/<int:course_id>/students/<int:student_id>/risk/record",
    methods=["POST"],
)
def record_risk_assessment(course_id, student_id):
    """Save the student's CURRENT risk as an immutable snapshot (POST + CSRF only).

    Same access checks as the detail page: course ownership (403), then
    enrolment in that course (404). Nothing is saved when nothing has changed
    since the previous snapshot, so double clicks cannot create duplicates.
    """
    course = get_owned_course(course_id)

    enrolment = Enrolment.query.filter_by(
        course_id=course.id,
        student_id=student_id,
    ).first_or_404()

    try:
        snapshot, created = RiskHistoryService.record_snapshot(
            enrolment.student_id,
            course.id,
            current_user.id,
        )
    except ValueError:
        abort(404)

    if created:
        flash(
            f"Risk assessment recorded for {enrolment.student.name}: "
            f"{snapshot.classification}.",
            "success",
        )
    else:
        flash(
            "Nothing has changed since the last recorded assessment on "
            f"{snapshot.recorded_at.strftime('%d %b %Y %H:%M')}, "
            "so no new assessment was recorded.",
            "info",
        )

    return redirect(
        url_for(
            "teacher.student_risk_detail",
            course_id=course.id,
            student_id=enrolment.student_id,
        ) + "#risk-history"
    )


@bp.route("/courses/<int:course_id>/risk-report/record", methods=["POST"])
def record_course_risk_assessments(course_id):
    """Record a snapshot for every enrolled student in an owned course (POST + CSRF only)."""
    course = get_owned_course(course_id)

    result = RiskHistoryService.record_course_snapshots(course.id, current_user.id)

    if result["total"] == 0:
        flash("No students are enrolled in this course, so nothing was recorded.", "info")
    else:
        flash(
            f"Recorded {result['recorded']} new risk assessment(s). "
            f"{result['unchanged']} student(s) were unchanged since their last assessment.",
            "success",
        )

    return redirect(url_for("teacher.risk_report", course_id=course.id))


@bp.route("/courses/<int:course_id>/attendance", methods=["GET", "POST"])
def attendance(course_id):
    """Record or edit attendance for enrolled students in an owned course."""
    course = get_owned_course(course_id)

    students = (
        Student.query
        .join(Enrolment, Enrolment.student_id == Student.id)
        .filter(Enrolment.course_id == course.id)
        .order_by(Student.name)
        .all()
    )

    if not students:
        flash("No students are enrolled in this course yet.", "warning")

    form = AttendanceForm()

    if request.method == "GET":
        selected_date = date.today()


        date_text = request.args.get("date")
        if date_text:
            try:
                selected_date = date.fromisoformat(date_text)
            except ValueError:
                flash(
                    "Invalid attendance date. Today's date is selected.",
                    "warning"
                )

        form.session_date.data = selected_date

        existing_records = Attendance.query.filter_by(
            course_id=course.id,
            session_date=selected_date
        ).all()

        existing_by_student = {
            record.student_id: record.status
            for record in existing_records
        }

        for student in students:
            form.entries.append_entry({
                "student_id": str(student.id),
                "status": existing_by_student.get(student.id, "Present"),
            })

    if form.validate_on_submit():

        enrolled_ids = {student.id for student in students}

        try:
            submitted_ids = [
                int(entry.student_id.data)
                for entry in form.entries
            ]
        except (TypeError, ValueError):
            submitted_ids = []

        # Reject missing, duplicate, or non-enrolled student IDs.
        if (
            len(submitted_ids) != len(enrolled_ids)
            or len(set(submitted_ids)) != len(submitted_ids)
            or set(submitted_ids) != enrolled_ids
        ):
            flash(
                "Attendance entries are invalid. Please reload the page and try again.",
                "danger"
            )
            return render_template(
                "teacher/attendance.html",
                course=course,
                students=students,
                form=form,
            )

        selected_date = form.session_date.data

        existing_records = Attendance.query.filter_by(
            course_id=course.id,
            session_date=selected_date
        ).all()

        existing_by_student = {
            record.student_id: record
            for record in existing_records
        }

        for entry in form.entries:
            student_id = int(entry.student_id.data)
            status = entry.status.data

            if status not in ATTENDANCE_STATUSES:
                flash("Invalid attendance status.", "danger")
                return render_template(
                    "teacher/attendance.html",
                    course=course,
                    students=students,
                    form=form,
                )

            record = existing_by_student.get(student_id)

            if record:
                # Update the existing record instead of creating a duplicate.
                record.status = status
            else:
                db.session.add(Attendance(
                    student_id=student_id,
                    course_id=course.id,
                    session_date=selected_date,
                    status=status,
                ))

        db.session.commit()

        flash("Attendance saved successfully.", "success")

        return redirect(url_for(
            "teacher.attendance",
            course_id=course.id,
            date=selected_date.isoformat()
        ))

    return render_template(
        "teacher/attendance.html",
        course=course,
        students=students,
        form=form,
    )

@bp.route("/courses/<int:course_id>/assessments")
def assessments(course_id):
    """List assessments for a course owned by the logged-in teacher."""
    course = get_owned_course(course_id)

    assessments = (
        Assessment.query
        .filter_by(course_id=course.id)
        .order_by(Assessment.assessment_date.desc(), Assessment.title)
        .all()
    )

    return render_template(
        "teacher/assessments.html",
        course=course,
        assessments=assessments,
    )


@bp.route(
    "/courses/<int:course_id>/assessments/create",
    methods=["GET", "POST"],
)
def create_assessment(course_id):
    """Create an assessment for an owned course."""
    course = get_owned_course(course_id)
    form = AssessmentForm()

    if form.validate_on_submit():
        assessment = Assessment(
            course_id=course.id,
            title=form.title.data,
            max_marks=form.max_marks.data,
            assessment_date=form.assessment_date.data,
        )

        db.session.add(assessment)
        db.session.commit()

        flash("Assessment created successfully.", "success")

        return redirect(
            url_for("teacher.assessments", course_id=course.id)
        )

    return render_template(
        "teacher/assessment_form.html",
        course=course,
        form=form,
    )


@bp.route(
    "/assessments/<int:assessment_id>/marks",
    methods=["GET", "POST"],
)
def assessment_marks(assessment_id):
    """Enter or update marks for students in an owned course."""

    assessment = Assessment.query.get_or_404(assessment_id)
    course = get_owned_course(assessment.course_id)

    students = (
        Student.query
        .join(Enrolment, Enrolment.student_id == Student.id)
        .filter(Enrolment.course_id == course.id)
        .order_by(Student.name)
        .all()
    )

    existing_marks = {
        record.student_id: record
        for record in StudentAssessment.query.filter_by(
            assessment_id=assessment.id
        ).all()
    }

    form = MarksForm()

    if request.method == "GET":
        for student in students:
            record = existing_marks.get(student.id)
            form.entries.append_entry({
                "student_id": str(student.id),
                "marks_obtained": (
                    record.marks_obtained if record else None
                ),
            })

    if form.validate_on_submit():
        enrolled_ids = [student.id for student in students]

        try:
            submitted_ids = [
                int(entry.student_id.data)
                for entry in form.entries
            ]
        except (TypeError, ValueError):
            submitted_ids = []

        # Require exactly the enrolled students in the expected order.
        if submitted_ids != enrolled_ids:
            flash(
                "Invalid student entries. Please reload the page.",
                "danger",
            )
            return redirect(
                url_for(
                    "teacher.assessment_marks",
                    assessment_id=assessment.id,
                )
            )

        for entry in form.entries:
            student_id = int(entry.student_id.data)
            marks = entry.marks_obtained.data

            if marks is not None and marks > assessment.max_marks:
                flash(
                    f"Marks cannot exceed {assessment.max_marks}.",
                    "danger",
                )
                return render_template(
                    "teacher/assessment_marks.html",
                    course=course,
                    assessment=assessment,
                    students=students,
                    form=form,
                )

            record = existing_marks.get(student_id)

            if record:
                record.marks_obtained = marks
            elif marks is not None:
                db.session.add(
                    StudentAssessment(
                        assessment_id=assessment.id,
                        student_id=student_id,
                        marks_obtained=marks,
                    )
                )

        db.session.commit()

        flash("Marks saved successfully.", "success")

        return redirect(
            url_for(
                "teacher.assessment_marks",
                assessment_id=assessment.id,
            )
        )

    return render_template(
        "teacher/assessment_marks.html",
        course=course,
        assessment=assessment,
        students=students,
        form=form,
    )


@bp.route(
    "/courses/<int:course_id>/assignments",
    methods=["GET", "POST"],
)
def assignments(course_id):
    """List assignments for a course owned by the teacher."""
    course = get_owned_course(course_id)

    assignments = (
        Assignment.query
        .filter_by(course_id=course.id)
        .order_by(Assignment.id)
        .all()
    )

    return render_template(
        "teacher/assignments.html",
        course=course,
        assignments=assignments,
    )


@bp.route(
    "/courses/<int:course_id>/assignments/create",
    methods=["GET", "POST"],
)
def create_assignment(course_id):
    """Create up to five assignments for an owned course."""
    course = get_owned_course(course_id)

    assignment_count = Assignment.query.filter_by(
        course_id=course.id
    ).count()

    if assignment_count >= 5:
        flash(
            "This course already has five assignments.",
            "warning",
        )
        return redirect(
            url_for("teacher.assignments", course_id=course.id)
        )

    form = AssignmentForm()

    if form.validate_on_submit():
        assignment = Assignment(
            course_id=course.id,
            title=form.title.data,
            deadline=form.deadline.data,
            original_deadline=form.deadline.data,
        )

        db.session.add(assignment)
        db.session.commit()

        flash("Assignment created successfully.", "success")

        return redirect(
            url_for("teacher.assignments", course_id=course.id)
        )

    return render_template(
        "teacher/assignment_form.html",
        course=course,
        form=form,
    )

@bp.route(
    "/assignments/<int:assignment_id>/edit-deadline",
    methods=["GET", "POST"],
)
def edit_assignment_deadline(assignment_id):
    """Allow the course teacher to update an assignment deadline."""
    assignment = Assignment.query.get_or_404(assignment_id)

    # Verify that the logged-in teacher owns this assignment's course.
    course = get_owned_course(assignment.course_id)

    form = AssignmentDeadlineForm()

    if form.validate_on_submit():
        # Update only the current deadline.
        # Never overwrite the original deadline.
        assignment.deadline = form.deadline.data

        db.session.commit()

        flash("Assignment deadline updated successfully.", "success")

        return redirect(
            url_for("teacher.assignments", course_id=course.id)
        )

    # Display the existing current deadline in the form.
    if request.method == "GET":
        form.deadline.data = assignment.deadline

    return render_template(
        "teacher/assignment_deadline_form.html",
        course=course,
        assignment=assignment,
        form=form,
    )

@bp.route(
    "/assignments/<int:assignment_id>/submissions",
    methods=["GET", "POST"],
)
def assignment_submissions(assignment_id):
    """Record submission statuses for enrolled students."""
    assignment = Assignment.query.get_or_404(assignment_id)

    # Verify that the logged-in teacher owns this course.
    course = get_owned_course(assignment.course_id)

    # Get only students enrolled in this course.
    students = (
        Student.query
        .join(Enrolment, Enrolment.student_id == Student.id)
        .filter(Enrolment.course_id == course.id)
        .order_by(Student.name)
        .all()
    )

    form = AssignmentSubmissionsForm()

    if request.method == "GET":
        for student in students:
            existing_submission = AssignmentSubmission.query.filter_by(
                assignment_id=assignment.id,
                student_id=student.id,
            ).first()

            entry = form.submissions.append_entry()
            entry.student_id.data = str(student.id)
            entry.status.data = (
                existing_submission.status
                if existing_submission
                else "Not Submitted"
            )

    if form.validate_on_submit():
        enrolled_student_ids = {student.id for student in students}
        submitted_student_ids = set()

        for entry in form.submissions.entries:
            student_id = int(entry.student_id.data)

            # Reject duplicate or non-enrolled student IDs.
            if (
                student_id not in enrolled_student_ids
                or student_id in submitted_student_ids
            ):
                abort(400)

            submitted_student_ids.add(student_id)

            submission = AssignmentSubmission.query.filter_by(
                assignment_id=assignment.id,
                student_id=student_id,
            ).first()

            if submission is None:
                submission = AssignmentSubmission(
                    assignment_id=assignment.id,
                    student_id=student_id,
                )
                db.session.add(submission)

            submission.status = entry.status.data

        # Require an entry for every enrolled student.
        if submitted_student_ids != enrolled_student_ids:
            abort(400)

        db.session.commit()

        flash("Assignment submission statuses saved successfully.", "success")

        return redirect(
            url_for(
                "teacher.assignment_submissions",
                assignment_id=assignment.id,
            )
        )
    return render_template(
        "teacher/assignment_submissions.html",
        course=course,
        assignment=assignment,
        form=form,
        students_by_id={
            student.id: student
            for student in students
        },
    )