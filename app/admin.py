"""Administrator pages: dashboard, students, teachers, courses, enrolment."""
from flask import Blueprint, render_template, abort, redirect, url_for, flash, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db, login_manager
from app.forms import StudentForm, TeacherForm, CourseForm, EnrolForm
from app.models import (User, Student, Course, Enrolment,
                        ROLE_ADMIN, ROLE_TEACHER)

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def only_admins():
    """Runs before EVERY route in this file, so no admin page can be forgotten."""
    if not current_user.is_authenticated:
        return login_manager.unauthorized()      # redirect to the login page
    if current_user.role != ROLE_ADMIN:
        abort(403)


@bp.route("/dashboard")
def dashboard():
    # Real counts from the database. Priority charts arrive in Milestone 3.
    return render_template(
        "admin/dashboard.html",
        total_students=Student.query.count(),
        total_teachers=User.query.filter_by(role=ROLE_TEACHER).count(),
        total_courses=Course.query.count(),
    )


# ===========================================================================
# Small helpers used by the routes below
# ===========================================================================

def describe_counts(counts):
    """{'attendance records': 3, 'follow-up records': 0}  ->  '3 attendance records'"""
    parts = [f"{number} {label}" for label, number in counts.items() if number > 0]
    return ", ".join(parts)


def get_teacher_or_404(user_id):
    """Load a user by id, but only if it is a TEACHER account.
    Administrator accounts cannot be edited or deactivated from the teacher pages."""
    user = db.get_or_404(User, user_id)
    if user.role != ROLE_TEACHER:
        abort(404)
    return user


def teacher_choices():
    """Dropdown options for 'Assigned teacher'. Value 0 means 'not assigned'.
    Only users with the teacher role are listed, so an admin id can never be chosen."""
    teachers = User.query.filter_by(role=ROLE_TEACHER).order_by(User.full_name).all()
    choices = [(0, "-- Not assigned --")]
    for teacher in teachers:
        label = teacher.full_name
        if not teacher.is_active:
            label += " (inactive)"
        choices.append((teacher.id, label))
    return choices


def teacher_is_assignable(teacher_id, current_teacher_id=None):
    """Server-side rule for assigning a teacher to a course.

    * None (no teacher)                      -> allowed
    * must exist and have the teacher role   -> otherwise refused
    * an INACTIVE teacher cannot be newly assigned. If the course already has
      that teacher (current_teacher_id), keeping them is not a new assignment.
    """
    if teacher_id is None:
        return True
    teacher = db.session.get(User, teacher_id)
    if teacher is None or teacher.role != ROLE_TEACHER:
        return False
    if teacher.is_active:
        return True
    return teacher_id == current_teacher_id


# ===========================================================================
# STUDENTS
# NOTE on names: in the URLs below, <student_id> is the DATABASE id (Student.id),
# not the college ID typed by the admin (Student.student_id).
# ===========================================================================

@bp.route("/students")
def student_list():
    students = Student.query.order_by(Student.student_id).all()
    return render_template("admin/students.html", students=students)


@bp.route("/students/add", methods=["GET", "POST"])
def student_add():
    form = StudentForm()
    if form.validate_on_submit():
        student = Student(student_id=form.student_id.data, name=form.name.data,
                          email=form.email.data, semester=form.semester.data)
        db.session.add(student)
        db.session.commit()
        flash(f"Student {student.name} was added.", "success")
        return redirect(url_for("admin.student_detail", student_id=student.id))
    return render_template("admin/student_form.html", form=form, heading="Add student",
                           cancel_url=url_for("admin.student_list"))


@bp.route("/students/<int:student_id>")
def student_detail(student_id):
    student = db.get_or_404(Student, student_id)
    enrolments = sorted(student.enrolments, key=lambda e: e.course.code)
    blockers = describe_counts(student.dependent_record_counts())
    return render_template("admin/student_detail.html", student=student,
                           enrolments=enrolments, blockers=blockers)


@bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def student_edit(student_id):
    student = db.get_or_404(Student, student_id)
    form = StudentForm(obj=student, editing_id=student.id)
    if form.validate_on_submit():
        student.student_id = form.student_id.data
        student.name = form.name.data
        student.email = form.email.data
        student.semester = form.semester.data
        db.session.commit()
        flash(f"Student {student.name} was updated.", "success")
        return redirect(url_for("admin.student_detail", student_id=student.id))
    return render_template("admin/student_form.html", form=form,
                           heading=f"Edit student {student.student_id}",
                           cancel_url=url_for("admin.student_detail", student_id=student.id))


@bp.route("/students/<int:student_id>/delete", methods=["POST"])
def student_delete(student_id):
    student = db.get_or_404(Student, student_id)
    blockers = describe_counts(student.dependent_record_counts())
    if blockers:
        # Students are kept for academic history. Deleting one would also delete
        # their attendance, marks, submissions and follow-ups, so it is refused.
        flash(f"Cannot delete {student.name}: this student still has {blockers}. "
              "Academic history is kept. (Enrolments can only be removed when "
              "no academic records exist.)", "danger")
        return redirect(url_for("admin.student_detail", student_id=student.id))
    name = student.name
    db.session.delete(student)
    db.session.commit()
    flash(f"Student {name} was deleted.", "success")
    return redirect(url_for("admin.student_list"))


# ===========================================================================
# TEACHER ACCOUNTS
# (Teachers are DEACTIVATED, never deleted, so their follow-up history is kept.)
# ===========================================================================

@bp.route("/teachers")
def teacher_list():
    teachers = User.query.filter_by(role=ROLE_TEACHER).order_by(User.full_name).all()
    return render_template("admin/teachers.html", teachers=teachers)


@bp.route("/teachers/add", methods=["GET", "POST"])
def teacher_add():
    form = TeacherForm()
    if form.validate_on_submit():
        teacher = User(full_name=form.full_name.data, email=form.email.data,
                       role=ROLE_TEACHER)
        teacher.set_password(form.password.data)       # stored as a hash
        db.session.add(teacher)
        db.session.commit()
        flash(f"Teacher account for {teacher.full_name} was created.", "success")
        return redirect(url_for("admin.teacher_list"))
    return render_template("admin/teacher_form.html", form=form, heading="Add teacher",
                           is_edit=False)


@bp.route("/teachers/<int:user_id>/edit", methods=["GET", "POST"])
def teacher_edit(user_id):
    teacher = get_teacher_or_404(user_id)
    form = TeacherForm(obj=teacher, editing_id=teacher.id)
    if form.validate_on_submit():
        teacher.full_name = form.full_name.data
        teacher.email = form.email.data
        if form.password.data:                         # blank = keep current password
            teacher.set_password(form.password.data)
        db.session.commit()
        flash(f"Teacher {teacher.full_name} was updated.", "success")
        return redirect(url_for("admin.teacher_list"))
    return render_template("admin/teacher_form.html", form=form,
                           heading=f"Edit teacher {teacher.full_name}", is_edit=True)


@bp.route("/teachers/<int:user_id>/toggle", methods=["POST"])
def teacher_toggle_active(user_id):
    teacher = get_teacher_or_404(user_id)
    teacher.is_active = not teacher.is_active
    db.session.commit()
    if teacher.is_active:
        flash(f"{teacher.full_name} was activated and can log in again.", "success")
    else:
        message = f"{teacher.full_name} was deactivated and can no longer log in."
        if teacher.courses:
            message += (f" They are still assigned to {len(teacher.courses)} course(s); "
                        "assign another teacher where needed.")
        flash(message, "warning")
    return redirect(url_for("admin.teacher_list"))


# ===========================================================================
# COURSES (the teacher is assigned here, on the course)
# ===========================================================================

@bp.route("/courses")
def course_list():
    courses = Course.query.order_by(Course.code).all()
    return render_template("admin/courses.html", courses=courses)


@bp.route("/courses/add", methods=["GET", "POST"])
def course_add():
    form = CourseForm()
    form.teacher_id.choices = teacher_choices()
    if form.validate_on_submit():
        teacher_id = form.teacher_id.data or None          # 0 -> None (not assigned)
        if teacher_is_assignable(teacher_id):
            course = Course(code=form.code.data, name=form.name.data, teacher_id=teacher_id)
            db.session.add(course)
            db.session.commit()
            flash(f"Course {course.code} was created.", "success")
            return redirect(url_for("admin.course_list"))
        form.teacher_id.errors = list(form.teacher_id.errors) + ["Choose an active teacher."]
    return render_template("admin/course_form.html", form=form, heading="Add course",
                           cancel_url=url_for("admin.course_list"))


@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def course_edit(course_id):
    course = db.get_or_404(Course, course_id)
    form = CourseForm(obj=course, editing_id=course.id)
    form.teacher_id.choices = teacher_choices()
    if request.method == "GET":
        form.teacher_id.data = course.teacher_id or 0      # pre-select current teacher
    if form.validate_on_submit():
        new_teacher_id = form.teacher_id.data or None
        if teacher_is_assignable(new_teacher_id, current_teacher_id=course.teacher_id):
            course.code = form.code.data
            course.name = form.name.data
            course.teacher_id = new_teacher_id
            db.session.commit()
            flash(f"Course {course.code} was updated.", "success")
            return redirect(url_for("admin.course_list"))
        form.teacher_id.errors = list(form.teacher_id.errors) + ["Choose an active teacher."]
    return render_template("admin/course_form.html", form=form,
                           heading=f"Edit course {course.code}",
                           cancel_url=url_for("admin.course_list"))


@bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    course = db.get_or_404(Course, course_id)
    blockers = describe_counts(course.dependent_record_counts())
    if blockers:
        flash(f"Cannot delete course {course.code}: it still has {blockers}. "
              "Academic history is kept.", "danger")
        return redirect(url_for("admin.course_list"))
    code = course.code
    db.session.delete(course)
    db.session.commit()
    flash(f"Course {code} was deleted.", "success")
    return redirect(url_for("admin.course_list"))


# ===========================================================================
# ENROLMENT (admin enrols students into a course, or removes them)
# ===========================================================================

@bp.route("/courses/<int:course_id>/enrol", methods=["GET", "POST"])
def course_enrol(course_id):
    course = db.get_or_404(Course, course_id)

    # Only students who are NOT already enrolled can be chosen. Because the form
    # only accepts ids from this list, duplicates and unknown ids are refused.
    enrolled_ids = [enrolment.student_id for enrolment in course.enrolments]
    available = (Student.query.filter(~Student.id.in_(enrolled_ids))
                 .order_by(Student.student_id).all())

    form = EnrolForm()
    form.student_ids.choices = [(s.id, f"{s.student_id} - {s.name}") for s in available]

    if form.validate_on_submit():
        added = 0
        for student_pk in form.student_ids.data:
            already = Enrolment.query.filter_by(student_id=student_pk,
                                                course_id=course.id).first()
            if already is None:
                db.session.add(Enrolment(student_id=student_pk, course_id=course.id))
                added += 1
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Could not enrol the students (duplicate enrolment).", "danger")
        else:
            flash(f"{added} student(s) enrolled in {course.code}.", "success")
        return redirect(url_for("admin.course_enrol", course_id=course.id))

    enrolments = sorted(course.enrolments, key=lambda e: e.student.student_id)
    rows = [{"enrolment": e, "records": describe_counts(e.record_counts())}
            for e in enrolments]
    return render_template("admin/course_enrol.html", course=course, form=form, rows=rows)


@bp.route("/courses/<int:course_id>/enrolments/<int:student_id>/remove", methods=["POST"])
def enrolment_remove(course_id, student_id):
    enrolment = Enrolment.query.filter_by(course_id=course_id,
                                          student_id=student_id).first_or_404()
    records = describe_counts(enrolment.record_counts())
    if records:
        flash(f"Cannot remove {enrolment.student.name} from {enrolment.course.code}: "
              f"this student has {records} in this course.", "danger")
    else:
        name, code = enrolment.student.name, enrolment.course.code
        db.session.delete(enrolment)
        db.session.commit()
        flash(f"{name} was removed from {code}.", "success")
    return redirect(url_for("admin.course_enrol", course_id=course_id))
