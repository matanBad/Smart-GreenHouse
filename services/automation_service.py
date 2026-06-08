"""
automation_service.py -> Simulated Automation Responses

PRD area: Simulated Automation Responses.

When the rule engine raises a *critical* alert, the automation controller
"responds" by activating the matching simulated actuator (e.g. a critical high
temperature turns the ventilation fan on). Every response is recorded as an
automation action and the actuator's status is updated.

Flow:
    Critical Alert -> Automation Controller -> Simulated Actuator Response ->
    Automation Action (history) -> Dashboard

Security model:
    - Automation actions are NEVER created from client input. They are produced
      only here, after a server-side critical alert.
    - Actuator status is owned by this service. Clients may request a reset, but
      never set status directly.
    - Only CRITICAL alerts trigger automation. warning / normal / invalid
      readings never reach this service with an effect.

Out of scope for this prompt: authentication, threshold editing, analytics.
"""

import uuid
from datetime import datetime, timezone

from models.actuator_model import make_actuator  # noqa: F401  (shape reference)
from models.automation_action_model import make_automation_action
from services import log_service
from services.storage_service import append_json, read_json, write_json

ACTUATORS_FILE = "actuators.json"
ACTIONS_FILE = "automation_actions.json"

# Maps a critical alert_type to the actuator that should respond. alert_type is
# "<sensor_type>_<direction>" (see alert_service). action_type is derived from
# the actuator_type as f"activate_{actuator_type}".
AUTOMATION_RULES = {
    "temperature_too_high": "ventilation",
    "soil_moisture_too_low": "irrigation",
    "light_intensity_too_low": "lighting",
    "humidity_too_high": "air_circulation",
}


def _now_iso():
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _new_action_id():
    """Generate a unique automation action id."""
    return "ACTION-" + uuid.uuid4().hex[:12]


def get_all_actuators():
    """Return all actuators and their current status."""
    return read_json(ACTUATORS_FILE, default=[])


def get_actuator_by_type(actuator_type):
    """Return the first actuator of a given type, or None if none exists."""
    for actuator in read_json(ACTUATORS_FILE, default=[]):
        if actuator.get("actuator_type") == actuator_type:
            return actuator
    return None


def get_actuator_by_id(actuator_id):
    """Return an actuator by id, or None if it does not exist."""
    for actuator in read_json(ACTUATORS_FILE, default=[]):
        if actuator.get("actuator_id") == actuator_id:
            return actuator
    return None


def determine_automation_response(alert):
    """
    Decide which actuator type should respond to an alert.

    Returns the actuator_type string, or None if there is no rule for the
    alert's type. This does NOT check severity — callers gate on critical.
    """
    if not alert:
        return None
    return AUTOMATION_RULES.get(alert.get("alert_type"))


def update_actuator_status(actuator_id, status, trigger_reason=None):
    """
    Update an actuator's status (and activation metadata). Backend-only.

    Returns the updated actuator, or None if the actuator does not exist. This
    is a pure data mutation — callers are responsible for logging.
    """
    actuators = read_json(ACTUATORS_FILE, default=[])
    target = None
    for actuator in actuators:
        if actuator.get("actuator_id") == actuator_id:
            target = actuator
            break

    if target is None:
        return None

    target["status"] = status
    target["last_trigger_reason"] = trigger_reason
    if status == "active":
        target["last_activation_time"] = _now_iso()
    write_json(ACTUATORS_FILE, actuators)
    return target


def create_automation_action(alert, actuator):
    """
    Build and persist an automation action linking an alert to an actuator.

    Returns the stored action. Callers must only invoke this after a critical
    alert with a matching actuator.
    """
    actuator_type = actuator.get("actuator_type")
    action = make_automation_action(
        action_id=_new_action_id(),
        actuator_id=actuator.get("actuator_id"),
        actuator_type=actuator_type,
        actuator_name=actuator.get("actuator_name"),
        related_alert_id=alert.get("alert_id"),
        related_sensor_id=alert.get("sensor_id"),
        action_type=f"activate_{actuator_type}",
        trigger_reason=alert.get("message"),
        action_status="active",
        triggered_at=_now_iso(),
        # Inherit provenance from the triggering alert so a simulation-scenario
        # alert produces a simulation-scenario action (None for normal alerts).
        source=alert.get("source"),
        scenario_id=alert.get("scenario_id"),
    )
    append_json(ACTIONS_FILE, action)
    return action


def trigger_automation_for_alert(alert):
    """
    Run a simulated automation response for a critical alert.

    Steps: confirm the alert is critical, find the matching actuator, activate
    it, record the automation action, and log every outcome. Returns the stored
    automation action, or None when no automation was performed (non-critical,
    unsupported alert type, or missing actuator).
    """
    if not alert or alert.get("severity") != "critical":
        # Defensive guard — only critical alerts ever drive automation.
        return None

    alert_id = alert.get("alert_id")
    sensor_id = alert.get("sensor_id")

    actuator_type = determine_automation_response(alert)
    if actuator_type is None:
        log_service.log_unsupported_automation_rule(
            alert_id=alert_id, sensor_id=sensor_id, alert_type=alert.get("alert_type")
        )
        return None

    actuator = get_actuator_by_type(actuator_type)
    if actuator is None:
        log_service.log_automation_trigger_failed(
            alert_id=alert_id,
            sensor_id=sensor_id,
            reason=f"no actuator of type '{actuator_type}'",
        )
        return None

    trigger_reason = alert.get("message")
    updated = update_actuator_status(
        actuator.get("actuator_id"), "active", trigger_reason
    )
    log_service.log_actuator_status_changed(
        actuator_id=actuator.get("actuator_id"),
        status="active",
        trigger_reason=trigger_reason,
    )

    action = create_automation_action(alert, updated or actuator)
    log_service.log_automation_triggered(
        actuator_id=action["actuator_id"],
        alert_id=alert_id,
        sensor_id=sensor_id,
        action_type=action["action_type"],
    )
    return action


def get_all_actions():
    """Return all automation actions, newest-to-oldest by triggered_at."""
    actions = list(read_json(ACTIONS_FILE, default=[]))
    actions.sort(key=lambda a: a.get("triggered_at") or "", reverse=True)
    return actions


def get_active_actions():
    """Return automation actions that are still active, newest-to-oldest."""
    actions = [
        a for a in read_json(ACTIONS_FILE, default=[]) if a.get("action_status") == "active"
    ]
    actions.sort(key=lambda a: a.get("triggered_at") or "", reverse=True)
    return actions


def reset_actuator_status(actuator_id):
    """
    Reset an actuator to inactive (manual operator action).

    Returns one of:
        {"outcome": "not_found", "actuator": None}
        {"outcome": "already_inactive", "actuator": <actuator>}
        {"outcome": "reset", "actuator": <actuator>}

    Only status / activation metadata change. Also marks that actuator's active
    automation actions as resolved so the active list stays consistent.
    """
    actuator = get_actuator_by_id(actuator_id)
    if actuator is None:
        return {"outcome": "not_found", "actuator": None}

    if actuator.get("status") == "inactive":
        return {"outcome": "already_inactive", "actuator": actuator}

    updated = update_actuator_status(actuator_id, "inactive", trigger_reason="manual reset")
    _deactivate_actions_for_actuator(actuator_id)
    log_service.log_actuator_reset(actuator_id=actuator_id)
    return {"outcome": "reset", "actuator": updated}


def _deactivate_actions_for_actuator(actuator_id):
    """Mark active automation actions for an actuator as resolved on reset."""
    actions = read_json(ACTIONS_FILE, default=[])
    changed = False
    for action in actions:
        if action.get("actuator_id") == actuator_id and action.get("action_status") == "active":
            action["action_status"] = "resolved"
            changed = True
    if changed:
        write_json(ACTIONS_FILE, actions)
