"""
threshold_rule_model.py

Describes the shape of a threshold rule (stored in data/threshold_rules.json).

Fields:
    rule_id     : unique id for the rule
    sensor_type : temperature | humidity | soil_moisture | light_intensity
    unit        : measurement unit
    min         : minimum acceptable value
    max         : maximum acceptable value
"""


def make_threshold_rule(rule_id, sensor_type, unit, min_value, max_value):
    """Build a threshold rule dict in the canonical shape (future prompts)."""
    return {
        "rule_id": rule_id,
        "sensor_type": sensor_type,
        "unit": unit,
        "min": min_value,
        "max": max_value,
    }
