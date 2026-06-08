"""
system_log_model.py

Describes the shape of a system log entry (stored in data/system_logs.json).

For Prompt 2 the most common log is a rejected sensor reading, so the model
captures enough context to audit why a reading was refused.

Fields:
    log_id           : unique id for the log entry
    event_type       : category, e.g. "invalid_sensor_reading",
                       "unknown_sensor_id", "invalid_unit", ...
    description       : human-readable description of the event
    sensor_id        : sensor the event relates to (if available)
    sensor_type      : sensor type the event relates to (if available)
    alert_id         : alert the event relates to (if available)
    actuator_id      : actuator the event relates to (if available)
    rejection_reason : why a reading was rejected (if applicable)
    original_payload : the original request payload, when safe to store
    details          : optional dict of event-specific structured data (e.g. the
                       old/new values and role for a threshold change)
    created_at       : ISO-8601 time the event occurred
"""


def make_log(
    log_id,
    event_type,
    description,
    sensor_id=None,
    sensor_type=None,
    alert_id=None,
    actuator_id=None,
    rejection_reason=None,
    original_payload=None,
    details=None,
    created_at=None,
):
    """Build a system log dict in the canonical shape."""
    return {
        "log_id": log_id,
        "event_type": event_type,
        "description": description,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "alert_id": alert_id,
        "actuator_id": actuator_id,
        "rejection_reason": rejection_reason,
        "original_payload": original_payload,
        "details": details,
        "created_at": created_at,
    }
