"""
sensor_service.py -> Sensor Monitoring

Future PRD area: Sensor Monitoring.

Responsible for the virtual sensors and the readings they produce. Prompt 2
adds reading ingestion (store a validated reading), latest-reading retrieval,
and per-sensor reading history. Prompt 7 adds sensor management: demo-admin
configuration updates (name/unit/status), activity (communication) status
derivation from the last valid reading, and stale-sensor detection.

Note: this service assumes readings have already been validated by
`validation_service`. It does not re-validate; it only stores and queries.
"""

import uuid
from datetime import datetime, timezone

from models.reading_model import make_reading
from services.storage_service import append_json, read_json, write_json

# Demo admin protection for Prompt 7. This is temporary "demo admin mode" for
# the MVP; full authentication / role-based permissions come in a later prompt.
ADMIN_ROLE = "system_administrator"

# The four supported virtual sensor types.
VALID_SENSOR_TYPES = (
    "temperature",
    "humidity",
    "soil_moisture",
    "light_intensity",
)

# Administrative (enabled/disabled) states a sensor may be set to.
VALID_STATUSES = ("enabled", "disabled")

# Units that are valid for each sensor type. Unit edits must match the sensor's
# configured type — a temperature sensor cannot suddenly report in "lux".
VALID_UNITS_BY_TYPE = {
    "temperature": ("C", "F"),
    "humidity": ("%",),
    "soil_moisture": ("%",),
    "light_intensity": ("lux",),
}

# Fields a demo administrator is allowed to edit. sensor_id and sensor_type are
# deliberately excluded — they are immutable.
EDITABLE_FIELDS = ("sensor_name", "unit", "status")


def _now_iso():
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _new_reading_id():
    """Generate a unique reading id."""
    return "READ-" + uuid.uuid4().hex[:12]


def _parse_iso(value):
    """Parse an ISO-8601 timestamp into an aware datetime, or None if invalid."""
    if not value or not isinstance(value, str):
        return None
    try:
        # Python's fromisoformat accepts "Z" from 3.11, but normalise to be safe.
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_all_sensors():
    """Return the list of configured virtual sensors from storage."""
    return read_json("sensors.json", default=[])


def get_sensor_by_id(sensor_id):
    """Return a single sensor by its id, or None if not found."""
    for sensor in get_all_sensors():
        if sensor.get("sensor_id") == sensor_id:
            return sensor
    return None


def _save_all_sensors(sensors):
    """Persist the full sensors list back to storage."""
    write_json("sensors.json", sensors)


def save_all_sensors(sensors):
    """Public helper to persist the full sensors list (used by activity checks)."""
    _save_all_sensors(sensors)


def calculate_sensor_activity_status(sensor):
    """
    Derive a sensor's communication status from its last valid reading.

    - No last_valid_reading_at            -> "no_data"
    - age <= expected_frequency_seconds*2  -> "active"
    - age >  expected_frequency_seconds*2  -> "inactive"
    """
    last = _parse_iso(sensor.get("last_valid_reading_at"))
    if last is None:
        return "no_data"
    frequency = sensor.get("expected_frequency_seconds") or 0
    age_seconds = (datetime.now(timezone.utc) - last).total_seconds()
    if age_seconds <= frequency * 2:
        return "active"
    return "inactive"


def mark_sensor_inactive_if_stale(sensor):
    """Recalculate and set the sensor's communication_status in place; return it."""
    sensor["communication_status"] = calculate_sensor_activity_status(sensor)
    return sensor


def update_sensor_last_valid_reading(sensor_id):
    """
    Record that a sensor produced a valid reading right now.

    Sets last_valid_reading_at to the SERVER's ingestion time (never the
    client-supplied reading timestamp) and recomputes communication_status, then
    persists. Deriving freshness from server time keeps activity classification
    trustworthy — a client cannot spoof its own active/inactive status by sending
    stale or future timestamps. Returns the updated sensor, or None if the sensor
    id is unknown. Only call this for readings that passed validation — rejected
    readings must never update activity.
    """
    sensors = get_all_sensors()
    updated = None
    now_iso = datetime.now(timezone.utc).isoformat()
    for sensor in sensors:
        if sensor.get("sensor_id") == sensor_id:
            sensor["last_valid_reading_at"] = now_iso
            sensor["communication_status"] = calculate_sensor_activity_status(sensor)
            updated = sensor
            break
    if updated is not None:
        _save_all_sensors(sensors)
    return updated


def validate_sensor_update(sensor_id, update_data, role):
    """
    Validate a demo-admin sensor configuration update without trusting the client.

    Returns a dict:
        authorized   : bool  (role is system_administrator)
        sensor_found : bool  (sensor id exists)
        errors       : list[str]  (field-level validation problems)
    """
    authorized = role == ADMIN_ROLE
    sensor = get_sensor_by_id(sensor_id)
    sensor_found = sensor is not None
    errors = []

    if not isinstance(update_data, dict):
        return {
            "authorized": authorized,
            "sensor_found": sensor_found,
            "errors": ["Update body must be a JSON object"],
        }

    # Immutable fields may not be changed.
    if "sensor_id" in update_data and update_data["sensor_id"] != sensor_id:
        errors.append("sensor_id cannot be changed")
    if sensor is not None:
        if (
            "sensor_type" in update_data
            and update_data["sensor_type"] != sensor.get("sensor_type")
        ):
            errors.append("sensor_type cannot be changed")

        if "sensor_name" in update_data:
            name = update_data["sensor_name"]
            if not isinstance(name, str) or not name.strip():
                errors.append("sensor_name must be a non-empty string")

        if "unit" in update_data:
            unit = update_data["unit"]
            allowed_units = VALID_UNITS_BY_TYPE.get(sensor.get("sensor_type"), ())
            if unit not in allowed_units:
                errors.append("Unit does not match sensor type")

        if "status" in update_data:
            if update_data["status"] not in VALID_STATUSES:
                errors.append("Unsupported status value")

    return {
        "authorized": authorized,
        "sensor_found": sensor_found,
        "errors": errors,
    }


def update_sensor_configuration(sensor_id, update_data, role):
    """
    Apply an editable-field update to a sensor and persist it.

    Only sensor_name, unit, and status are mutable. Returns
    (updated_sensor, changes) where `changes` maps each changed field to
    {"old": ..., "new": ...} for logging. Returns (None, {}) if the sensor is
    unknown. Callers must validate first via validate_sensor_update().
    """
    sensors = get_all_sensors()
    target = None
    for sensor in sensors:
        if sensor.get("sensor_id") == sensor_id:
            target = sensor
            break
    if target is None:
        return None, {}

    changes = {}
    for field in EDITABLE_FIELDS:
        if field in update_data:
            new_value = update_data[field]
            old_value = target.get(field)
            if new_value != old_value:
                changes[field] = {"old": old_value, "new": new_value}
                target[field] = new_value

    if changes:
        target["updated_at"] = _now_iso()
        _save_all_sensors(sensors)
    return target, changes


def get_all_sensor_statuses():
    """
    Return every sensor with its derived communication status (read-only).

    This computes communication_status on the fly without persisting, so it is
    safe to call for display. Each entry also includes the latest reading (if
    any) under `current_reading`.
    """
    result = []
    for sensor in get_all_sensors():
        sensor_id = sensor.get("sensor_id")
        result.append(
            {
                "sensor_id": sensor_id,
                "sensor_name": sensor.get("sensor_name"),
                "sensor_type": sensor.get("sensor_type"),
                "unit": sensor.get("unit"),
                "status": sensor.get("status"),
                "expected_frequency_seconds": sensor.get("expected_frequency_seconds"),
                "last_valid_reading_at": sensor.get("last_valid_reading_at"),
                "communication_status": calculate_sensor_activity_status(sensor),
                "current_reading": get_latest_reading_for_sensor(sensor_id),
            }
        )
    return result


def save_reading(
    sensor_id,
    sensor_type,
    value,
    unit,
    timestamp,
    reading_status,
    source=None,
    scenario_id=None,
):
    """
    Persist a validated, rule-evaluated reading to readings.json.

    Adds server-side metadata: reading_id and created_at. The reading_status
    ("normal" | "warning" | "critical") is computed by the Rule Engine — callers
    must validate the payload and evaluate it before saving. `source` /
    `scenario_id` mark provenance (set for simulation-scenario readings, else
    None). Returns the record.
    """
    reading = make_reading(
        reading_id=_new_reading_id(),
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        value=value,
        unit=unit,
        timestamp=timestamp,
        reading_status=reading_status,
        created_at=_now_iso(),
        source=source,
        scenario_id=scenario_id,
    )
    append_json("readings.json", reading)
    return reading


def get_readings_for_sensor(sensor_id):
    """Return all stored readings for a sensor, newest first (by created_at)."""
    readings = read_json("readings.json", default=[])
    sensor_readings = [r for r in readings if r.get("sensor_id") == sensor_id]
    sensor_readings.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return sensor_readings


def get_latest_reading_for_sensor(sensor_id):
    """Return the most recent stored reading for a sensor, or None."""
    sensor_readings = get_readings_for_sensor(sensor_id)
    return sensor_readings[0] if sensor_readings else None


def get_latest_readings():
    """
    Return the latest reading for each configured sensor.

    Each entry merges the sensor configuration with its latest reading. Sensors
    with no reading yet have `has_reading: false` and a null `latest_reading`.
    """
    # Imported here (not at module top) to avoid a circular import:
    # rule_engine imports storage_service, and this service is widely imported.
    from services.rule_engine import get_threshold_rule

    result = []
    for sensor in get_all_sensors():
        sensor_id = sensor.get("sensor_id")
        sensor_type = sensor.get("sensor_type")
        latest = get_latest_reading_for_sensor(sensor_id)
        rule = get_threshold_rule(sensor_type)
        result.append(
            {
                "sensor_id": sensor_id,
                "sensor_type": sensor_type,
                "name": sensor.get("sensor_name"),
                "unit": sensor.get("unit"),
                "location": sensor.get("location"),
                "status": sensor.get("status"),
                "communication_status": calculate_sensor_activity_status(sensor),
                "threshold_min": rule.get("min_value") if rule else None,
                "threshold_max": rule.get("max_value") if rule else None,
                "has_reading": latest is not None,
                "latest_reading": latest,
            }
        )
    return result
