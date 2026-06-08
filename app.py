"""
Smart Greenhouse IoT System
===========================

Prompt 7 — Sensor Management & Sensor Activity Monitoring

This is the application entry point. It wires up a small, modular Flask
application that grows to support the full greenhouse data flow:

    Virtual Sensors -> REST API -> Validation Layer -> Rule Engine ->
    Alerts -> Automation Controller -> Simulated Actuators -> Storage -> Dashboard

Implemented so far:
    - GET   /                                  -> dashboard (templates/index.html)
    - GET   /api/health                        -> health check
    - GET   /api/sensors                       -> list configured virtual sensors
    - GET   /api/sensors/status                -> sensors + derived communication status
    - PUT   /api/sensors/<sensor_id>           -> update sensor config (admin demo mode)
    - POST  /api/sensors/check-activity        -> recalc + persist communication status
    - POST  /api/sensors/<sensor_id>/reading   -> validate + evaluate + store (+alert +automation +activity)
    - GET   /api/readings/latest               -> latest reading per sensor (+status)
    - GET   /api/sensors/<sensor_id>/readings  -> reading history for one sensor
    - GET   /api/thresholds                    -> all threshold rules
    - GET   /api/thresholds/<sensor_type>      -> one threshold rule
    - PUT   /api/thresholds/<sensor_type>      -> update a rule (admin demo mode)
    - GET   /api/alerts/active                 -> active alerts (critical-first)
    - GET   /api/alerts/history                -> all alerts (active + resolved)
    - GET   /api/sensors/<sensor_id>/alerts    -> alerts for one sensor
    - PATCH /api/alerts/<alert_id>/resolve     -> resolve an active alert
    - GET   /api/actuators                     -> all actuators + current status
    - GET   /api/automation/actions            -> automation history (newest-first)
    - GET   /api/automation/active             -> active automation responses
    - PATCH /api/actuators/<actuator_id>/reset -> reset an actuator to inactive
    - GET   /api/analytics/summary             -> full dashboard analytics summary
    - GET   /api/analytics/health              -> greenhouse health status + score
    - GET   /api/analytics/trends              -> recent trend per sensor type
    - GET   /api/simulation/scenarios          -> list predefined simulation scenarios
    - POST  /api/simulation/run/<scenario_id>  -> run one predefined scenario

Predefined simulation scenarios (Hot Day, Dry Soil, High Humidity, Low Light)
live in services/simulation_service.py. The backend generates controlled readings
relative to the current thresholds and runs them through the SAME ingestion
pipeline as normal readings (services/reading_pipeline.py: validate -> rule
engine -> storage -> alerts -> automation), so simulated readings never bypass
the real backend logic. Authentication remains future work.
"""

import os
from functools import wraps

from flask import Flask, jsonify, render_template, request

from services.alert_service import (
    create_alert,
    get_active_alerts,
    get_alert_history,
    get_alerts_for_sensor,
    resolve_alert,
)
from services.automation_service import (
    get_active_actions,
    get_actuator_by_id,
    get_all_actions,
    get_all_actuators,
    reset_actuator_status,
    trigger_automation_for_alert,
)
from services.analytics_service import (
    get_dashboard_analytics_summary,
    get_recent_trends_for_all_sensors,
    calculate_greenhouse_health_status,
    calculate_greenhouse_health_score,
    collect_current_state,
)
from services.log_service import (
    log_alert_generated,
    log_alert_generation_failed,
    log_alert_resolve_failed,
    log_alert_resolved,
    log_analytics_calculation_failed,
    log_analytics_summary_generated,
    log_automation_trigger_failed,
    log_health_score_calculated,
    log_invalid_sensor_update,
    log_missing_threshold_rule,
    log_rejected_reading,
    log_sensor_became_inactive,
    log_sensor_configuration_updated,
    log_sensor_no_data,
    log_unauthorized_sensor_update,
)
from services.rule_engine import apply_threshold_evaluation, get_all_rules, get_threshold_rule
from services.threshold_service import (
    log_rejected_update,
    update_threshold_rule,
    validate_threshold_update,
)
from services.sensor_service import (
    calculate_sensor_activity_status,
    get_all_sensor_statuses,
    get_all_sensors,
    get_latest_readings,
    get_readings_for_sensor,
    get_sensor_by_id,
    save_all_sensors,
    save_reading,
    update_sensor_configuration,
    update_sensor_last_valid_reading,
    validate_sensor_update,
)
from services.storage_service import init_storage
from services.validation_service import validate_sensor_reading
from services.reading_pipeline import process_reading
from services.simulation_service import (
    get_available_scenarios,
    get_scenario_by_id,
    run_simulation_scenario,
)
from services.log_service import (
    log_simulation_scenario_started,
    log_simulation_scenario_completed,
    log_simulation_scenario_failed,
    log_unknown_simulation_scenario,
)
from services.log_service import (
    get_logs,
    log_invalid_role_attempt,
    log_unauthorized_access_attempt,
)
from services.access_control_service import (
    get_role_from_request,
    normalize_role,
    require_permission,
)

app = Flask(__name__)


def permission_required(*actions):
    """
    Guard a route with role-based access control (Prompt 10).

    The caller's role is read ONLY from the X-User-Role header (never the JSON
    body), then checked against the permission matrix in
    services/access_control_service.py. Access is granted if the role holds ANY
    of the listed actions, so one endpoint can serve several capabilities (e.g.
    an admin who may reset actuators also needs to read them).

    Responses on denial (and every denial is logged to the security audit trail):
        - missing / invalid role -> 401 "Missing or invalid user role"
        - valid role, no permission -> 403 "You are not authorized to perform this action"
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            role = get_role_from_request(request)
            outcome = require_permission(role, actions)
            if outcome["allowed"]:
                return view(*args, **kwargs)

            # Record who tried to do what, and where, before refusing. The audit
            # log lives in the route layer so the access-control service stays a
            # pure, side-effect-free decision maker.
            if outcome["error"] == "invalid_role":
                log_invalid_role_attempt(role, actions[0], request.path)
                return (
                    jsonify(
                        {"success": False, "message": "Missing or invalid user role"}
                    ),
                    401,
                )

            log_unauthorized_access_attempt(
                normalize_role(role), actions[0], request.path
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "You are not authorized to perform this action",
                    }
                ),
                403,
            )

        return wrapped

    return decorator

# Make sure the JSON data files exist and are readable before serving traffic.
# This keeps the rest of the code simple and avoids missing-file crashes.
init_storage()


@app.route("/")
def index():
    """Homepage — renders the greenhouse dashboard."""
    return render_template("index.html")


@app.route("/api/health")
def health():
    """Basic health check used by QA and uptime monitoring."""
    return jsonify(
        {
            "status": "ok",
            "message": "Smart Greenhouse IoT System is running",
        }
    )


@app.route("/api/sensors")
@permission_required("view_current_readings", "view_sensor_status")
def sensors():
    """Return the configured virtual sensors from storage."""
    try:
        return jsonify(get_all_sensors())
    except Exception:
        return jsonify({"error": "Unable to load sensors at this time."}), 500


@app.route("/api/sensors/status")
@permission_required("view_sensor_status")
def sensors_status():
    """Return every sensor with its derived communication (activity) status."""
    try:
        return jsonify(get_all_sensor_statuses())
    except Exception:
        return jsonify({"error": "Unable to load sensor statuses at this time."}), 500


@app.route("/api/sensors/<sensor_id>", methods=["PUT"])
@permission_required("update_sensor_configuration")
def update_sensor(sensor_id):
    """
    Update a sensor's configuration (demo admin mode).

    Only a caller presenting role "system_administrator" may edit, and only the
    editable fields (sensor_name, unit, status) are applied — sensor_id and
    sensor_type are immutable. Everything is validated server-side; the frontend
    is never trusted. Authorization is checked first so unauthorized callers do
    not learn anything about validation.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}

    # The role is taken from the verified X-User-Role header (see the
    # permission_required guard), never from the request body.
    role = get_role_from_request(request)
    result = validate_sensor_update(sensor_id, payload, role)

    if not result["authorized"]:
        log_unauthorized_sensor_update(sensor_id, role)
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Only system administrators can update sensor configuration",
                }
            ),
            403,
        )

    if not result["sensor_found"]:
        return jsonify({"success": False, "message": "Sensor not found"}), 404

    if result["errors"]:
        log_invalid_sensor_update(sensor_id, result["errors"], role)
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Invalid sensor update",
                    "errors": result["errors"],
                }
            ),
            400,
        )

    try:
        updated, changes = update_sensor_configuration(sensor_id, payload, role)
    except Exception:
        return (
            jsonify({"success": False, "message": "Unable to update sensor configuration"}),
            500,
        )

    if updated is None:
        return jsonify({"success": False, "message": "Sensor not found"}), 404

    if changes:
        log_sensor_configuration_updated(
            sensor_id, updated.get("sensor_type"), changes, role
        )

    return jsonify(
        {
            "success": True,
            "message": "Sensor configuration updated successfully",
            "sensor": updated,
        }
    )


@app.route("/api/sensors/check-activity", methods=["POST"])
@permission_required("check_sensor_activity")
def check_sensor_activity():
    """
    Recalculate every sensor's communication status and persist it.

    Logs a "sensor_became_inactive" event when a sensor newly goes stale, and a
    "sensor_no_data" event for sensors that have never reported. Returns the
    refreshed statuses for all sensors. Useful for manual QA / demonstration.
    """
    try:
        sensors_list = get_all_sensors()
        for sensor in sensors_list:
            previous = sensor.get("communication_status")
            new_status = calculate_sensor_activity_status(sensor)
            sensor["communication_status"] = new_status

            # "Becomes inactive" is a transition, so only log when it newly goes
            # stale. A sensor that has no data yet is logged on every activity
            # check (it is a manual QA/demo endpoint) so the state is visible.
            if new_status == "inactive" and previous != "inactive":
                log_sensor_became_inactive(
                    sensor.get("sensor_id"), sensor.get("sensor_type")
                )
            elif new_status == "no_data":
                log_sensor_no_data(
                    sensor.get("sensor_id"), sensor.get("sensor_type")
                )

        save_all_sensors(sensors_list)
        return jsonify({"success": True, "sensors": get_all_sensor_statuses()})
    except Exception:
        return (
            jsonify({"success": False, "message": "Unable to check sensor activity"}),
            500,
        )


@app.route("/api/sensors/<sensor_id>/reading", methods=["POST"])
def submit_reading(sensor_id):
    """
    Ingest a sensor reading.

    Flow: parse -> validate (never trust client input) -> store if valid,
    otherwise reject and write a system log entry. Invalid readings are NEVER
    saved to readings.json.
    """
    payload = request.get_json(silent=True)

    if payload is None:
        # Malformed or missing JSON body.
        log_rejected_reading(
            sensor_id=sensor_id,
            event_type="invalid_sensor_reading",
            rejection_reason="Request body is missing or not valid JSON",
            original_payload=None,
        )
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Invalid sensor reading",
                    "errors": ["Request body must be valid JSON"],
                }
            ),
            400,
        )

    # Valid JSON body — run it through the shared ingestion pipeline (the same
    # flow used by simulation scenarios). The pipeline validates, evaluates,
    # stores, refreshes activity, and raises alerts/automation as needed.
    outcome = process_reading(sensor_id, payload)
    return jsonify(outcome["response"]), outcome["http_status"]


@app.route("/api/readings/latest")
@permission_required("view_current_readings")
def latest_readings():
    """Return the latest reading for each configured sensor."""
    try:
        return jsonify(get_latest_readings())
    except Exception:
        return jsonify({"error": "Unable to load latest readings."}), 500


@app.route("/api/sensors/<sensor_id>/readings")
@permission_required("view_reading_history")
def sensor_reading_history(sensor_id):
    """Return all stored readings for a sensor, newest first."""
    if get_sensor_by_id(sensor_id) is None:
        return (
            jsonify({"success": False, "message": "Sensor not found"}),
            404,
        )
    try:
        return jsonify(get_readings_for_sensor(sensor_id))
    except Exception:
        return jsonify({"error": "Unable to load reading history."}), 500


@app.route("/api/thresholds")
@permission_required("view_threshold_history")
def thresholds():
    """Return all configured threshold rules (read-only; editing comes later)."""
    try:
        return jsonify(get_all_rules())
    except Exception:
        return jsonify({"error": "Unable to load threshold rules."}), 500


@app.route("/api/thresholds/<sensor_type>")
@permission_required("view_threshold_history")
def threshold_for_type(sensor_type):
    """Return the threshold rule for a single sensor type, or 404 if missing."""
    try:
        rule = get_threshold_rule(sensor_type)
    except Exception:
        return jsonify({"error": "Unable to load threshold rule."}), 500
    if rule is None:
        return (
            jsonify({"success": False, "message": "Threshold rule not found"}),
            404,
        )
    return jsonify(rule)


@app.route("/api/thresholds/<sensor_type>", methods=["PUT"])
@permission_required("update_thresholds")
def update_threshold(sensor_type):
    """
    Update a single threshold rule (System Administrator only).

    Demo admin mode for this stage: the caller must send role
    "system_administrator" in the body. Full authentication / role-based
    permissions arrive in a later prompt. All values are validated server-side;
    frontend input is never trusted.
    """
    payload = request.get_json(silent=True) or {}
    # The role is taken from the verified X-User-Role header (see the
    # permission_required guard), never from the request body.
    role = get_role_from_request(request)
    min_value = payload.get("min_value")
    max_value = payload.get("max_value")
    warning_margin = payload.get("warning_margin")

    try:
        result = validate_threshold_update(
            sensor_type, min_value, max_value, warning_margin, role
        )

        # Authorization first — never reveal validation detail to an unauthorized
        # caller, and always log the attempt.
        if not result["authorized"]:
            log_rejected_update(sensor_type, role, authorized=False, errors=[])
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Only system administrators can update threshold rules",
                    }
                ),
                403,
            )

        if not result["sensor_type_supported"]:
            log_rejected_update(
                sensor_type,
                role,
                authorized=True,
                errors=["Unsupported sensor type"],
            )
            return (
                jsonify({"success": False, "message": "Unsupported sensor type"}),
                400,
            )

        if result["errors"]:
            log_rejected_update(
                sensor_type, role, authorized=True, errors=result["errors"]
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Invalid threshold update",
                        "errors": result["errors"],
                    }
                ),
                400,
            )

        updated = update_threshold_rule(
            sensor_type, min_value, max_value, warning_margin, role
        )
        if updated is None:
            # Validated as supported, but no stored rule for it — treat as unknown.
            log_rejected_update(
                sensor_type,
                role,
                authorized=True,
                errors=["Unsupported sensor type"],
            )
            return (
                jsonify({"success": False, "message": "Unsupported sensor type"}),
                400,
            )
    except Exception:
        return (
            jsonify({"success": False, "message": "Unable to update threshold rule"}),
            500,
        )

    return jsonify(
        {
            "success": True,
            "message": "Threshold rule updated successfully",
            "threshold": updated,
        }
    )


@app.route("/api/alerts/active")
@permission_required("view_active_alerts")
def active_alerts():
    """Active alerts, ordered critical-first then newest-first."""
    try:
        return jsonify(get_active_alerts())
    except Exception:
        return jsonify({"error": "Unable to load active alerts."}), 500


@app.route("/api/alerts/history")
@permission_required("view_alert_history")
def alert_history():
    """All alerts (active + resolved), newest-first."""
    try:
        return jsonify(get_alert_history())
    except Exception:
        return jsonify({"error": "Unable to load alert history."}), 500


@app.route("/api/sensors/<sensor_id>/alerts")
@permission_required("view_alert_history")
def sensor_alerts(sensor_id):
    """All alerts for a single sensor (404 if the sensor is unknown)."""
    if get_sensor_by_id(sensor_id) is None:
        return (
            jsonify({"success": False, "message": "Sensor not found"}),
            404,
        )
    try:
        return jsonify(get_alerts_for_sensor(sensor_id))
    except Exception:
        return jsonify({"error": "Unable to load sensor alerts."}), 500


@app.route("/api/alerts/<alert_id>/resolve", methods=["PATCH"])
@permission_required("resolve_alerts")
def resolve_alert_endpoint(alert_id):
    """
    Resolve an active alert. Only status and resolved_at change.

    Unknown id -> 404; already resolved -> safe 200; resolved -> 200 with alert.
    """
    try:
        result = resolve_alert(alert_id)
    except Exception:
        return jsonify({"success": False, "message": "Unable to resolve alert"}), 500

    if result["outcome"] == "not_found":
        log_alert_resolve_failed(alert_id=alert_id, reason="alert not found")
        return jsonify({"success": False, "message": "Alert not found"}), 404

    if result["outcome"] == "already_resolved":
        return jsonify(
            {
                "success": True,
                "message": "Alert is already resolved",
                "alert": result["alert"],
            }
        )

    log_alert_resolved(
        alert_id=alert_id, sensor_id=result["alert"].get("sensor_id")
    )
    return jsonify(
        {
            "success": True,
            "message": "Alert resolved",
            "alert": result["alert"],
        }
    )


@app.route("/api/actuators")
@permission_required("view_automation_status", "reset_actuators")
def actuators():
    """All actuators and their current status."""
    try:
        return jsonify(get_all_actuators())
    except Exception:
        return jsonify({"error": "Unable to load actuators."}), 500


@app.route("/api/automation/actions")
@permission_required("view_automation_history", "reset_actuators")
def automation_actions():
    """All automation actions, newest-first."""
    try:
        return jsonify(get_all_actions())
    except Exception:
        return jsonify({"error": "Unable to load automation actions."}), 500


@app.route("/api/automation/active")
@permission_required("view_automation_status", "reset_actuators")
def automation_active():
    """Currently active automation responses (active actuator actions)."""
    try:
        return jsonify(get_active_actions())
    except Exception:
        return jsonify({"error": "Unable to load active automation."}), 500


@app.route("/api/actuators/<actuator_id>/reset", methods=["PATCH"])
@permission_required("reset_actuators")
def reset_actuator_endpoint(actuator_id):
    """
    Reset an actuator to inactive. Only status / activation metadata change.

    Unknown id -> 404; already inactive -> safe 200; reset -> 200 with actuator.
    """
    try:
        result = reset_actuator_status(actuator_id)
    except Exception:
        return jsonify({"success": False, "message": "Unable to reset actuator"}), 500

    if result["outcome"] == "not_found":
        return jsonify({"success": False, "message": "Actuator not found"}), 404

    if result["outcome"] == "already_inactive":
        return jsonify(
            {
                "success": True,
                "message": "Actuator is already inactive",
                "actuator": result["actuator"],
            }
        )

    return jsonify(
        {
            "success": True,
            "message": "Actuator reset to inactive",
            "actuator": result["actuator"],
        }
    )


@app.route("/api/analytics/summary")
@permission_required("view_basic_analytics")
def analytics_summary():
    """
    Full dashboard analytics summary (read-only): averages, alert counts, the
    most frequent abnormal condition, recent trends, health status, and score.

    Everything is computed server-side from stored records; the client never
    supplies any analytics value. Failures return a safe generic message.
    """
    try:
        summary = get_dashboard_analytics_summary()
    except Exception:
        log_analytics_calculation_failed("dashboard summary")
        return (
            jsonify({"success": False, "message": "Unable to generate analytics"}),
            500,
        )

    log_analytics_summary_generated()
    return jsonify({"success": True, "analytics": summary})


@app.route("/api/analytics/health")
@permission_required("view_greenhouse_health_status", "view_greenhouse_health_score")
def analytics_health():
    """
    Greenhouse health status + score (read-only).

    Returns health_status, explanation, score, and interpretation, all derived
    server-side from current sensor state and active alerts.
    """
    try:
        state = collect_current_state()
        status = calculate_greenhouse_health_status(state)
        score = calculate_greenhouse_health_score(state)
    except Exception:
        log_analytics_calculation_failed("greenhouse health")
        return (
            jsonify({"success": False, "message": "Unable to calculate health"}),
            500,
        )

    log_health_score_calculated(score["score"], score["interpretation"])
    return jsonify(
        {
            "success": True,
            "health_status": status["health_status"],
            "explanation": status["explanation"],
            "score": score["score"],
            "interpretation": score["interpretation"],
        }
    )


@app.route("/api/analytics/trends")
@permission_required("view_basic_analytics")
def analytics_trends():
    """Recent trend for each supported sensor type (read-only)."""
    try:
        trends = get_recent_trends_for_all_sensors()
    except Exception:
        log_analytics_calculation_failed("sensor trends")
        return (
            jsonify({"success": False, "message": "Unable to calculate trends"}),
            500,
        )

    return jsonify({"success": True, "recent_trends": trends})


@app.route("/api/simulation/scenarios")
@permission_required("run_simulation_scenarios")
def simulation_scenarios():
    """List all predefined simulation scenarios (read-only)."""
    try:
        scenarios = get_available_scenarios()
    except Exception:
        return (
            jsonify({"success": False, "message": "Unable to load scenarios"}),
            500,
        )
    return jsonify({"success": True, "scenarios": scenarios})


@app.route("/api/simulation/run/<scenario_id>", methods=["POST"])
@permission_required("run_simulation_scenarios")
def run_scenario(scenario_id):
    """
    Run one predefined simulation scenario.

    Only predefined scenario ids are accepted — the backend generates the
    readings (relative to the current thresholds) and processes them through the
    same ingestion pipeline as normal readings (validate -> rule engine ->
    storage -> alerts -> automation). Unknown ids return a safe 404. Lifecycle
    events are logged (started / completed / failed / unknown).
    """
    if get_scenario_by_id(scenario_id) is None:
        log_unknown_simulation_scenario(scenario_id)
        return (
            jsonify({"success": False, "message": "Unknown simulation scenario"}),
            404,
        )

    log_simulation_scenario_started(scenario_id)
    try:
        result = run_simulation_scenario(scenario_id)
    except ValueError:
        # The scenario could not run end to end (e.g. the generated reading was
        # rejected by the pipeline). This is a known, safe failure -> 422.
        log_simulation_scenario_failed(scenario_id, "reading rejected by pipeline")
        return (
            jsonify({"success": False, "message": "Simulation scenario could not be completed"}),
            422,
        )
    except Exception:
        # Never leak internal details; record the failure and return a safe message.
        log_simulation_scenario_failed(scenario_id, "scenario execution error")
        return (
            jsonify({"success": False, "message": "Simulation scenario failed"}),
            500,
        )

    log_simulation_scenario_completed(scenario_id)
    return jsonify(result), 200


@app.route("/api/logs")
@permission_required("view_system_logs")
def system_logs():
    """
    Return the system log entries, newest first (System Administrator only).

    This exposes the existing audit trail in data/system_logs.json — including
    rejected readings, threshold/sensor changes, automation events, and the
    role-based access denials recorded by the permission guard — for admin review.
    """
    try:
        return jsonify({"success": True, "logs": get_logs()})
    except Exception:
        return (
            jsonify({"success": False, "message": "Unable to load system logs"}),
            500,
        )


if __name__ == "__main__":
    # Bind to 0.0.0.0:5000 so the Replit preview proxy can reach the app.
    port = int(os.environ.get("PORT", 5000))
    # Debug is OFF by default so unhandled errors never leak stack traces /
    # the interactive debugger. Opt in locally with FLASK_DEBUG=1 if needed.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
