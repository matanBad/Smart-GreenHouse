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
from datetime import datetime, timezone, timedelta

from models.actuator_model import make_actuator  # noqa: F401  (shape reference)
from models.automation_action_model import make_automation_action
from services import log_service
from services.storage_service import append_json, read_json, write_json
from services.rule_engine import get_threshold_rule, evaluate_reading_status
from services.sensor_service import save_reading, update_sensor_last_valid_reading

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
    # Optionally simulate an actuator effect by generating a corrective reading
    # that moves the sensor back into the safe range. This is a pure simulation
    # for the demo environment and does not represent real device control.
    try:
        _simulate_actuator_correction(alert, updated or actuator)
    except Exception:
        # Never allow a simulation hiccup to break the main flow.
        log_service.log_automation_trigger_failed(
            alert_id=alert_id,
            sensor_id=sensor_id,
            reason="failed to simulate actuator correction",
        )

    return action


def _simulate_actuator_correction(alert, actuator):
    """
    For demo/simulation only: create a single corrective reading that nudges the
    sensor back inside the configured threshold so the dashboard reflects the
    actuator's expected effect.

    This directly persists a reading via the sensor service (bypassing the full
    pipeline) and updates the sensor activity timestamp. It computes a value
    just inside the allowed range (one warning_margin or 1 unit inside).
    """
    if not alert or not actuator:
        return None

    sensor_type = alert.get("sensor_type")
    sensor_id = alert.get("sensor_id")
    rule = get_threshold_rule(sensor_type)
    if rule is None:
        return None

    # Determine the breached direction from the alert_type (expected format
    # "<sensor_type>_too_high" / "<sensor_type>_too_low").
    alert_type = alert.get("alert_type", "")
    direction = "too_high" if alert_type.endswith("too_high") else "too_low"

    margin = rule.get("warning_margin", 1) or 1

    # Current breached value comes from the alert's measured_value when
    # available; fall back to boundary + offset if missing.
    current_value = alert.get("measured_value")
    try:
        current_value = float(current_value)
    except Exception:
        # Fallback: pick a value just beyond the breached boundary
        if direction == "too_high":
            current_value = float(rule.get("max_value") + (margin or 1))
        else:
            current_value = float(rule.get("min_value") - (margin or 1))

    # Target: one margin inside the allowed range (safe side).
    if direction == "too_high":
        target_value = float(rule.get("max_value") - margin)
    else:
        target_value = float(rule.get("min_value") + margin)

    # If already inside range, nothing to do.
    if (direction == "too_high" and current_value <= target_value) or (
        direction == "too_low" and current_value >= target_value
    ):
        return None

    # Simulate a gradual corrective effect over several steps so the value
    # approaches the target (demo only). Use 3 steps by default.
    steps = 3
    delta = (target_value - current_value) / steps

    # Build timestamps spaced by 1 second so created_at ordering is sensible.
    base_time = datetime.now(timezone.utc)
    for i in range(1, steps + 1):
        step_value = current_value + delta * i
        # Ensure numeric type
        try:
            step_value = float(step_value)
        except Exception:
            continue

        status = evaluate_reading_status(sensor_type, step_value)
        ts = (base_time + timedelta(seconds=i)).isoformat()

        save_reading(
            sensor_id,
            sensor_type,
            step_value,
            alert.get("unit") or rule.get("unit"),
            ts,
            status,
            source="automation",
        )
        try:
            update_sensor_last_valid_reading(sensor_id)
        except Exception:
            pass

    # If the simulated corrective steps moved the sensor back into the normal
    # range, resolve any active alerts for the sensor and deactivate related
    # automation actions so the actuator stops responding. This keeps the demo
    # behaviour consistent: automation should cease once the condition is fixed.
    try:
        # Determine final evaluation from the last simulated step (status).
        final_status = status if "status" in locals() else None
        # If the simulated corrective readings moved the sensor out of a
        # critical state (into warning or normal), resolve active critical
        # alerts and deactivate related automation actions so the actuator
        # stops responding.
        if final_status is not None and final_status != "critical":
            # Lazy import to avoid cycles
            from services.alert_service import get_alerts_for_sensor, resolve_alert

            # Resolve active alerts for this sensor
            alerts = get_alerts_for_sensor(sensor_id)
            for a in alerts:
                if a.get("status") == "active":
                    try:
                        resolve_alert(a.get("alert_id"))
                    except Exception:
                        pass

            # Deactivate any automation actions related to this sensor
            try:
                deactivate_actions_for_sensor(sensor_id)
            except Exception:
                pass
    except Exception:
        # Never allow the simulation cleanup to break the main flow.
        pass


def get_all_actions():
    """Return all automation actions, newest-to-oldest by triggered_at."""
    actions = list(read_json(ACTIONS_FILE, default=[]))
    actions.sort(key=lambda a: a.get("triggered_at") or "", reverse=True)
    return actions


def clear_actions():
    """Clear the automation actions history (overwrite with an empty list).

    Returns True on success.
    """
    write_json(ACTIONS_FILE, [])
    return True


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


def deactivate_actions_for_sensor(sensor_id):
    """Resolve active automation actions related to a sensor and set actuators inactive.

    Called when a corrective reading (e.g. from a simulated actuator) brings a
    sensor back into the safe range.
    """
    actions = read_json(ACTIONS_FILE, default=[])
    changed = False
    actuators_to_reset = set()
    for action in actions:
        if action.get("related_sensor_id") == sensor_id and action.get("action_status") == "active":
            action["action_status"] = "resolved"
            actuators_to_reset.add(action.get("actuator_id"))
            changed = True
    if changed:
        write_json(ACTIONS_FILE, actions)

    # Set actuator status to inactive for any actuators that were responding.
    for aid in actuators_to_reset:
        try:
            update_actuator_status(aid, "inactive", trigger_reason="automation completed")
            log_service.log_actuator_status_changed(actuator_id=aid, status="inactive", trigger_reason="automation completed")
        except Exception:
            pass
    return True


