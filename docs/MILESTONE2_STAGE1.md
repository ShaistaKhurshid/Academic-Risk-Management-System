# Milestone 2, Stage 1: what changed and why

Scope: student management, teacher accounts, course management, teacher assignment,
enrolment, plus the review decisions that apply now. **The database schema is unchanged.**

## Decisions from the Milestone 1 review

| # | Decision | Where it lives | Status |
|---|---|---|---|
| 1 | Normalise emails (strip + lower case) | `normalize_email()` and `@validates("email")` in `models.py`; form filters in `forms.py` | done |
| 2 | Permanent 8-hour sessions | `session.permanent = True` in `auth.login` | done |
| 3 | No unenrolment when records exist | `Enrolment.record_counts()` + `admin.enrolment_remove` | done |
| 4 | No casual delete of students/courses | `dependent_record_counts()` on Student and Course + the two delete routes | done |
| 5 | Teacher must be assigned to a course | teacher-side routes (attendance, marks...) | **next stage**: no teacher course routes exist yet |
| 6 | Student must be enrolled before records are saved | same | next stage |
| 7 | `marks_obtained <= max_marks` | marks route | next stage |
| 8 | Follow-up teacher = course teacher | follow-up route | next stage |
| 9 | Tests for untested constraints, seed, logout CSRF | `test_constraints.py`, `test_seed.py`, `test_auth_hardening.py` | done |

Admin-side teacher assignment is validated now (see below), because assigning a teacher
is part of this stage.

## Important code decisions (read these before editing)

**Email normalisation lives in the model.** `@validates("email")` runs every time an
email is assigned, so the admin forms, the seed script and tests all get the same
behaviour. Forms also normalise *before* checking duplicates, so `ASHA@x.com` is caught
as a duplicate of `asha@x.com`.

**Validation lives in the forms, not in the routes.** A method called `validate_<field>`
inside a form runs automatically (for example `validate_student_id`). Edit forms receive
`editing_id` so a record is not reported as a duplicate of itself.

**Teacher assignment is checked on the server** (`teacher_is_assignable` in `admin.py`):
- the dropdown only offers users with the teacher role, so an admin id is refused as "not a valid choice";
- an inactive teacher cannot be newly assigned;
- an already-assigned teacher who later became inactive may stay on the course while other fields are edited.

**"Dependent records" rules.** Each model has a small method returning counts:
- `Student.dependent_record_counts()` and `Course.dependent_record_counts()` decide deletion. Any count above zero blocks it, so attendance, marks, submissions and follow-up history are never lost by accident.
- `Enrolment.record_counts()` counts records for that student in that course only. Records in another course do not block unenrolment.
- A student who only has enrolments must be unenrolled first (allowed when no records exist), then deleted.
- The database cascade still exists (see `test_constraints.py`, which documents it). The **application** is what prevents the destructive delete, so never add a delete route without calling these methods.

**Teachers are deactivated, never deleted** (`admin.teacher_toggle_active`). A deactivated
teacher is logged out on their next request because `load_user` returns `None` for inactive users.

**Every POST button has a CSRF token.** Delete, remove and toggle buttons are small forms
containing `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.

**No template value is placed inside JavaScript.** The confirm dialogs use fixed text.

## Test-writing rule for the team

The test fixtures share one app context, so Flask-Login remembers the first user who
logged in. **Use only one logged-in client per test** (`admin_client` or `teacher_client`).
After a request changes data, re-read it with `fresh(Model, id)` rather than trusting a cached object.
