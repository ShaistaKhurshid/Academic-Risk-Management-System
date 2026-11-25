"""All Flask-WTF forms live in this one file.

FlaskForm automatically adds a hidden CSRF token field (form.hidden_tag()).
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    SelectField,
    SelectMultipleField,
    IntegerField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    Regexp,
    ValidationError,
    NumberRange,
    Optional,
)
from wtforms.widgets import CheckboxInput, ListWidget
from app.models import User, Student, Course, normalize_email
from wtforms import (
    DateField,
    FieldList,
    Form,
    FormField,
    HiddenField,
    SelectField,
)

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Log in")


# ---------------------------------------------------------------------------
# Milestone 2 forms (admin pages)
# ---------------------------------------------------------------------------

def strip_text(value):
    """Filter: remove spaces at the start and end of what was typed."""
    return value.strip() if isinstance(value, str) else value


# A simple "something@something.something" check (no extra package needed).
EMAIL_SHAPE = Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Enter a valid email address.")


class StudentForm(FlaskForm):
    """Used for both 'Add student' and 'Edit student'.

    editing_id is the database id of the student being edited (None when adding).
    It lets the duplicate checks ignore the student's own row.
    """
    student_id = StringField("Student ID", filters=[strip_text],
                             validators=[DataRequired(), Length(max=20)])
    name = StringField("Full name", filters=[strip_text],
                       validators=[DataRequired(), Length(max=100)])
    email = StringField("Email", filters=[normalize_email],
                        validators=[DataRequired(), Length(max=120), EMAIL_SHAPE])
    semester = StringField("Semester / class", filters=[strip_text],
                           validators=[DataRequired(), Length(max=20)])
    submit = SubmitField("Save student")

    def __init__(self, *args, editing_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing_id = editing_id

    # WTForms runs any method named validate_<fieldname> automatically.
    def validate_student_id(self, field):
        existing = Student.query.filter_by(student_id=field.data).first()
        if existing is not None and existing.id != self.editing_id:
            raise ValidationError("This student ID already exists.")

    def validate_email(self, field):
        existing = Student.query.filter_by(email=field.data).first()
        if existing is not None and existing.id != self.editing_id:
            raise ValidationError("A student with this email already exists.")


class TeacherForm(FlaskForm):
    """Add / edit a teacher account. On edit, leave the password blank to keep it."""
    full_name = StringField("Full name", filters=[strip_text],
                            validators=[DataRequired(), Length(max=100)])
    email = StringField("Email", filters=[normalize_email],
                        validators=[DataRequired(), Length(max=120), EMAIL_SHAPE])
    password = PasswordField("Password")
    submit = SubmitField("Save teacher")

    def __init__(self, *args, editing_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing_id = editing_id

    def validate_email(self, field):
        existing = User.query.filter_by(email=field.data).first()
        if existing is not None and existing.id != self.editing_id:
            raise ValidationError("An account with this email already exists.")

    def validate_password(self, field):
        if not field.data:
            if self.editing_id is None:
                raise ValidationError("A password is required for a new teacher.")
            return                      # editing: blank means "keep the old password"
        if len(field.data) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        if len(field.data) > 128:
            raise ValidationError("Password must be at most 128 characters.")


class CourseForm(FlaskForm):
    """Add / edit a course, including which teacher is assigned.

    teacher_id choices are filled in by the route (0 means "not assigned").
    """
    code = StringField("Course code", filters=[strip_text],
                       validators=[DataRequired(), Length(max=20)])
    name = StringField("Course name", filters=[strip_text],
                       validators=[DataRequired(), Length(max=100)])
    teacher_id = SelectField("Assigned teacher", coerce=int)
    submit = SubmitField("Save course")

    def __init__(self, *args, editing_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing_id = editing_id

    def validate_code(self, field):
        existing = Course.query.filter_by(code=field.data).first()
        if existing is not None and existing.id != self.editing_id:
            raise ValidationError("This course code already exists.")



class EnrolForm(FlaskForm):
    """Tick one or more students to enrol in a course."""
    student_ids = SelectMultipleField(
        "Students to enrol",
        coerce=int,
        validators=[
            DataRequired(message="Select at least one student.")
        ],
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False)
    )
    submit = SubmitField("Enrol selected students")

class AttendanceEntryForm(Form):
    """Attendance status for one student."""
    student_id = HiddenField()
    status = SelectField(
        "Status",
       choices=[
    ("Present", "Present"),
    ("Absent", "Absent"),
    ("Present (Late)", "Present (Late)"),
],
        validators=[DataRequired()]
    )


class AttendanceForm(FlaskForm):
    """Record attendance for enrolled students on a selected date."""
    session_date = DateField(
        "Attendance Date",
        format="%Y-%m-%d",
        validators=[DataRequired()]
    )

    entries = FieldList(FormField(AttendanceEntryForm))

    submit = SubmitField("Save Attendance")

class AssessmentForm(FlaskForm):
    """Create an assessment for a course."""

    title = StringField(
        "Assessment Title",
        filters=[strip_text],
        validators=[
            DataRequired(message="Assessment title is required."),
            Length(max=100),
        ],
    )

    max_marks = IntegerField(
        "Maximum Marks",
        validators=[
            DataRequired(message="Maximum marks are required."),
            NumberRange(
                min=1,
                message="Maximum marks must be at least 1.",
            ),
        ],
    )

    assessment_date = DateField(
        "Assessment Date",
        format="%Y-%m-%d",
        validators=[Optional()],
    )

    submit = SubmitField("Create Assessment")


class MarksEntryForm(Form):
    """Marks for one student in an assessment."""

    student_id = HiddenField()

    marks_obtained = IntegerField(
        "Marks Obtained",
        validators=[
            Optional(),
            NumberRange(
                min=0,
                message="Marks cannot be negative.",
            ),
        ],
    )



class MarksEntryForm(Form):
    """Marks for one student in an assessment."""

    student_id = HiddenField()

    marks_obtained = IntegerField(
        "Marks Obtained",
        validators=[
            Optional(),
            NumberRange(
                min=0,
                message="Marks cannot be negative.",
            ),
        ],
    )


class MarksForm(FlaskForm):
    """Enter or update marks for enrolled students."""

    entries = FieldList(FormField(MarksEntryForm))

    submit = SubmitField("Save Marks")


class AssignmentForm(FlaskForm):
    """Create an assignment for a course."""

    title = StringField(
        "Assignment Title",
        filters=[strip_text],
        validators=[
            DataRequired(message="Assignment title is required."),
            Length(max=100),
        ],
    )

    deadline = DateField(
        "Submission Deadline",
        format="%Y-%m-%d",
        validators=[DataRequired(message="Submission deadline is required.")],
    )

    submit = SubmitField("Create Assignment")


class AssignmentDeadlineForm(FlaskForm):
    """Update the submission deadline of an existing assignment."""

    deadline = DateField(
        "New Submission Deadline",
        format="%Y-%m-%d",
        validators=[
            DataRequired(message="Submission deadline is required."),
        ],
    )

    submit = SubmitField("Update Deadline")

class AssignmentSubmissionEntryForm(Form):
    """Store one student's assignment submission status."""

    student_id = HiddenField()
    
    status = SelectField(
        "Submission Status",
        choices=[
            ("Submitted", "Submitted"),
            ("Late Submission", "Late Submission"),
            ("Not Submitted", "Not Submitted"),
            ("Excused", "Excused"),
        ],
        validators=[DataRequired(message="Please select a status.")],
    )


class AssignmentSubmissionsForm(FlaskForm):
    """Manage submission statuses for multiple students."""

    submissions = FieldList(
        FormField(AssignmentSubmissionEntryForm),
        min_entries=0,
    )

    submit = SubmitField("Save Submission Statuses")
