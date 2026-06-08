"""
simulation_service.py -> Predefined Simulation Scenarios

PRD area: Run predefined simulation scenarios (FR-44) such as Hot Day, Dry Soil,
High Humidity, and Low Light.

Design principles:
- Scenarios are PREDEFINED only. Arbitrary client-supplied readings or custom
  scenarios are not accepted in this prompt — callers select a scenario_id and
  the backend generates the readings.
- Generated values are computed RELATIVE to the current threshold rules
  (read fresh from threshold_rules.json), never hardcoded, so a scenario keeps
  breaching the threshold even after an admin edits it.
- Generated readings are processed through the SAME ingestion pipeline as normal
  readings (`services.reading_pipeline.process_reading`) — they are validated,
  rule-evaluated, stored, and may raise alerts and automation. Scenarios never
  bypass the real backend logic.

This module is pure orchestration: it does not log scenario lifecycle events or
return HTTP responses (the route handles logging and status codes), keeping the
service focused and testable.
"""

from datetime import datetime, timezone

from services.storage_service import read_json
from services.rule_engine import get_threshold_rule
from services.sensor_service import get_sensor_by_id
from services.reading_pipeline import process_reading

SCENARIOS_FILE = "simulation_scenarios.json"
SOURCE = "simulation_scenario"

# Public, descriptive fields exposed by the scenarios API. Internal generation
# fields (value_strategy, offset) are intentionally not part of the contract.
_PUBLIC_FIELDS = (
    "scenario_id",
    "name",
    "description",
    "expected_result",
    "sensor_id",
    "sensor_type",
    "unit",
)


def _now_iso():
    """Current UTC time as an ISO-8601 string (used for generated timestamps)."""
    return datetime.now(timezone.utc).isoformat()


def _public_view(scenario):
    """Return only the public, contract-stable fields of a scenario."""
    return {field: scenario.get(field) for field in _PUBLIC_FIELDS}


def get_available_scenarios():
    """Return all predefined scenarios (public fields only)."""
    scenarios = read_json(SCENARIOS_FILE, default=[])
    return [_public_view(s) for s in scenarios]


def get_scenario_by_id(scenario_id):
    """Return the full scenario definition for an id, or None if unknown."""
    scenarios = read_json(SCENARIOS_FILE, default=[])
    for scenario in scenarios:
        if scenario.get("scenario_id") == scenario_id:
            return scenario
    return None


def _compute_scenario_value(scenario):
    """
    Compute the reading value relative to the CURRENT threshold for the
    scenario's sensor type. Returns None if no threshold rule is configured.

    - above_max -> max_value + offset
    - below_min -> min_value - offset
    """
    rule = get_threshold_rule(scenario.get("sensor_type"))
    if rule is None:
        return None

    offset = scenario.get("offset", 5)
    strategy = scenario.get("value_strategy")
    if strategy == "above_max":
        return rule.get("max_value") + offset
    if strategy == "below_min":
        return rule.get("min_value") - offset
    return None


def generate_scenario_readings(scenario_id):
    """
    Build the controlled reading payload(s) for a scenario, relative to the
    current thresholds. Returns a list of reading payloads (always a list so the
    pipeline can process each one). Returns an empty list if the scenario is
    unknown or has no configured threshold rule.

    Each payload carries the full reading shape required by validation
    (sensor_id, sensor_type, value, unit, timestamp) — the backend, not the
    client, decides these values.
    """
    scenario = get_scenario_by_id(scenario_id)
    if scenario is None:
        return []

    value = _compute_scenario_value(scenario)
    if value is None:
        return []

    # Build the payload from the sensor's CURRENT configuration (type + unit)
    # rather than the scenario's static fields, so a scenario stays valid even
    # after an admin edits the sensor (e.g. switches temperature C <-> F). This
    # mirrors how the value tracks the current threshold. If the sensor is gone,
    # the scenario cannot run.
    sensor = get_sensor_by_id(scenario.get("sensor_id"))
    if sensor is None:
        return []

    payload = {
        "sensor_id": sensor.get("sensor_id"),
        "sensor_type": sensor.get("sensor_type"),
        "value": value,
        "unit": sensor.get("unit"),
        "timestamp": _now_iso(),
    }
    return [payload]


def build_scenario_result(scenario_id, readings, alerts, automation_actions):
    """
    Assemble the API result for a completed scenario run.

    `readings`, `alerts`, and `automation_actions` are the records actually
    produced by the pipeline (alerts/actions may be empty if a reading did not
    breach a threshold or was non-critical).
    """
    scenario = get_scenario_by_id(scenario_id) or {}
    return {
        "success": True,
        "scenario_id": scenario_id,
        "scenario_name": scenario.get("name"),
        "message": "Simulation scenario completed successfully",
        "generated_readings": readings,
        "alerts": alerts,
        "automation_actions": automation_actions,
        "expected_result": scenario.get("expected_result"),
    }


def run_simulation_scenario(scenario_id):
    """
    Run one predefined scenario end to end and return the assembled result.

    Generates the controlled reading(s), processes each through the shared
    ingestion pipeline (validation -> rule engine -> storage -> alerts ->
    automation), and collects the produced records. Raises ValueError if the
    scenario is unknown or cannot generate a valid reading, so the route can map
    it to a safe response.
    """
    scenario = get_scenario_by_id(scenario_id)
    if scenario is None:
        raise ValueError(f"Unknown scenario: {scenario_id}")

    payloads = generate_scenario_readings(scenario_id)
    if not payloads:
        raise ValueError(f"Could not generate readings for scenario: {scenario_id}")

    readings = []
    alerts = []
    automation_actions = []

    for payload in payloads:
        outcome = process_reading(
            payload.get("sensor_id"),
            payload,
            source=SOURCE,
            scenario_id=scenario_id,
        )
        # If the shared pipeline rejected the generated reading (e.g. an admin
        # changed the sensor's unit so it no longer matches), the scenario did
        # NOT run end to end. Surface that as a failure instead of silently
        # reporting success with empty results.
        if not outcome.get("ok"):
            raise ValueError(
                f"Generated reading for scenario '{scenario_id}' was rejected by the pipeline"
            )
        if outcome.get("reading"):
            readings.append(outcome["reading"])
        if outcome.get("alert"):
            alerts.append(outcome["alert"])
        if outcome.get("automation_action"):
            automation_actions.append(outcome["automation_action"])

    return build_scenario_result(scenario_id, readings, alerts, automation_actions)
