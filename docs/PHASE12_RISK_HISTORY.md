# Phase 12: Historical Risk Tracking

## What it does
Teachers can **record** a student's current risk as a snapshot, then see how risk
changed over time on the Student Risk Details page (new **Risk History** section):
a comparison with the last recorded assessment, two trend charts, and a table of every
recorded assessment. The existing risk calculation, weights and thresholds are untouched:
snapshots are produced by the existing `AcademicRiskService`.

## How snapshots are created
Only by an explicit teacher action (a POST button with CSRF protection):

* **Record Risk Assessment** (student page) records one student.
* **Record Risk Assessments** (Risk Report page) records every enrolled student in one
  transaction (all or nothing).

Nothing is recorded by viewing or refreshing a page, and there are no background jobs.
A new snapshot is skipped when every stored value is identical to the most recent one
(so double clicks and repeated recording add nothing). Several snapshots on the same day
are allowed when the results changed.

## Database: one new table, `risk_snapshots`
No existing table is altered.

| Column | Meaning |
|---|---|
| `id` | primary key |
| `student_id`, `course_id` | which student, in which course (foreign keys, `ON DELETE RESTRICT`) |
| `recorded_by_id` | the teacher who recorded it (foreign key, `RESTRICT`) |
| `recorded_at` | server local time when recorded |
| `overall_risk_score`, `classification` | the engine's overall result (`NULL` score and `Pending` together) |
| `attendance_`, `performance_`, `assignment_` + `percentage`, `risk_score`, `weight` | each indicator's value, its 0-100 risk, and the weight actually used after rescaling |
| `explanations_json` | the explanation strings at that time, as JSON |

* `NULL` means **unavailable at that time**. It is never stored as 0. A real 0 is stored as 0.
* Indicator availability is therefore the `NULL` / not `NULL` state of each percentage.
* Indexes: `(student_id, course_id, recorded_at)` for history lookups, and `course_id`.
* Snapshots belong to a student and course, not to the enrolment, so unenrolling a student never deletes history.

### Immutability (three layers)
1. The application only ever inserts. No update or delete code exists.
2. SQLite triggers refuse any `UPDATE` or `DELETE` on `risk_snapshots`.
3. `RESTRICT` foreign keys stop a student, course or teacher with history from being deleted, and the admin delete pages show a friendly message (history counts as a dependent record).

### Direction rules (do not invert)
* Overall risk score: **lower = improved**, higher = deteriorated. Differences under 0.05 (the displayed precision) are "unchanged".
* Indicator percentages: higher = improving, lower = declining.
* If either side is Pending/unavailable, **no direction is claimed**.
* "Current" in the comparison is the **live** calculation, compared with the most recent snapshot. The history table also shows the change between each pair of consecutive snapshots.

## MIGRATION (existing database): REQUIRED before starting the new version

The new code reads the new table. `python run.py` now refuses to start, with a clear
message, if the table is missing.

Windows, in the project folder, **with the server stopped**:

```
copy instance\academic_risk.db instance\academic_risk.manual_backup.db
python migrate_risk_snapshots.py
```

The script makes its own backup (`instance\academic_risk.backup_before_risk_snapshots_<date>_<time>.db`),
creates only the missing table, indexes and triggers in one transaction, checks that every
existing table has the same number of rows, and runs SQLite integrity checks. It is safe to
run again ("Migration already applied"). Then start the app with `python run.py`.

Fresh database (no data yet): `python init_db.py` also creates the table.

### Rolling back
Stop the server and copy a backup over the database:
```
copy instance\academic_risk.manual_backup.db instance\academic_risk.db
```
(Then run the previous version of the project, since the new code expects the table.)

## Manual verification checklist (browser)
1. Log in as a teacher, open a course Risk Report, click a student name.
2. Scroll to **Risk History**: it says no assessments recorded. Reload the page several times; nothing is recorded.
3. Click **Record Risk Assessment**. A success message appears, and one row is listed. Reload: still one row.
4. Click it again without changing anything: "Nothing has changed", still one row.
5. Change that student's attendance or marks, then record again: a second row appears, with a change badge. The first row's numbers are unchanged.
6. With two or more rows both charts show lines. Lower risk score must read as "Improved".
7. On the Risk Report page click **Record Risk Assessments**: confirm, then check the message counts.
8. Log in as a *different* teacher and paste the first teacher's student URL: you must see "Access denied".
9. As admin, try deleting a student or course that has history: it must be refused.
10. Disconnect the internet and reload the history: a note replaces the charts and the table still shows the data.

## Known limitations
* Times are the server's local time (naive, no time zone), like the existing session dates.
* The immutability triggers are SQLite-specific. If the database engine changes (Phase 17), equivalent protection must be added; the application-level and foreign-key protections still apply.
* Two truly simultaneous identical record requests could both pass the duplicate check. The button disables itself on submit, so this is unlikely and harmless (two equal rows).
* Charts need internet (Chart.js CDN, now pinned to 4.4.7, no integrity hash). A text fallback and the table remain. The existing Risk Report page still loads an unpinned Chart.js and is unchanged.
* Backup files accumulate in `instance\`; delete old ones yourself when satisfied.
* A student who is later unenrolled keeps their history, but it is only visible again if re-enrolled.
