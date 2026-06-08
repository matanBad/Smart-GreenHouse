"""
actuator_model.py

Describes the shape of a simulated actuator device (stored in
data/actuators.json).

Actuators are virtual devices the automation controller "operates" in response
to critical alerts (e.g. turning on the ventilation fan). Their status is owned
entirely by backend automation logic — a client may request a reset but never
sets status directly.

Fields:
    actuator_id          : unique id, e.g. ACT-VENT-001
    actuator_type        : ventilation | irrigation | lighting | air_circulation
    actuator_name        : human-friendly device name
    status               : active | inactive
    greenhouse_id        : greenhouse the actuator belongs to
    last_activation_time : ISO-8601 time the actuator was last activated (or None)
    last_trigger_reason  : why it was last activated (or None)
"""


def make_actuator(
    actuator_id,
    actuator_type,
    actuator_name,
    status="inactive",
    greenhouse_id="GH-001",
    last_activation_time=None,
    last_trigger_reason=None,
):
    """Build an actuator dict in the canonical shape."""
    return {
        "actuator_id": actuator_id,
        "actuator_type": actuator_type,
        "actuator_name": actuator_name,
        "status": status,
        "greenhouse_id": greenhouse_id,
        "last_activation_time": last_activation_time,
        "last_trigger_reason": last_trigger_reason,
    }
