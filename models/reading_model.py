"""
reading_model.py

Describes the shape of a sensor reading (stored in data/readings.json).

Fields:
    reading_id     : unique id for the reading
    sensor_id      : id of the sensor that produced it
    sensor_type    : type of the sensor (temperature, humidity, ...)
    value          : numeric measured value
    unit           : measurement unit
    timestamp      : ISO-8601 time the reading was taken (from the sensor)
    reading_status : lifecycle status. For Prompt 2 this is always "received".
                     normal/warning/critical evaluation comes with the Rule
                     Engine in a later prompt.
    created_at     : ISO-8601 time the reading was stored by the server
"""


def make_reading(
    reading_id,
    sensor_id,
    sensor_type,
    value,
    unit,
    timestamp,
    reading_status="received",
    created_at=None,
    source=None,
    scenario_id=None,
):
    """
    Build a reading dict in the canonical shape.

    `source` / `scenario_id` mark a reading's provenance. They are None for
    normal ingestion and set (e.g. source="simulation_scenario") when a reading
    is produced by a predefined simulation scenario.
    """
    return {
        "reading_id": reading_id,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": value,
        "unit": unit,
        "timestamp": timestamp,
        "reading_status": reading_status,
        "created_at": created_at,
        "source": source,
        "scenario_id": scenario_id,
    }
