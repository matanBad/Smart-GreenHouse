"""
rule_engine.py -> Threshold Evaluation

Future PRD area: Threshold Evaluation.

Compares a validated reading against the min/max threshold rules in
data/threshold_rules.json and decides whether the reading is "normal",
"warning", or "critical".

Status logic (per threshold rule):
    - critical : value < min_value  OR  value > max_value
    - warning  : value is inside [min_value, max_value] but within
                 `warning_margin` of either boundary
    - normal   : value is comfortably inside the range

Security note: the status is computed only here, on the server. The client must
never supply reading_status — any client-provided status is ignored.

This layer does NOT raise alerts or trigger automation; it only classifies.
"""

from services.storage_service import read_json


def get_all_rules():
    """Return all configured threshold rules."""
    return read_json("threshold_rules.json", default=[])


def get_threshold_rule(sensor_type):
    """Return the threshold rule for a sensor type, or None if not configured."""
    for rule in get_all_rules():
        if rule.get("sensor_type") == sensor_type:
            return rule
    return None


def is_below_min(value, rule):
    """True if the value is below the rule's minimum."""
    return value < rule["min_value"]


def is_above_max(value, rule):
    """True if the value is above the rule's maximum."""
    return value > rule["max_value"]


def is_near_threshold(value, rule):
    """
    True if the value is inside the allowed range but within `warning_margin`
    of either boundary (the "warning band").
    """
    margin = rule.get("warning_margin", 0)
    # Inclusive of the margin boundary: a value sitting exactly `warning_margin`
    # away from a limit is still considered "near" (in the warning band).
    near_min = value <= rule["min_value"] + margin
    near_max = value >= rule["max_value"] - margin
    return near_min or near_max


def evaluate_reading_status(sensor_type, value):
    """
    Return "normal" | "warning" | "critical" for a value, or None if no
    threshold rule is configured for the sensor type.
    """
    rule = get_threshold_rule(sensor_type)
    if rule is None:
        return None

    if is_below_min(value, rule) or is_above_max(value, rule):
        return "critical"
    if is_near_threshold(value, rule):
        return "warning"
    return "normal"


def apply_threshold_evaluation(reading):
    """
    Evaluate a reading dict and return {"status", "rule"}.

    `status` is the computed reading_status, or None when no threshold rule
    exists for the reading's sensor_type (the caller must handle that case and
    must NOT store the reading as valid).
    """
    sensor_type = reading.get("sensor_type")
    value = reading.get("value")
    rule = get_threshold_rule(sensor_type)
    if rule is None:
        return {"status": None, "rule": None}
    return {"status": evaluate_reading_status(sensor_type, value), "rule": rule}
