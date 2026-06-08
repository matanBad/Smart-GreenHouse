"""
alert_model.py

Describes the shape of an alert (stored in data/alerts.json).

Alerts are created ONLY by backend logic after the rule engine flags a reading as
"warning" or "critical" — never directly by a client. Each alert is linked to the
exact reading that triggered it.

Fields:
    alert_id           : unique id for the alert
    sensor_id          : sensor the alert relates to
    reading_id         : the reading that triggered the alert
    sensor_type        : temperature | humidity | soil_moisture | light_intensity
    sensor_name        : human-friendly sensor name
    alert_type         : e.g. temperature_too_high, soil_moisture_too_low
    severity           : warning | critical (derived from reading_status)
    measured_value     : the value that triggered the alert
    unit               : unit of the measured value
    min_threshold      : configured minimum for the sensor type
    max_threshold      : configured maximum for the sensor type
    message            : human-readable description of the alert
    recommended_action : suggested operator response
    status             : active | resolved
    created_at         : ISO-8601 time the alert was raised
    resolved_at        : ISO-8601 time the alert was resolved (None while active)
"""


def make_alert(
    alert_id,
    sensor_id,
    reading_id,
    sensor_type,
    sensor_name,
    alert_type,
    severity,
    measured_value,
    unit,
    min_threshold,
    max_threshold,
    message,
    recommended_action,
    status="active",
    created_at=None,
    resolved_at=None,
    source=None,
    scenario_id=None,
):
    """
    Build an alert dict in the canonical shape.

    `source` / `scenario_id` carry the provenance of the triggering reading
    (None for normal readings, set for simulation-scenario readings).
    """
    return {
        "alert_id": alert_id,
        "sensor_id": sensor_id,
        "reading_id": reading_id,
        "sensor_type": sensor_type,
        "sensor_name": sensor_name,
        "alert_type": alert_type,
        "severity": severity,
        "measured_value": measured_value,
        "unit": unit,
        "min_threshold": min_threshold,
        "max_threshold": max_threshold,
        "message": message,
        "recommended_action": recommended_action,
        "status": status,
        "created_at": created_at,
        "resolved_at": resolved_at,
        "source": source,
        "scenario_id": scenario_id,
    }
