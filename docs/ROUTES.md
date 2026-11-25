# Route naming table

Rules for everyone:
1. Endpoint name = `blueprint.function_name`. In templates and redirects always use
   `url_for('admin.student_list')`, never a typed URL.
2. Admin routes live in `app/admin.py`, teacher routes in `app/teacher.py`, shared
   reports in `app/reports.py`, login in `app/auth.py`.
3. Templates go in the matching folder: `templates/admin/`, `templates/teacher/`, ...
4. Any teacher route with a `course_id` must check that the course belongs to
   `current_user` (403 otherwise).
5. Any route that changes data must be POST (forms include the CSRF token).
6. Only the owner edits a route. Need a new route? Add it to this table first.

Owners: **M1** Member 1 (auth, students, courses) - **M2** Member 2 (attendance, marks) -
**M3** Member 3 (assignments, risk engine, follow-ups) - **M4** Member 4 (dashboards, UI, charts).

## Milestone 1 (built now)

| Endpoint | URL | Methods | Who | Owner |
|---|---|---|---|---|
| `auth.index` | `/` | GET | anyone (redirects) | M1 |
| `auth.login` | `/login` | GET, POST | anyone | M1 |
| `auth.logout` | `/logout` | POST | logged in | M1 |
| `admin.dashboard` | `/admin/dashboard` | GET | admin | M1 (M4 completes in Milestone 3) |
| `teacher.dashboard` | `/teacher/dashboard` | GET | teacher | M2 (M4 completes in Milestone 3) |

## Milestone 2, Stage 1 (built: admin side)

In URLs, `<student_id>` / `<course_id>` / `<user_id>` are DATABASE ids (`Student.id`,
`Course.id`, `User.id`), not the college student ID typed by the admin.
All of these need the **admin** role (enforced by `before_request` in `app/admin.py`).

| Endpoint | URL | Methods | Purpose |
|---|---|---|---|
| `admin.student_list` | `/admin/students` | GET | list students |
| `admin.student_add` | `/admin/students/add` | GET, POST | add student |
| `admin.student_detail` | `/admin/students/<int:student_id>` | GET | details, enrolled courses, delete button |
| `admin.student_edit` | `/admin/students/<int:student_id>/edit` | GET, POST | edit student |
| `admin.student_delete` | `/admin/students/<int:student_id>/delete` | POST | delete **only if no dependent records** |
| `admin.teacher_list` | `/admin/teachers` | GET | list teacher accounts |
| `admin.teacher_add` | `/admin/teachers/add` | GET, POST | create teacher (password hashed) |
| `admin.teacher_edit` | `/admin/teachers/<int:user_id>/edit` | GET, POST | edit teacher; blank password keeps old one |
| `admin.teacher_toggle_active` | `/admin/teachers/<int:user_id>/toggle` | POST | activate / deactivate (never delete) |
| `admin.course_list` | `/admin/courses` | GET | list courses with teacher and student count |
| `admin.course_add` | `/admin/courses/add` | GET, POST | create course and assign teacher |
| `admin.course_edit` | `/admin/courses/<int:course_id>/edit` | GET, POST | edit course / change teacher |
| `admin.course_delete` | `/admin/courses/<int:course_id>/delete` | POST | delete **only if no dependent records** |
| `admin.course_enrol` | `/admin/courses/<int:course_id>/enrol` | GET, POST | enrolled list + tick-box enrolment |
| `admin.enrolment_remove` | `/admin/courses/<int:course_id>/enrolments/<int:student_id>/remove` | POST | unenrol **only if no records in that course** |

Added to the original plan: `admin.student_delete`, `admin.course_delete`, `admin.enrolment_remove`.

## Milestone 2 (remaining, planned)

| Endpoint | URL | Methods | Who | Owner |
|---|---|---|---|---|
| `teacher.course_list` | `/teacher/courses` | GET | teacher | M2 |
| `teacher.course_detail` | `/teacher/courses/<int:course_id>` | GET | teacher (own course) | M2 |
| `teacher.attendance` | `/teacher/courses/<int:course_id>/attendance` | GET, POST | teacher (own course) | M2 |
| `teacher.assessment_list` | `/teacher/courses/<int:course_id>/assessments` | GET | teacher (own course) | M2 |
| `teacher.assessment_add` | `/teacher/courses/<int:course_id>/assessments/add` | GET, POST | teacher (own course) | M2 |
| `teacher.marks_entry` | `/teacher/assessments/<int:assessment_id>/marks` | GET, POST | teacher (own course) | M2 |
| `teacher.assignment_list` | `/teacher/courses/<int:course_id>/assignments` | GET | teacher (own course) | M3 |
| `teacher.assignment_add` | `/teacher/courses/<int:course_id>/assignments/add` | GET, POST | teacher (own course) | M3 |
| `teacher.submission_update` | `/teacher/assignments/<int:assignment_id>/submissions` | GET, POST | teacher (own course) | M3 |

## Milestone 3 and 4 (planned)

| Endpoint | URL | Methods | Who | Owner |
|---|---|---|---|---|
| `reports.course_risk_list` | `/reports/courses/<int:course_id>/risk` | GET | admin, or teacher of course | M3 |
| `reports.student_report` | `/reports/courses/<int:course_id>/students/<int:student_id>` | GET | admin, or teacher of course | M3 |
| `reports.priority_chart_data` | `/reports/api/priority-distribution` | GET (JSON) | logged in | M4 |
| `reports.attendance_chart_data` | `/reports/api/attendance-overview` | GET (JSON) | logged in | M4 |
| `teacher.followup_list` | `/teacher/courses/<int:course_id>/students/<int:student_id>/followups` | GET | teacher (own course) | M3 |
| `teacher.followup_add` | `/teacher/courses/<int:course_id>/students/<int:student_id>/followups/add` | GET, POST | teacher (own course) | M3 |

## Phase 11: Individual student risk details

Teacher only (blueprint `before_request`). Access checks run in this order: course ownership (403), then student enrolment in that course (404). `<student_id>` is the database id (`Student.id`).

| Endpoint | URL | Methods | Purpose |
|---|---|---|---|
| `teacher.student_risk_detail` | `/teacher/courses/<int:course_id>/students/<int:student_id>/risk` | GET | full risk profile for one student in one owned course |

## Phase 12: Historical risk tracking

Teacher only. Same access checks as the student detail page: course ownership (403), then enrolment in that course (404). The two POST routes also require a CSRF token and never accept GET.

| Endpoint | URL | Methods | Purpose |
|---|---|---|---|
| `teacher.student_risk_detail` | `/teacher/courses/<int:course_id>/students/<int:student_id>/risk` | GET | now also shows the **Risk History** section (comparison, charts, table) |
| `teacher.record_risk_assessment` | `/teacher/courses/<int:course_id>/students/<int:student_id>/risk/record` | POST | save ONE student's current risk as an immutable snapshot |
| `teacher.record_course_risk_assessments` | `/teacher/courses/<int:course_id>/risk-report/record` | POST | save a snapshot for EVERY enrolled student (one transaction; unchanged students are skipped) |

## Phase 13: PDF and Excel exports
All three are read-only GET downloads. They reuse the risk services, never write to the database and never create snapshots. Same access rules as the pages they belong to: logged-in teacher (403 for admins), course owned by that teacher (403 otherwise), student enrolled in that course (404 otherwise).

| Endpoint | URL | Method | What it does |
|---|---|---|---|
| `teacher.export_course_risk_pdf` | `/teacher/courses/<int:course_id>/risk-report/export.pdf` | GET | Course Risk Report as PDF |
| `teacher.export_course_risk_excel` | `/teacher/courses/<int:course_id>/risk-report/export.xlsx` | GET | Course Risk Report as Excel (sheets `Course Risk Report`, `Summary`) |
| `teacher.export_student_risk_pdf` | `/teacher/courses/<int:course_id>/students/<int:student_id>/risk/export.pdf` | GET | Individual Student Risk Report as PDF (includes Phase 12 history) |
