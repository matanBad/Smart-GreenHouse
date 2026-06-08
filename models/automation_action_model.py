"""
automation_action_model.py

Describes the shape of an automation action (stored in
data/automation_actions.json).

An automation action is the record of the automation controller responding to a
critical alert by activating an actuator. Actions are created ONLY by backend
logic after a critical alert — never directly by a client.

Fields:
    action_id        : unique id for the action
    actuator_id      : the actuator that was operated
    actuator_type    : ventilation | irrigation | lighting | air_circulation
    actuator_name    : human-friendly actuator name
    related_alert_id : the critical alert that triggered this action
    related_sensor_id: the sensor whose reading raised the alert
    action_type      : e.g. activate_ventilation, activate_irrigation
    action_status    : active (actuator currently responding)
    trigger_reason   : why the action was taken (alert message)
    triggered_at     : ISO-8601 time the action was performed
"""


def make_automation_action(
    action_id,
    actuator_id,
    actuator_type,
    actuator_name,
    related_alert_id,
    related_sensor_id,
    action_type,
    trigger_reason,
    action_status="active",
    triggered_at=None,
    source=None,
    scenario_id=None,
):
    """
    Build an automation action dict in the canonical shape.

    `source` / `scenario_id` carry the provenance inherited from the triggering
    alert (None for normal alerts, set for simulation-scenario alerts).
    """
    return {
        "action_id": action_id,
        "actuator_id": actuator_id,
        "actuator_type": actuator_type,
        "actuator_name": actuator_name,
        "related_alert_id": related_alert_id,
        "related_sensor_id": related_sensor_id,
        "action_type": action_type,
        "action_status": action_status,
        "trigger_reason": trigger_reason,
        "triggered_at": triggered_at,
        "source": source,
        "scenario_id": scenario_id,
    }
