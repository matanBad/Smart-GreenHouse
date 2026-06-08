"""
validation_service.py -> Sensor Reading Validation

Future PRD area: Sensor Reading Validation.

Security principle: NEVER trust client input. Every field of an incoming sensor
reading is validated before it is allowed anywhere near storage.

Each individual check returns a tuple:
    (is_ok: bool, message: str | None, code: str | None)

`validate_sensor_reading` aggregates the individual checks into a structured
result:
    {
        "is_valid": bool,
        "errors": [str, ...],   # human-readable messages
        "codes":  [str, ...],   # machine-readable event_type codes
    }

The `codes` map onto the system-log event_type values used when a reading is
rejected (e.g. "invalid_unit", "non_numeric_value").
"""

from datetime import datetime

from services.sensor_service import get_sensor_by_id


def validate_sensor_exists(sensor_id):
    """Check that the sensor id is registered in sensors.json."""
    if get_sensor_by_id(sensor_id) is not None:
        return True, None, None
    return False, f"Unknown sensor id: {sensor_id}", "unknown_sensor_id"


def validate_id_match(url_sensor_id, body_sensor_id):
    """Check that the URL sensor id matches the sensor id in the body."""
    if body_sensor_id is None:
        return False, "sensor_id is required in the request body", "sensor_id_mismatch"
    if url_sensor_id != body_sensor_id:
        return (
            False,
            "sensor_id in URL does not match sensor_id in body",
            "sensor_id_mismatch",
        )
    return True, None, None


def validate_sensor_type(sensor_id, sensor_type):
    """Check that the reading's sensor_type matches the configured sensor type."""
    sensor = get_sensor_by_id(sensor_id)
    if sensor is None:
        return False, f"Unknown sensor id: {sensor_id}", "unknown_sensor_id"
    if not sensor_type:
        return False, "sensor_type is required", "invalid_sensor_type"
    if sensor_type != sensor.get("sensor_type"):
        return (
            False,
            f"sensor_type '{sensor_type}' does not match configured type "
            f"'{sensor.get('sensor_type')}'",
            "invalid_sensor_type",
        )
    return True, None, None


def validate_numeric_value(value):
    """Check that the value is a real number (and not a bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, "value must be numeric", "non_numeric_value"
    return True, None, None


def validate_unit(sensor_id, unit):
    """Check that the reading's unit matches the configured sensor unit."""
    sensor = get_sensor_by_id(sensor_id)
    if sensor is None:
        return False, f"Unknown sensor id: {sensor_id}", "unknown_sensor_id"
    if not unit:
        return False, "unit is required", "invalid_unit"
    if unit != sensor.get("unit"):
        return (
            False,
            f"unit '{unit}' does not match configured unit '{sensor.get('unit')}'",
            "invalid_unit",
        )
    return True, None, None


def validate_timestamp(timestamp):
    """Check that the timestamp exists and is a valid ISO-8601 string."""
    if not timestamp or not isinstance(timestamp, str):
        return False, "timestamp is required", "invalid_timestamp"
    try:
        # Python's fromisoformat accepts the trailing 'Z' from 3.11 onward,
        # but normalise it defensively for safety.
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False, "timestamp is not a valid ISO-8601 datetime", "invalid_timestamp"
    return True, None, None


def validate_sensor_reading(sensor_id, payload):
    """
    Validate a full sensor reading payload against the sensor configuration.

    Returns a structured result: {"is_valid", "errors", "codes"}.
    """
    errors = []
    codes = []

    def collect(result):
        ok, message, code = result
        if not ok:
            errors.append(message)
            codes.append(code)
        return ok

    if not isinstance(payload, dict):
        return {
            "is_valid": False,
            "errors": ["Request body must be a JSON object"],
            "codes": ["invalid_sensor_reading"],
        }

    # 1) The sensor in the URL must exist. If it doesn't, stop here — the
    #    type/unit checks have nothing to compare against.
    if not collect(validate_sensor_exists(sensor_id)):
        return {"is_valid": False, "errors": errors, "codes": codes}

    # 2) URL id must match the body id.
    collect(validate_id_match(sensor_id, payload.get("sensor_id")))

    # 3) Field-level checks.
    collect(validate_sensor_type(sensor_id, payload.get("sensor_type")))
    collect(validate_numeric_value(payload.get("value")))
    collect(validate_unit(sensor_id, payload.get("unit")))
    collect(validate_timestamp(payload.get("timestamp")))

    return {"is_valid": len(errors) == 0, "errors": errors, "codes": codes}
