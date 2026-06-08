"""
threshold_service.py -> Threshold Management

Future PRD area: Threshold Management (System Administrator).

This service owns reading and updating the threshold rules stored in
data/threshold_rules.json. Keeping the logic here (rather than in app.py) means
the route layer stays thin and the validation / persistence rules live in one
place.

Security model for this stage (Prompt 6):
    - Updating thresholds is a privileged action. Only callers presenting the
      role "system_administrator" may update a rule. This is a demo-level guard
      ("demo admin mode") until full authentication / role-based permissions are
      implemented in a later prompt.
    - All numeric values and the sensor_type are validated on the server; the
      frontend is never trusted.

The Rule Engine always reads the *current* rules from threshold_rules.json, so a
saved update automatically applies to future readings without recalculating any
historical readings or alerts.
"""

from services.log_service import (
    log_invalid_threshold_update,
    log_threshold_rule_updated,
    log_unauthorized_threshold_update,
)
from services.storage_service import read_json, write_json

# The only role allowed to update thresholds in this stage.
ADMIN_ROLE = "system_administrator"

# Sensor types that have configurable threshold rules.
VALID_SENSOR_TYPES = ("temperature", "humidity", "soil_moisture", "light_intensity")

THRESHOLDS_FILE = "threshold_rules.json"


def _is_number(value):
    """True if value is a real number (and not a bool, which is an int subclass)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def get_all_thresholds():
    """Return all configured threshold rules."""
    return read_json(THRESHOLDS_FILE, default=[])


def get_threshold_by_sensor_type(sensor_type):
    """Return the threshold rule for a sensor type, or None if not configured."""
    for rule in get_all_thresholds():
        if rule.get("sensor_type") == sensor_type:
            return rule
    return None


def validate_threshold_update(sensor_type, min_value, max_value, warning_margin, role):
    """
    Validate a threshold update request.

    Returns a dict describing the outcome so the route can choose the right
    response and the right log entry:
        {
            "authorized":            bool,   # role is system_administrator
            "sensor_type_supported": bool,   # sensor_type is a known type
            "errors":                [str],  # numeric / logical problems
        }
    The update is allowed only when authorized and sensor_type_supported are
    True and errors is empty.
    """
    authorized = role == ADMIN_ROLE
    sensor_type_supported = sensor_type in VALID_SENSOR_TYPES

    errors = []
    if not _is_number(min_value):
        errors.append("min_value must be numeric")
    if not _is_number(max_value):
        errors.append("max_value must be numeric")
    if not _is_number(warning_margin):
        errors.append("warning_margin must be numeric")
    elif warning_margin < 0:
        errors.append("warning_margin must be greater than or equal to 0")

    # Only check the min/max relationship once both are confirmed numeric.
    if _is_number(min_value) and _is_number(max_value) and min_value >= max_value:
        errors.append("min_value must be lower than max_value")

    return {
        "authorized": authorized,
        "sensor_type_supported": sensor_type_supported,
        "errors": errors,
    }


def update_threshold_rule(sensor_type, min_value, max_value, warning_margin, role):
    """
    Update a single threshold rule and persist it.

    Only the rule matching `sensor_type` is changed; all other rules and every
    other field of the matched rule (rule_id, unit, severity_levels) are
    preserved. A successful change is logged. Returns the updated rule, or None
    if no rule exists for the sensor type.

    Callers must validate the request first (see validate_threshold_update).
    """
    rules = get_all_thresholds()
    old_rule = None
    updated_rule = None

    for rule in rules:
        if rule.get("sensor_type") == sensor_type:
            old_rule = dict(rule)  # snapshot before mutation, for the change log
            rule["min_value"] = min_value
            rule["max_value"] = max_value
            rule["warning_margin"] = warning_margin
            updated_rule = rule
            break

    if old_rule is None:
        return None

    write_json(THRESHOLDS_FILE, rules)
    create_threshold_change_log(sensor_type, old_rule, updated_rule, role)
    return updated_rule


def create_threshold_change_log(sensor_type, old_rule, new_rule, role):
    """Record a successful threshold change in the system logs."""
    return log_threshold_rule_updated(sensor_type, old_rule, new_rule, role)


def log_rejected_update(sensor_type, role, authorized, errors):
    """Log a rejected threshold update attempt (unauthorized or invalid)."""
    if not authorized:
        return log_unauthorized_threshold_update(sensor_type, role)
    return log_invalid_threshold_update(sensor_type, errors, role)
