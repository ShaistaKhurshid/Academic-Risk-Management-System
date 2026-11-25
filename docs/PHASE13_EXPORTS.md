# Phase 13: PDF and Excel Report Exports

## What it does
| Button | Page | Output |
|---|---|---|
| **Export PDF** | Course Risk Report | `course_risk_report_<COURSE>_<YYYYMMDD>.pdf` |
| **Export Excel** | Course Risk Report | `course_risk_report_<COURSE>_<YYYYMMDD>.xlsx` |
| **Download Student PDF** | Student Risk Details | `student_risk_report_<COURSE>_<STUDENTID>_<YYYYMMDD>.pdf` |

The export buttons on the course page appear only when the course has enrolled students (the routes themselves also work for an empty course).

## Contents
* **Course PDF**: heading and generation time, course information, summary counts (total, Low, Medium, High, Pending), student table (ID, name, attendance, performance, assignments, score, classification; header repeats on every page), then per-student explanations and interventions. Pages are numbered "Page x of y".
* **Course Excel**: sheet `Course Risk Report` (header row, filters, frozen header, number format `0.0`, colour-coded classification, wrapped explanation/intervention columns) and a small `Summary` sheet with course details and counts.
* **Student PDF**: student/course info, current assessment, attendance sessions, assessments (obtained, maximum, result), assignments, risk analysis (value, threshold, risk score, base weight, weight used, contribution), explanations, interventions, unavailable indicators, and Phase 12 history (previous vs current score, difference, Improved/Deteriorated/Unchanged, indicator changes, snapshot list). Without history a clear message is printed.

## Design
* `app/services/course_risk_report_service.py`: the per-student reports and counts that used to be inline in the `risk_report` view, moved unchanged so the page and exports always agree.
* `app/services/report_export_service.py`: ReportLab / OpenPyXL formatting only. It calculates nothing and touches no database.
* Three GET routes in `app/teacher.py` return in-memory files (`BytesIO`) with `send_file`; no temp files. `Cache-Control: no-store` is set because the files contain student data.
* No schema change. New dependencies: `reportlab`, `openpyxl` (and `pypdf`, used only by the tests).

## Data rules in exports
* Unavailable indicators are "Pending" (PDF/Excel) or "Unavailable", never 0. In Excel an unavailable number is the text `Pending`.
* An assessment with no marks is "Not graded". Assignment statuses keep their meanings; a missing record is "No record".
* Excel text beginning with `=` is stored as text, so it can never run as a formula.

## Known limitations
* PDFs use the built-in Helvetica font, so characters outside Western European (e.g. Devanagari names) print as `?`. The Excel file keeps them.
* The student PDF lists history as tables; the on-screen charts are not embedded.
* Report times are server local time.
