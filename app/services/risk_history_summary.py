"""Pure helpers for historical risk tracking (Phase 12).

IMPORTANT: nothing here calculates risk. Scores, percentages, weights and
classifications always come from the existing engine (AcademicRiskService). These
functions only
  * turn an engine report into the values stored in a snapshot,
  * decide whether a new snapshot would add any information,
  * compare two sets of values (improved / deteriorated / unchanged),
  * prepare rows and chart data for the Risk History section.

There are no database or Flask imports, so everything is easy to unit test.

Direction rules (do not invert):
  * overall RISK score: LOWER is better.  decrease = improved, increase = deteriorated.
  * indicator PERCENTAGES (attendance, marks, assignment completion): HIGHER is
    better. increase = improving, decrease = declining.
  * a missing value (None) is "unavailable", never zero. If either side of a
    comparison is unavailable, no direction is claimed.
"""
import json

# Differences smaller than this are shown as "unchanged"/"stable". Scores are
# displayed with one decimal, so 0.05 is the smallest visible difference.
CHANGE_TOLERANCE = 0.05

# The indicators, in display order: (key, label, snapshot column prefix)
INDICATORS = [
    ("attendance", "Attendance", "attendance"),
    ("performance", "Academic performance", "performance"),
    ("assignments", "Assignment completion", "assignment"),
]

# Every value that describes one risk calculation. These match the
# RiskSnapshot column names (minus ids and the timestamp).
VALUE_FIELDS = (
    "overall_risk_score",
    "classification",
    "attendance_percentage", "attendance_risk_score", "attendance_weight",
    "performance_percentage", "performance_risk_score", "performance_weight",
    "assignment_percentage", "assignment_risk_score", "assignment_weight",
    "explanations_json",
)

_PERCENTAGE_COLUMN = {
    "attendance": "attendance_percentage",
    "performance": "performance_percentage",
    "assignments": "assignment_percentage",
}


# --------------------------------------------------------------------------
# Engine report  ->  snapshot values
# --------------------------------------------------------------------------
def snapshot_values_from_report(report):
    """Convert an AcademicRiskService report into snapshot column values.

    Unavailable indicators and a Pending overall result are stored as None.
    """
    attendance = report["attendance"]
    performance = report["performance"]
    assignments = report["assignments"]
    overall = report["overall"]
    weights = overall.get("effective_weights", {})

    def value(result, key):
        return result[key] if result["available"] else None

    return {
        "overall_risk_score": (
            overall["overall_risk_score"] if overall["available"] else None
        ),
        "classification": report["classification"],

        "attendance_percentage": value(attendance, "attendance_percentage"),
        "attendance_risk_score": value(attendance, "risk_score"),
        "attendance_weight": weights.get("attendance"),

        "performance_percentage": value(performance, "performance_percentage"),
        "performance_risk_score": value(performance, "risk_score"),
        "performance_weight": weights.get("performance"),

        "assignment_percentage": value(assignments, "completion_percentage"),
        "assignment_risk_score": value(assignments, "risk_score"),
        "assignment_weight": weights.get("assignments"),

        "explanations_json": json.dumps(list(report["risk_explanations"])),
    }


def snapshot_to_values(snapshot):
    """Read the comparable values from a stored snapshot (any object with attributes)."""
    return {field: getattr(snapshot, field) for field in VALUE_FIELDS}


def explanations_from_json(text):
    """Decode a stored explanations_json string. Never raises on bad data."""
    try:
        loaded = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return loaded if isinstance(loaded, list) else []


# --------------------------------------------------------------------------
# Duplicate detection
# --------------------------------------------------------------------------
def _same_value(first, second):
    if first is None or second is None:
        return first is None and second is None
    if isinstance(first, float) or isinstance(second, float):
        return round(float(first), 6) == round(float(second), 6)
    return first == second


def values_are_identical(first, second):
    """True when two sets of snapshot values contain exactly the same information.

    Used to avoid recording a new snapshot when nothing has changed since the
    previous one. Floats are compared to 6 decimal places.
    """
    return all(_same_value(first[field], second[field]) for field in VALUE_FIELDS)


# --------------------------------------------------------------------------
# Comparisons
# --------------------------------------------------------------------------
def _score_direction(difference):
    if abs(difference) < CHANGE_TOLERANCE:
        return "unchanged"
    return "improved" if difference < 0 else "deteriorated"


def _indicator_direction(difference):
    if abs(difference) < CHANGE_TOLERANCE:
        return "stable"
    return "improving" if difference > 0 else "declining"


def compare_indicator(previous_percentage, current_percentage):
    """Compare one indicator's percentage. HIGHER is better.

    direction is None (no claim) when either value is unavailable.
    """
    if previous_percentage is None or current_percentage is None:
        return {
            "previous": previous_percentage,
            "current": current_percentage,
            "difference": None,
            "direction": None,
        }
    difference = current_percentage - previous_percentage
    return {
        "previous": previous_percentage,
        "current": current_percentage,
        "difference": difference,
        "direction": _indicator_direction(difference),
    }


def compare_values(previous, current):
    """Compare two sets of snapshot values (previous -> current).

    Returns a dict. `sufficient` is False, with a `reason`, when the overall
    scores cannot be compared (a Pending side). In that case NO improvement or
    deterioration is claimed. Indicator comparisons are still included because an
    individual indicator may be comparable even when the overall score is not.
    """
    indicators = {
        key: compare_indicator(previous[_PERCENTAGE_COLUMN[key]],
                               current[_PERCENTAGE_COLUMN[key]])
        for key, _label, _prefix in INDICATORS
    }

    result = {
        "sufficient": False,
        "reason": None,
        "direction": None,
        "previous_score": previous["overall_risk_score"],
        "current_score": current["overall_risk_score"],
        "difference": None,
        "previous_classification": previous["classification"],
        "current_classification": current["classification"],
        "classification_changed": (
            previous["classification"] != current["classification"]
        ),
        "indicators": indicators,
    }

    if previous["overall_risk_score"] is None and current["overall_risk_score"] is None:
        result["reason"] = "Both assessments are Pending, so no score can be compared."
        return result
    if previous["overall_risk_score"] is None:
        result["reason"] = "The earlier assessment was Pending, so no score can be compared."
        return result
    if current["overall_risk_score"] is None:
        result["reason"] = "The later assessment is Pending, so no score can be compared."
        return result

    difference = current["overall_risk_score"] - previous["overall_risk_score"]
    result["sufficient"] = True
    result["difference"] = difference
    result["direction"] = _score_direction(difference)
    return result


# --------------------------------------------------------------------------
# What the Risk History section shows
# --------------------------------------------------------------------------
def build_history_view(snapshots, current_report):
    """Prepare everything the Risk History section needs.

    `snapshots` must be in chronological order (oldest first). They are plain
    stored records; `current_report` is the LIVE engine report (not stored).

    Returns:
      count        number of snapshots
      has_history  True when at least one snapshot exists
      rows         newest first, each with a `change` compared to the snapshot
                   before it (None for the very first snapshot)
      since_last   live current risk compared with the most recent snapshot, or
                   None when there is no history
      chart        chronological series for Chart.js (None = unavailable)
    """
    snapshots = list(snapshots)
    stored = [snapshot_to_values(snapshot) for snapshot in snapshots]

    chronological_rows = []
    for index, (snapshot, values) in enumerate(zip(snapshots, stored)):
        previous_values = stored[index - 1] if index > 0 else None
        chronological_rows.append({
            "recorded_at": snapshot.recorded_at,
            "classification": values["classification"],
            "overall_risk_score": values["overall_risk_score"],
            "attendance_percentage": values["attendance_percentage"],
            "performance_percentage": values["performance_percentage"],
            "assignment_percentage": values["assignment_percentage"],
            "explanations": explanations_from_json(values["explanations_json"]),
            "change": compare_values(previous_values, values) if previous_values else None,
        })

    since_last = None
    if stored:
        since_last = compare_values(stored[-1], snapshot_values_from_report(current_report))
        since_last["last_recorded_at"] = snapshots[-1].recorded_at

    chart = {
        "labels": [row["recorded_at"].strftime("%d %b %Y %H:%M")
                   for row in chronological_rows],
        "overall": [row["overall_risk_score"] for row in chronological_rows],
        "attendance": [row["attendance_percentage"] for row in chronological_rows],
        "performance": [row["performance_percentage"] for row in chronological_rows],
        "assignments": [row["assignment_percentage"] for row in chronological_rows],
    }

    return {
        "count": len(snapshots),
        "has_history": bool(snapshots),
        "rows": list(reversed(chronological_rows)),
        "since_last": since_last,
        "chart": chart,
    }
