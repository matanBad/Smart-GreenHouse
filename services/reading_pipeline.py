"""
reading_pipeline.py -> Shared Sensor Reading Processing Pipeline

A single, authoritative implementation of the reading ingestion flow:

    validate -> rule-engine evaluate -> store -> refresh activity
             -> generate alert (warning/critical) -> trigger automation (critical)

Both the public reading endpoint (`POST /api/sensors/<sensor_id>/reading`) and
the predefined simulation scenarios (`POST /api/simulation/run/<scenario_id>`)
run readings through THIS function, so simulated readings never bypass the real
backend logic — they are validated, evaluated, alerted, and automated exactly
like normal readings.

`source` / `scenario_id` mark provenance and propagate from the reading into any
alert and automation action it produces (None for normal readings, set for
simulation-scenario readings).

The function never raises for an expected outcome (invalid reading, missing
rule, storage hiccup). It returns a structured result the caller turns into an
HTTP response:

    {
        "ok": bool,            # True only when a reading was stored
        "http_status": int,    # suggested HTTP status code
        "response": dict,      # JSON body for the caller to return
        "reading": dict|None,  # the stored reading (or None)
        "alert": dict|None,    # the generated alert (or None)
        "automation_action": dict|None,  # the automation action (or None)
    }
"""

from services.validation_service import validate_sensor_reading
from services.rule_engine import apply_threshold_evaluation
from services.sensor_service import save_reading, update_sensor_last_valid_reading
from services.alert_service import create_alert
from services.automation_service import trigger_automation_for_alert
from services.log_service import (
    log_rejected_reading,
    log_missing_threshold_rule,
    log_alert_generated,
    log_alert_generation_failed,
    log_automation_trigger_failed,
)


def process_reading(sensor_id, payload, source=None, scenario_id=None):
    """
    Run one reading payload through the full ingestion pipeline.

    `payload` must be a dict (the caller is responsible for JSON parsing and the
    malformed-body case). Returns the structured result documented above.
    """
    # 1) Validate — never trust the input. Invalid readings are logged and never
    #    stored.
    result = validate_sensor_reading(sensor_id, payload)
    if not result["is_valid"]:
        event_type = result["codes"][0] if result["codes"] else "invalid_sensor_reading"
        log_rejected_reading(
            sensor_id=sensor_id,
            event_type=event_type,
            rejection_reason="; ".join(result["errors"]),
            original_payload=payload,
        )
        status_code = 404 if "unknown_sensor_id" in result["codes"] else 400
        return {
            "ok": False,
            "http_status": status_code,
            "response": {
                "success": False,
                "message": "Invalid sensor reading",
                "errors": result["errors"],
            },
            "reading": None,
            "alert": None,
            "automation_action": None,
        }

    # 2) Evaluate against the threshold rules (server-side only). The caller never
    #    supplies reading_status; it is always computed here.
    sensor_type = payload.get("sensor_type")
    value = payload.get("value")
    evaluation = apply_threshold_evaluation(
        {"sensor_type": sensor_type, "value": value}
    )

    if evaluation["status"] is None:
        # Valid but unclassifiable — no threshold rule for this sensor type.
        log_missing_threshold_rule(sensor_id=sensor_id, sensor_type=sensor_type)
        return {
            "ok": False,
            "http_status": 422,
            "response": {
                "success": False,
                "message": "Reading could not be evaluated: no threshold rule configured",
            },
            "reading": None,
            "alert": None,
            "automation_action": None,
        }

    # 3) Store with the server-computed status and provenance.
    try:
        reading = save_reading(
            sensor_id=sensor_id,
            sensor_type=sensor_type,
            value=value,
            unit=payload.get("unit"),
            timestamp=payload.get("timestamp"),
            reading_status=evaluation["status"],
            source=source,
            scenario_id=scenario_id,
        )
    except Exception:
        return {
            "ok": False,
            "http_status": 500,
            "response": {"success": False, "message": "Unable to store reading"},
            "reading": None,
            "alert": None,
            "automation_action": None,
        }

    # 4) Refresh the sensor's activity from the SERVER ingestion time (best-effort;
    #    a stored reading must not fail just because activity tracking hiccuped).
    try:
        update_sensor_last_valid_reading(sensor_id)
    except Exception:
        pass

    # 5) Warning/critical readings raise an alert (severity from the rule engine,
    #    never from input). The alert inherits the reading's provenance.
    alert = None
    if evaluation["status"] in ("warning", "critical"):
        try:
            alert = create_alert(reading, evaluation["rule"], evaluation["status"])
            log_alert_generated(
                alert_id=alert["alert_id"],
                sensor_id=alert["sensor_id"],
                severity=alert["severity"],
                alert_type=alert["alert_type"],
            )
        except Exception:
            alert = None
            try:
                log_alert_generation_failed(
                    sensor_id=sensor_id,
                    reading_id=reading.get("reading_id"),
                    reason="alert creation error",
                )
            except Exception:
                pass

    # 6) Critical alerts drive a simulated automation response. The action
    #    inherits the alert's provenance.
    automation_action = None
    if alert is not None and alert.get("severity") == "critical":
        try:
            automation_action = trigger_automation_for_alert(alert)
        except Exception:
            automation_action = None
            try:
                log_automation_trigger_failed(
                    alert_id=alert.get("alert_id"),
                    sensor_id=sensor_id,
                    reason="automation controller error",
                )
            except Exception:
                pass

    if alert is None:
        message = "Sensor reading saved successfully"
    elif alert.get("severity") == "warning":
        message = "Sensor reading saved and warning alert generated"
    elif automation_action is not None:
        message = (
            "Sensor reading saved, critical alert generated, "
            "and automation response triggered"
        )
    else:
        message = "Sensor reading saved and critical alert generated"

    return {
        "ok": True,
        "http_status": 201,
        "response": {
            "success": True,
            "message": message,
            "reading": reading,
            "alert": alert,
            "automation_action": automation_action,
        },
        "reading": reading,
        "alert": alert,
        "automation_action": automation_action,
    }
