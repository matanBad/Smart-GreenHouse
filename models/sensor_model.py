"""
sensor_model.py

Describes the shape of a virtual sensor record (stored in data/sensors.json).
This is a lightweight model definition for the MVP — it documents the expected
fields and offers a small helper to build a sensor dict. No ORM/database.

Fields:
    sensor_id                 : unique id, e.g. "TEMP-001"
    greenhouse_id             : greenhouse the sensor belongs to
    sensor_type               : temperature | humidity | soil_moisture | light_intensity
    sensor_name               : human-readable sensor name
    unit                      : measurement unit, e.g. "C", "%", "lux"
    location                  : where the sensor sits in the greenhouse
    status                    : enabled | disabled (administrative state)
    expected_frequency_seconds: how often this sensor is expected to report
    last_valid_reading_at     : ISO-8601 time of the last accepted reading (or None)
    communication_status      : active | inactive | no_data (derived activity state)
    created_at                : ISO-8601 time the sensor was created
    updated_at                : ISO-8601 time the sensor was last updated
"""


def make_sensor(
    sensor_id,
    sensor_type,
    unit,
    sensor_name="",
    greenhouse_id="GH-001",
    location="",
    status="enabled",
    expected_frequency_seconds=5,
    last_valid_reading_at=None,
    communication_status="no_data",
    created_at=None,
    updated_at=None,
):
    """Build a sensor dict in the canonical shape (helper for future prompts)."""
    return {
        "sensor_id": sensor_id,
        "greenhouse_id": greenhouse_id,
        "sensor_type": sensor_type,
        "sensor_name": sensor_name,
        "unit": unit,
        "location": location,
        "status": status,
        "expected_frequency_seconds": expected_frequency_seconds,
        "last_valid_reading_at": last_valid_reading_at,
        "communication_status": communication_status,
        "created_at": created_at,
        "updated_at": updated_at,
    }
