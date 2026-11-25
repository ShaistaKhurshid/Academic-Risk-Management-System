"""PDF and Excel report generation (Phase 13).

Three reports are produced, all entirely in memory (BytesIO, no temp files):

  * build_course_pdf      Course Risk Report, PDF   (ReportLab)
  * build_course_xlsx     Course Risk Report, Excel (OpenPyXL)
  * build_student_pdf     Individual Student Risk Report, PDF (ReportLab)

IMPORTANT
  * Nothing here calculates risk. Every score, percentage, weight, explanation and
    classification comes from the reports the existing engine already produced
    (AcademicRiskService / StudentRiskDetailService / build_history_view).
  * Nothing here touches the database. These functions only format data that
    was passed in, so exporting is read-only by construction.
  * An unavailable indicator is shown as "Pending" / "Unavailable" (or an empty
    cell), NEVER as 0. An assessment without marks is "Not graded".
"""
import re
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

SYSTEM_NAME = "Academic Risk Management System"
PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXCEL_SHEET_NAME = "Course Risk Report"
EXCEL_SUMMARY_SHEET_NAME = "Summary"

PENDING = "Pending"
UNAVAILABLE = "Unavailable"
NOT_GRADED = "Not graded"

INDICATOR_LABELS = {
    "attendance": "Attendance",
    "performance": "Academic performance",
    "assignments": "Assignment completion",
}

# Colours (PDF + Excel hex without '#')
NAVY = "1F3A5F"
LIGHT_GREY = "F2F4F7"
CLASS_COLOURS = {          # (background, text)
    "Low Risk": ("D1E7DD", "0F5132"),
    "Medium Risk": ("FFF3CD", "664D03"),
    "High Risk": ("F8D7DA", "842029"),
    "Pending": ("E2E3E5", "41464B"),
}


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------
def safe_filename_part(text):
    """Letters, digits, '-' and '_' only, so a download name is always safe."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(text or "")).strip("_")
    return cleaned or "report"


def course_report_filename(course, extension, now):
    return (f"course_risk_report_{safe_filename_part(course.code)}_"
            f"{now.strftime('%Y%m%d')}.{extension}")


def student_report_filename(course, student, now):
    return (f"student_risk_report_{safe_filename_part(course.code)}_"
            f"{safe_filename_part(student.student_id)}_"
            f"{now.strftime('%Y%m%d')}.pdf")


def _pdf_text(value):
    """Escaped text for a ReportLab Paragraph.

    The built-in PDF fonts only cover Western European characters; anything
    else becomes '?' instead of an ugly black box.
    """
    text = "" if value is None else str(value)
    text = text.encode("cp1252", "replace").decode("cp1252")
    return escape(text)


def _pct(value, missing=PENDING):
    return missing if value is None else f"{value:.1f}%"


def _num(value, missing=PENDING):
    return missing if value is None else f"{value:.1f}"


def _weight(value):
    return "-" if value is None else f"{value * 100:.1f}%"


def _when(value, with_time=True):
    if value is None:
        return "-"
    return value.strftime("%d %b %Y %H:%M" if with_time else "%d %b %Y")


def _classification(report):
    value = report.get("classification")
    return value if value in CLASS_COLOURS else PENDING


def _overall_score(report):
    overall = report["overall"]
    return overall["overall_risk_score"] if overall["available"] else None


def _indicator_values(report):
    """(attendance %, performance %, assignment %) with None when unavailable."""
    def pick(key, value_key):
        result = report[key]
        return result[value_key] if result["available"] else None
    return (pick("attendance", "attendance_percentage"),
            pick("performance", "performance_percentage"),
            pick("assignments", "completion_percentage"))


def _unavailable_labels(report):
    return [INDICATOR_LABELS.get(key, key)
            for key in report["overall"].get("unavailable_indicators", [])]


def _direction_text(direction):
    return {
        "improved": "Improved (risk decreased)",
        "deteriorated": "Deteriorated (risk increased)",
        "unchanged": "Unchanged",
        "improving": "Improving",
        "declining": "Declining",
        "stable": "Stable",
    }.get(direction, "No direction (not comparable)")


# ---------------------------------------------------------------------------
# PDF building blocks
# ---------------------------------------------------------------------------
_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("RT", parent=_base["Title"], fontSize=18, leading=22,
                            textColor=colors.HexColor("#" + NAVY), spaceAfter=2),
    "subtitle": ParagraphStyle("RS", parent=_base["Heading2"], fontSize=13, leading=16,
                               textColor=colors.HexColor("#333333"), alignment=TA_CENTER,
                               spaceAfter=2),
    "meta": ParagraphStyle("RM", parent=_base["Normal"], fontSize=9, leading=12,
                           textColor=colors.HexColor("#555555"), alignment=TA_CENTER),
    "h2": ParagraphStyle("H2", parent=_base["Heading2"], fontSize=12.5, leading=15,
                         textColor=colors.HexColor("#" + NAVY), spaceBefore=12,
                         spaceAfter=5, keepWithNext=True),
    "h3": ParagraphStyle("H3", parent=_base["Heading3"], fontSize=10.5, leading=13,
                         spaceBefore=6, spaceAfter=3, keepWithNext=True),
    "body": ParagraphStyle("B", parent=_base["Normal"], fontSize=9, leading=12),
    "small": ParagraphStyle("S", parent=_base["Normal"], fontSize=8, leading=10.5,
                            textColor=colors.HexColor("#555555")),
    "cell": ParagraphStyle("C", parent=_base["Normal"], fontSize=8.5, leading=10.5),
    "cell_c": ParagraphStyle("CC", parent=_base["Normal"], fontSize=8.5, leading=10.5,
                             alignment=TA_CENTER),
    "head": ParagraphStyle("HD", parent=_base["Normal"], fontSize=8.5, leading=10.5,
                           textColor=colors.white, fontName="Helvetica-Bold",
                           alignment=TA_CENTER),
    "head_l": ParagraphStyle("HDL", parent=_base["Normal"], fontSize=8.5, leading=10.5,
                             textColor=colors.white, fontName="Helvetica-Bold"),
    "bullet": ParagraphStyle("BL", parent=_base["Normal"], fontSize=9, leading=12,
                             leftIndent=12, bulletIndent=2),
}


def P(text, style="body"):
    return Paragraph(_pdf_text(text), STYLES[style])


def _bullets(items, empty_text):
    if not items:
        return [Paragraph(f"<i>{_pdf_text(empty_text)}</i>", STYLES["body"])]
    return [Paragraph(_pdf_text(item), STYLES["bullet"], bulletText="•")
            for item in items]


def _table(rows, col_widths, header_rows=1, align_center_from=None,
           zebra=True, extra_styles=None):
    """A consistently styled table whose header row repeats on every page."""
    table = Table(rows, colWidths=col_widths, repeatRows=header_rows)
    style = [
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#" + NAVY)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C5CAD3")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if zebra:
        for index in range(header_rows, len(rows)):
            if (index - header_rows) % 2 == 1:
                style.append(("BACKGROUND", (0, index), (-1, index),
                              colors.HexColor("#" + LIGHT_GREY)))
    if extra_styles:
        style.extend(extra_styles)
    table.setStyle(TableStyle(style))
    return table


def _key_value_table(pairs, widths=(45 * mm, 135 * mm)):
    rows = [[P(key, "cell"), P(value, "cell")] for key, value in pairs]
    table = Table(rows, colWidths=widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#" + LIGHT_GREY)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C5CAD3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    return table


def _class_style(row_index, col_index, classification):
    background, text = CLASS_COLOURS[classification]
    return [("BACKGROUND", (col_index, row_index), (col_index, row_index),
             colors.HexColor("#" + background)),
            ("TEXTCOLOR", (col_index, row_index), (col_index, row_index),
             colors.HexColor("#" + text))]


def _class_cell(classification):
    _background, text = CLASS_COLOURS[classification]
    style = ParagraphStyle("CL", parent=STYLES["cell_c"], fontName="Helvetica-Bold",
                           textColor=colors.HexColor("#" + text))
    return Paragraph(_pdf_text(classification), style)


class _NumberedCanvas(pdf_canvas.Canvas):
    """Adds 'Page x of y' and a footer to every page."""

    footer_text = SYSTEM_NAME

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        width, _height = self._pagesize
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#777777"))
        self.setStrokeColor(colors.HexColor("#C5CAD3"))
        self.line(15 * mm, 13 * mm, width - 15 * mm, 13 * mm)
        self.drawString(15 * mm, 8.5 * mm, self.footer_text)
        self.drawRightString(width - 15 * mm, 8.5 * mm,
                             f"Page {self._pageNumber} of {total}")
        self.restoreState()


def _render_pdf(story, title):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=20 * mm,
        title=title, author=SYSTEM_NAME, subject=title,
    )
    document.build(story, canvasmaker=_NumberedCanvas)
    buffer.seek(0)
    return buffer


def _heading_block(report_title, generated_at):
    return [
        Paragraph(_pdf_text(SYSTEM_NAME), STYLES["title"]),
        Paragraph(_pdf_text(report_title), STYLES["subtitle"]),
        Paragraph(f"Generated on {_pdf_text(_when(generated_at))}", STYLES["meta"]),
        Spacer(1, 8),
    ]


def _course_info_pairs(course, extra=()):
    teacher = getattr(getattr(course, "teacher", None), "full_name", None)
    pairs = [
        ("Course name", course.name),
        ("Course identifier", course.code),
        ("Course teacher", teacher or "Not assigned"),
    ]
    pairs.extend(extra)
    return pairs


# ---------------------------------------------------------------------------
# 1. Course Risk Report - PDF
# ---------------------------------------------------------------------------
def build_course_pdf(course, student_reports, risk_summary, generated_at=None):
    """Return a BytesIO holding the Course Risk Report PDF."""
    generated_at = generated_at or datetime.now()
    story = _heading_block("Course Risk Report", generated_at)

    story.append(P("Course information", "h2"))
    story.append(_key_value_table(_course_info_pairs(course)))

    story.append(P("Risk summary", "h2"))
    labels = ["Total enrolled", "Low Risk", "Medium Risk", "High Risk", "Pending"]
    values = [risk_summary["total_students"], risk_summary["low_risk"],
              risk_summary["medium_risk"], risk_summary["high_risk"],
              risk_summary["pending"]]
    summary_rows = [[Paragraph(_pdf_text(label), STYLES["head"]) for label in labels],
                    [Paragraph(f"<b>{value}</b>", STYLES["cell_c"]) for value in values]]
    story.append(_table(summary_rows, [36 * mm] * 5, zebra=False))

    story.append(P("Student risk table", "h2"))
    if not student_reports:
        story.append(P("No students are enrolled in this course yet.", "body"))
    else:
        header = ["Student ID", "Student name", "Attendance", "Academic performance",
                  "Assignment completion", "Overall risk score", "Classification"]
        rows = [[Paragraph(_pdf_text(text), STYLES["head_l" if i < 2 else "head"])
                 for i, text in enumerate(header)]]
        extra = []
        for index, item in enumerate(student_reports, start=1):
            student, report = item["student"], item["report"]
            attendance, performance, assignments = _indicator_values(report)
            classification = _classification(report)
            rows.append([
                P(student.student_id, "cell"),
                P(student.name, "cell"),
                P(_pct(attendance), "cell_c"),
                P(_pct(performance), "cell_c"),
                P(_pct(assignments), "cell_c"),
                P(_num(_overall_score(report)), "cell_c"),
                _class_cell(classification),
            ])
            extra += _class_style(index, 6, classification)
        story.append(_table(
            rows,
            [22 * mm, 36 * mm, 22 * mm, 26 * mm, 26 * mm, 20 * mm, 28 * mm],
            extra_styles=extra))
        story.append(Spacer(1, 4))
        story.append(P(
            "Pending means there is not enough recorded data for that indicator "
            "(or for the overall score). Pending is never treated as zero. "
            "Risk bands: Low 0-29.99, Medium 30-59.99, High 60-100.", "small"))

        story.append(P("Risk explanations and recommended interventions", "h2"))
        for item in student_reports:
            student, report = item["student"], item["report"]
            block = [
                P(f"{student.name} ({student.student_id}) - {_classification(report)}",
                  "h3"),
                P("Risk explanations", "small"),
                *_bullets(report.get("risk_explanations"), "No active risk flags."),
                Spacer(1, 3),
                P("Recommended interventions", "small"),
                *_bullets(report.get("interventions"),
                          "No intervention currently recommended."),
            ]
            unavailable = _unavailable_labels(report)
            if unavailable:
                block.append(Spacer(1, 3))
                block.append(P("Unavailable indicators: " + ", ".join(unavailable),
                               "small"))
            block.append(Spacer(1, 6))
            story.append(KeepTogether(block))

    return _render_pdf(story, "Course Risk Report - " + str(course.code))


# ---------------------------------------------------------------------------
# 2. Course Risk Report - Excel
# ---------------------------------------------------------------------------
EXCEL_HEADERS = [
    ("Student ID", 14),
    ("Student Name", 26),
    ("Course Code", 13),
    ("Course Name", 28),
    ("Attendance (%)", 15),
    ("Academic Performance (%)", 17),
    ("Assignment Completion (%)", 17),
    ("Overall Risk Score", 15),
    ("Risk Classification", 17),
    ("Unavailable Indicators", 26),
    ("Risk Explanations", 60),
    ("Recommended Interventions", 60),
]
_THIN = Side(style="thin", color="C5CAD3")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _set_text(cell, value):
    """Store text so Excel can never treat it as a formula (e.g. a name '=1+1')."""
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"


def build_course_xlsx(course, student_reports, risk_summary, generated_at=None):
    """Return a BytesIO holding the Course Risk Report workbook."""
    generated_at = generated_at or datetime.now()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = EXCEL_SHEET_NAME

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=NAVY)
    for column, (title, width) in enumerate(EXCEL_HEADERS, start=1):
        cell = sheet.cell(row=1, column=column, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.row_dimensions[1].height = 32

    top = Alignment(vertical="top")
    top_wrap = Alignment(vertical="top", wrap_text=True)
    top_centre = Alignment(horizontal="center", vertical="top")

    for row_number, item in enumerate(student_reports, start=2):
        student, report = item["student"], item["report"]
        attendance, performance, assignments = _indicator_values(report)
        classification = _classification(report)
        values = [
            student.student_id, student.name, course.code, course.name,
            attendance, performance, assignments, _overall_score(report),
            classification,
            ", ".join(_unavailable_labels(report)) or "None",
            "\n".join(report.get("risk_explanations") or []) or "No active risk flags.",
            "\n".join(report.get("interventions") or [])
            or "No intervention currently recommended.",
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_number, column=column)
            # Unavailable numbers are written as the text "Pending" - never 0.
            if column in (5, 6, 7, 8) and value is None:
                _set_text(cell, PENDING)
                cell.alignment = top_centre
                cell.font = Font(italic=True, color="6C757D")
            elif column in (5, 6, 7, 8):
                cell.value = round(float(value), 4)
                cell.number_format = "0.0"
                cell.alignment = top_centre
            elif column == 9:
                _set_text(cell, value)
                background, text = CLASS_COLOURS[value]
                cell.fill = PatternFill("solid", fgColor=background)
                cell.font = Font(bold=True, color=text)
                cell.alignment = top_centre
            elif column in (11, 12):
                _set_text(cell, value)
                cell.alignment = top_wrap
            else:
                _set_text(cell, value)
                cell.alignment = top_wrap if column in (4, 10) else top
            cell.border = _BORDER

    last_row = max(1, len(student_reports) + 1)
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(EXCEL_HEADERS))}{last_row}"
    sheet.freeze_panes = "A2"
    sheet.sheet_view.zoomScale = 100
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = "1:1"

    # A small second sheet with the course details and the summary counts.
    summary = workbook.create_sheet(EXCEL_SUMMARY_SHEET_NAME)
    pairs = [("Report", "Course Risk Report"), ("System", SYSTEM_NAME),
             ("Generated", _when(generated_at))]
    pairs += _course_info_pairs(course)
    pairs += [("Total enrolled students", risk_summary["total_students"]),
              ("Low Risk", risk_summary["low_risk"]),
              ("Medium Risk", risk_summary["medium_risk"]),
              ("High Risk", risk_summary["high_risk"]),
              ("Pending", risk_summary["pending"])]
    for row_number, (key, value) in enumerate(pairs, start=1):
        key_cell = summary.cell(row=row_number, column=1, value=key)
        key_cell.font = Font(bold=True)
        key_cell.fill = PatternFill("solid", fgColor=LIGHT_GREY)
        key_cell.border = _BORDER
        value_cell = summary.cell(row=row_number, column=2)
        _set_text(value_cell, value)
        value_cell.alignment = Alignment(horizontal="left")
        value_cell.border = _BORDER
    summary.column_dimensions["A"].width = 26
    summary.column_dimensions["B"].width = 40

    workbook.active = 0
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------------
# 3. Individual Student Risk Report - PDF
# ---------------------------------------------------------------------------
def build_student_pdf(detail, history, generated_at=None):
    """Return a BytesIO holding the Individual Student Risk Report PDF.

    `detail` is StudentRiskDetailService.generate_detail(...);
    `history` is build_history_view(...) (Phase 12).
    """
    generated_at = generated_at or datetime.now()
    student, course, report = detail["student"], detail["course"], detail["report"]
    classification = _classification(report)
    story = _heading_block("Individual Student Risk Report", generated_at)

    # ---- Student and course ------------------------------------------------
    story.append(P("Student and course information", "h2"))
    story.append(_key_value_table([
        ("Student name", student.name),
        ("Student ID", student.student_id),
        ("Course name", course.name),
        ("Course identifier", course.code),
    ]))

    # ---- Current risk assessment ------------------------------------------
    attendance, performance, assignments = _indicator_values(report)
    story.append(P("Current risk assessment", "h2"))
    top_rows = [[P("Overall risk score", "head_l"), P("Risk classification", "head")],
                [P(_num(_overall_score(report)), "cell_c"), _class_cell(classification)]]
    story.append(_table(top_rows, [60 * mm, 60 * mm], zebra=False,
                        extra_styles=_class_style(1, 1, classification)))
    story.append(Spacer(1, 6))
    indicator_rows = [[P("Indicator", "head_l"), P("Value", "head"), P("Status", "head")]]
    for label, value, key in (("Attendance", attendance, "attendance"),
                              ("Academic performance", performance, "performance"),
                              ("Assignment completion", assignments, "assignments")):
        if value is None:
            status = "Unavailable (not enough data)"
        else:
            status = "At risk" if report[key]["risk_flag"] else "Not at risk"
        indicator_rows.append([P(label, "cell"), P(_pct(value), "cell_c"),
                               P(status, "cell_c")])
    story.append(_table(indicator_rows, [60 * mm, 40 * mm, 80 * mm]))
    story.append(Spacer(1, 3))
    story.append(P("An overall score of 0-29.99 is Low Risk, 30-59.99 Medium Risk and "
                   "60-100 High Risk. Higher means more risk.", "small"))

    # ---- Attendance --------------------------------------------------------
    attendance_detail = detail["attendance"]
    story.append(P("Attendance details", "h2"))
    story.append(P(
        f"Sessions recorded: {attendance_detail['total_sessions']}  |  "
        f"Present: {attendance_detail['present_count']}  |  "
        f"Present (Late): {attendance_detail['late_count']}  |  "
        f"Absent: {attendance_detail['absent_count']}  |  "
        f"Attended: {attendance_detail['attended_count']}", "body"))
    story.append(P("Present and Present (Late) both count as attended; Absent does not.",
                   "small"))
    story.append(Spacer(1, 4))
    if attendance_detail["sessions"]:
        rows = [[P("Session date", "head_l"), P("Status", "head"), P("Counted as attended", "head")]]
        for session in attendance_detail["sessions"]:
            rows.append([P(_when(session["date"], False), "cell"),
                         P(session["status"], "cell_c"),
                         P("Yes" if session["attended"] else "No", "cell_c")])
        story.append(_table(rows, [60 * mm, 60 * mm, 60 * mm]))
    else:
        story.append(P("No attendance has been recorded for this student.", "body"))

    # ---- Assessments -------------------------------------------------------
    assessment_detail = detail["assessments"]
    story.append(P("Assessment details", "h2"))
    if assessment_detail["rows"]:
        rows = [[P("Assessment", "head_l"), P("Date", "head"), P("Marks obtained", "head"),
                 P("Maximum marks", "head"), P("Result", "head")]]
        for row in assessment_detail["rows"]:
            if row["graded"]:
                obtained = f"{row['marks_obtained']:g}"
                result = _pct(row["percentage"], NOT_GRADED)
            else:
                obtained = NOT_GRADED
                result = NOT_GRADED
            rows.append([P(row["title"], "cell"), P(_when(row["date"], False), "cell_c"),
                         P(obtained, "cell_c"), P(f"{row['max_marks']:g}", "cell_c"),
                         P(result, "cell_c")])
        story.append(_table(rows, [52 * mm, 28 * mm, 34 * mm, 34 * mm, 32 * mm]))
        story.append(Spacer(1, 3))
        story.append(P(
            f"Graded: {assessment_detail['graded_count']} of "
            f"{assessment_detail['total_assessments']}. Assessments marked "
            f"'{NOT_GRADED}' are excluded from the calculation and are never treated "
            "as zero.", "small"))
    else:
        story.append(P("No assessments have been created for this course.", "body"))

    # ---- Assignments -------------------------------------------------------
    assignment_detail = detail["assignments"]
    story.append(P("Assignment details", "h2"))
    if assignment_detail["rows"]:
        rows = [[P("Assignment", "head_l"), P("Deadline", "head"), P("Status", "head")]]
        for row in assignment_detail["rows"]:
            rows.append([P(row["title"], "cell"), P(_when(row["deadline"], False), "cell_c"),
                         P(row["status_label"], "cell_c")])
        story.append(_table(rows, [80 * mm, 45 * mm, 55 * mm]))
        story.append(Spacer(1, 3))
        story.append(P(
            f"Submitted: {assignment_detail['submitted_count']}  |  "
            f"Late Submission: {assignment_detail['late_count']}  |  "
            f"Not Submitted: {assignment_detail['not_submitted_count']}  |  "
            f"Excused: {assignment_detail['excused_count']}  |  "
            f"No record: {assignment_detail['no_record_count']}", "body"))
    else:
        story.append(P("No assignments have been created for this course.", "body"))
    story.append(P(
        "Submitted (on time) and Late Submission count as completed. Not Submitted and "
        "Excused count as incomplete. 'No record' means no status has been saved and is "
        "not assumed to be incomplete.", "small"))
    if assignment_detail["pending_message"]:
        story.append(P(assignment_detail["pending_message"], "body"))

    # ---- Risk analysis -----------------------------------------------------
    story.append(P("Risk analysis", "h2"))
    rows = [[P(text, "head_l" if i == 0 else "head") for i, text in enumerate(
        ["Indicator", "Value", "Threshold", "Risk score", "Base weight",
         "Weight used", "Contribution"])]]
    for component in detail["components"]:
        available = component["available"]
        rows.append([
            P(component["label"], "cell"),
            P(_pct(component["value"], UNAVAILABLE), "cell_c"),
            P(f"below {component['threshold']:g}%", "cell_c"),
            P(_num(component["risk_score"], UNAVAILABLE), "cell_c"),
            P(_weight(component["base_weight"]), "cell_c"),
            P(_weight(component["effective_weight"]) if available else UNAVAILABLE,
              "cell_c"),
            P(_num(component["contribution"], UNAVAILABLE), "cell_c"),
        ])
    story.append(_table(rows, [38 * mm, 22 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm]))
    story.append(Spacer(1, 3))
    story.append(P(
        "Contribution = indicator risk score x weight used. When an indicator is "
        "unavailable its weight is shared among the available indicators, so the "
        "contributions add up to the overall score.", "small"))

    story.append(P("Risk explanations", "h3"))
    story.extend(_bullets(report.get("risk_explanations"), "No active risk flags."))
    story.append(P("Recommended interventions", "h3"))
    story.extend(_bullets(report.get("interventions"),
                          "No intervention currently recommended."))
    story.append(P("Unavailable indicators", "h3"))
    unavailable = _unavailable_labels(report)
    story.append(P(", ".join(unavailable) if unavailable else "None - all indicators "
                   "are available.", "body"))

    # ---- Historical progression -------------------------------------------
    story.extend(_history_flowables(history))

    return _render_pdf(story, f"Student Risk Report - {student.name}")


def _history_flowables(history):
    out = [P("Historical risk progression", "h2")]
    if not history or not history.get("has_history"):
        out.append(P(
            "No historical risk assessments have been recorded for this student in "
            "this course yet, so progress cannot be shown. A teacher can record one "
            "using 'Record Risk Assessment' on the student page.", "body"))
        return out

    since = history["since_last"]
    out.append(P(f"Comparison of the current (live) risk with the last recorded "
                 f"assessment of {_when(since['last_recorded_at'])}.", "small"))
    out.append(Spacer(1, 3))

    if since["sufficient"]:
        difference = since["difference"]
        rows = [
            [P(text, "head") for text in
             ["Previous score", "Current score", "Difference", "Direction"]],
            [P(f"{_num(since['previous_score'])} ({since['previous_classification']})",
               "cell_c"),
             P(f"{_num(since['current_score'])} ({since['current_classification']})",
               "cell_c"),
             P(f"{difference:+.1f}", "cell_c"),
             P(_direction_text(since["direction"]), "cell_c")],
        ]
        out.append(_table(rows, [48 * mm, 48 * mm, 30 * mm, 54 * mm], zebra=False))
        out.append(Spacer(1, 3))
        if since["classification_changed"]:
            out.append(P(f"Classification changed: {since['previous_classification']} "
                         f"to {since['current_classification']}.", "body"))
        else:
            out.append(P(f"Classification unchanged ({since['current_classification']}).",
                         "body"))
    else:
        out.append(P("Not enough comparable data to show improvement or deterioration. "
                     + (since.get("reason") or ""), "body"))
    out.append(P("A lower risk score means lower risk (improvement).", "small"))

    out.append(P("Indicator changes since the last recorded assessment", "h3"))
    rows = [[P(text, "head_l" if i == 0 else "head") for i, text in enumerate(
        ["Indicator", "Last recorded", "Current", "Change", "Trend (higher is better)"])]]
    for key in ("attendance", "performance", "assignments"):
        item = since["indicators"][key]
        change = "-" if item["difference"] is None else f"{item['difference']:+.1f}"
        rows.append([P(INDICATOR_LABELS[key], "cell"),
                     P(_pct(item["previous"], UNAVAILABLE), "cell_c"),
                     P(_pct(item["current"], UNAVAILABLE), "cell_c"),
                     P(change, "cell_c"),
                     P(_direction_text(item["direction"]), "cell_c")])
    out.append(_table(rows, [46 * mm, 30 * mm, 30 * mm, 24 * mm, 50 * mm]))

    out.append(P(f"Snapshot history ({history['count']} recorded, newest first)", "h3"))
    rows = [[P(text, "head_l" if i == 0 else "head") for i, text in enumerate(
        ["Recorded", "Classification", "Risk score", "Attendance", "Performance",
         "Assignments"])]]
    for row in history["rows"]:
        rows.append([P(_when(row["recorded_at"]), "cell"),
                     P(row["classification"], "cell_c"),
                     P(_num(row["overall_risk_score"]), "cell_c"),
                     P(_pct(row["attendance_percentage"], UNAVAILABLE), "cell_c"),
                     P(_pct(row["performance_percentage"], UNAVAILABLE), "cell_c"),
                     P(_pct(row["assignment_percentage"], UNAVAILABLE), "cell_c")])
    out.append(_table(rows, [38 * mm, 32 * mm, 24 * mm, 28 * mm, 30 * mm, 28 * mm]))
    return out
