"""
alert_service.py -> Alerts and Recommended Actions

PRD area: Alerts and Notifications.

Creates, stores, and manages alerts when the rule engine flags a reading as
"warning" or "critical", and exposes them to the dashboard.

Security model:
    - Alerts are NEVER created from client input. They are produced only here,
      after server-side threshold evaluation.
    - Severity is derived from the reading_status computed by the rule engine,
      not from anything the client sends.

Out of scope for this prompt: simulated automation, threshold editing, auth.
"""

import uuid
from datetime import datetime, timezone

from models.alert_model import make_alert
from services.storage_service import append_json, read_json, write_json

ALERTS_FILE = "alerts.json"

# Recommended operator response keyed by alert_type (sensor_type + direction).
RECOMMENDED_ACTIONS = {
    "temperature_too_high": "Check ventilation status and monitor greenhouse heat level.",
    "temperature_too_low": "Review heating needs or check cold-condition protection.",
    "humidity_too_high": "Check air circulation response and monitor humidity levels.",
    "humidity_too_low": "Monitor air moisture and review greenhouse humidity conditions.",
    "soil_moisture_too_low": "Monitor irrigation response and check soil dryness.",
    "soil_moisture_too_high": "Review watering schedule and check for over-irrigation.",
    "light_intensity_too_low": "Check artificial lighting response and monitor light exposure.",
    "light_intensity_too_high": "Review shading or light exposure conditions.",
}

# Critical first, then warning. Used to order active alerts.
_SEVERITY_RANK = {"critical": 0, "warning": 1}


def _now_iso():
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _new_alert_id():
    """Generate a unique alert id."""
    return "ALERT-" + uuid.uuid4().hex[:12]


def _alert_direction(value, rule):
    """
    Decide whether a flagged value is "too_low" or "too_high".

    Out-of-range values use the breached boundary; in-range (warning) values use
    the boundary they are nearest to within warning_margin.
    """
    min_value = rule["min_value"]
    max_value = rule["max_value"]
    margin = rule.get("warning_margin", 0)

    if value < min_value:
        return "too_low"
    if value > max_value:
        return "too_high"
    # Inside the range -> warning band. Pick the boundary it is approaching.
    if value <= min_value + margin:
        return "too_low"
    return "too_high"


def get_alert_type(sensor_type, direction):
    """Build the alert_type, e.g. ("temperature", "too_high") -> temperature_too_high."""
    return f"{sensor_type}_{direction}"


def get_recommended_action(sensor_type, alert_type, severity):
    """
    Return the recommended operator action for an alert.

    Keyed by alert_type (which already encodes sensor_type + direction). Severity
    is accepted for interface completeness and future tuning.
    """
    return RECOMMENDED_ACTIONS.get(
        alert_type, "Review sensor conditions and respond as needed."
    )


def _build_message(sensor_name, severity, direction, value, unit, rule):
    """Compose a clear, human-readable alert message."""
    name = sensor_name or "Sensor"
    if direction == "too_high":
        limit = rule["max_value"]
        boundary = "maximum"
        verb = "exceeded" if severity == "critical" else "is approaching"
    else:
        limit = rule["min_value"]
        boundary = "minimum"
        verb = "dropped below" if severity == "critical" else "is approaching"
    return f"{name} reading {value}{unit} {verb} the {boundary} threshold of {limit}{unit}."


def create_alert(reading, rule, severity):
    """
    Create and persist an alert for a warning/critical reading.

    `reading` is the stored reading dict, `rule` is the matching threshold rule,
    and `severity` is the rule-engine reading_status ("warning" | "critical").
    Returns the stored alert. Callers must only invoke this for warning/critical.
    """
    # Lazy import avoids a circular import (sensor_service <-> alert flow).
    from services.sensor_service import get_sensor_by_id

    sensor = get_sensor_by_id(reading.get("sensor_id")) or {}
    value = reading.get("value")
    sensor_type = reading.get("sensor_type")
    direction = _alert_direction(value, rule)
    alert_type = get_alert_type(sensor_type, direction)
    sensor_name = sensor.get("sensor_name")

    alert = make_alert(
        alert_id=_new_alert_id(),
        sensor_id=reading.get("sensor_id"),
        reading_id=reading.get("reading_id"),
        sensor_type=sensor_type,
        sensor_name=sensor_name,
        alert_type=alert_type,
        severity=severity,
        measured_value=value,
        unit=reading.get("unit"),
        min_threshold=rule.get("min_value"),
        max_threshold=rule.get("max_value"),
        message=_build_message(sensor_name, severity, direction, value, reading.get("unit"), rule),
        recommended_action=get_recommended_action(sensor_type, alert_type, severity),
        status="active",
        created_at=_now_iso(),
        resolved_at=None,
        # Inherit provenance from the triggering reading so a simulation-scenario
        # reading produces a simulation-scenario alert (None for normal readings).
        source=reading.get("source"),
        scenario_id=reading.get("scenario_id"),
    )
    append_json(ALERTS_FILE, alert)
    return alert


def get_active_alerts():
    """
    Return active alerts ordered by severity (critical before warning), then by
    created_at newest-to-oldest.
    """
    alerts = [a for a in read_json(ALERTS_FILE, default=[]) if a.get("status") == "active"]
    # Stable sort: newest first, then group by severity rank.
    alerts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    alerts.sort(key=lambda a: _SEVERITY_RANK.get(a.get("severity"), 99))
    return alerts


def get_alert_history():
    """Return all alerts (active + resolved), newest-to-oldest by created_at."""
    alerts = list(read_json(ALERTS_FILE, default=[]))
    alerts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return alerts


def get_alerts_for_sensor(sensor_id):
    """Return all alerts for one sensor, newest-to-oldest by created_at."""
    alerts = [a for a in read_json(ALERTS_FILE, default=[]) if a.get("sensor_id") == sensor_id]
    alerts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return alerts


def resolve_alert(alert_id):
    """
    Resolve an active alert.

    Returns one of:
        {"outcome": "not_found", "alert": None}
        {"outcome": "already_resolved", "alert": <alert>}
        {"outcome": "resolved", "alert": <alert>}

    Only `status` and `resolved_at` are ever modified.
    """
    alerts = read_json(ALERTS_FILE, default=[])
    target = None
    for alert in alerts:
        if alert.get("alert_id") == alert_id:
            target = alert
            break

    if target is None:
        return {"outcome": "not_found", "alert": None}

    if target.get("status") == "resolved":
        return {"outcome": "already_resolved", "alert": target}

    target["status"] = "resolved"
    target["resolved_at"] = _now_iso()
    write_json(ALERTS_FILE, alerts)
    return {"outcome": "resolved", "alert": target}
