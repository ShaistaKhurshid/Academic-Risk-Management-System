# Phase 14: UI/UX Improvements

Templates and CSS only. No Python, database, risk-calculation, authorisation or export-generation code was changed.

## Design system
* `app/static/css/style.css`: CSS variables (navy `#1F3A5F` brand, risk colours, spacing, radius, shadow), Bootstrap 5 re-themed through its `--bs-*` variables, shared card, table, form, button, badge and stat-card styles, visible `:focus-visible` outlines, `prefers-reduced-motion` support.
* `app/templates/_components.html`: reusable macros `page_header`, `risk_badge`, `stat_card`, `empty_state`, `icon`.
* Risk is never shown by colour alone: every badge carries its text (Low Risk / Medium Risk / High Risk / Pending) plus an icon; indicator cards say "At risk" / "On track" / "Unavailable".

## Layout and navigation (`base.html`)
* Skip-to-content link, `<main>` landmark, `aria-current="page"` on the active link, labelled navigation landmarks.
* Responsive: the sidebar collapses behind a **Menu** button on phones.
* Sidebar links are all real routes for that role. Admin: Dashboard, Students, Teachers, Courses & Enrolment. Teacher: Dashboard, and for each of the teacher's OWN courses (`current_user.courses`) Risk Report, Attendance, Assessments, Assignments.
* Removed: greyed-out placeholders, "M2/M3/M4" badges, "Milestone" developer text. (Follow-ups and an admin "Risk Reports" page have no routes, so they are not linked.)
* Flash messages: consistent styles, dismissible, announced to screen readers (`role="alert"` for errors/warnings, `role="status"` otherwise).

## Pages restyled
Login; admin dashboard (stat cards + quick links); teacher dashboard (course cards); admin students / teachers / courses / enrolment / student detail / forms; teacher attendance, assessments, create assessment, marks, assignments, create assignment, edit deadline, submissions; error page.

### Course Risk Report
Five summary cards (Total, Low, Medium, High, **Pending**), distribution chart (now includes Pending), filter buttons with counts and a "no students match" message, one scannable row per student, export and record actions grouped in the header. Each student's "Why is this student flagged?", "Recommended Interventions" and "Unavailable indicators" are kept in three detail rows behind a **Show details** button (and an **Expand all details** button). Without JavaScript they stay visible. Row structure (four rows per student carrying `data-risk`) is unchanged, so the filters and the existing tests work as before.

### Student Risk Details
Overall score and classification header, indicator cards with progress bars and plain-language status, explanations and interventions side by side near the top, section jump links, full-width Risk Calculation table, then attendance, assessments, assignments and the unchanged Phase 12 history, charts and snapshot table.

## Known limitations / notes
* Bootstrap and Chart.js still load from the CDN, so the browser needs internet access.
* Visual checks were done with headless Chromium at 1366 px and 390 px widths; no real tablet/phone devices, and no screen-reader test.
* Tables scroll horizontally inside their card on very narrow screens.

## Existing behaviour noticed but NOT changed (for review)
* The assignments and submissions pages used to print flash messages themselves as well as the layout, so messages appeared twice. The duplicate block was removed from those two templates; the layout still shows each message once.
* The "Manage Assignment Submissions" table shows the student's internal database id in the "Student ID" column (`entry.student_id.data`), not the college ID such as S2026001. This is existing Phase 7 behaviour and was left as is.
* `tests/migrate_attendance_status.py` and `app/STAGE1_TEST_RESULTS.txt` are stray files (Phase 16 clean-up).
