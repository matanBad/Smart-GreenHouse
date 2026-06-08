---
name: Smart Greenhouse multi-prompt conventions
description: Durable decisions for the academic multi-prompt Greenhouse MVP (rule engine, security, scope).
---

# Smart Greenhouse IoT — durable decisions

## Threshold edits apply forward-only; updates are admin-gated and server-validated
Threshold rules are editable via `PUT /api/thresholds/<sensor_type>` but only by
a `system_administrator` (admin-gated). NOTE: as of Prompt 10 the role comes from
the `X-User-Role` HEADER via the `permission_required("update_thresholds")`
decorator — NOT the request body (the older body-`role` check was removed; do not
reintroduce it). See the header-based RBAC section below.
The server validates everything (role, sensor_type in the four known types, all
three values numeric, warning_margin>=0, min<max) — never trust the frontend.
A successful edit only changes the one matching rule (preserving rule_id/unit/
severity_levels) and is logged `threshold_rule_updated` with old+new values+role;
rejects are logged `unauthorized_threshold_update_attempt` /
`invalid_threshold_update_attempt`. The rule engine reads rules fresh per reading,
so edits apply to FUTURE readings only — never recalculate stored readings/alerts.
**Why:** PRD requires forward-only application + audited, privileged edits.
**How to apply:** keep edit logic in `services/threshold_service.py`; system log
model carries a generic optional `details` dict for structured event data.

## Threshold warning-band is margin-inclusive
A reading is `warning` when its value is **at or within** `warning_margin` of a
limit (e.g. min=18, margin=2 → value 20 is warning; max=30 → value 28 is warning;
exact limits 18/30 are also warning). Critical (`< min` or `> max`) is checked first.
**Why:** code review flagged strict `<`/`>` as under-flagging boundary values; an
alerting system should err toward warning at the edge.
**How to apply:** keep `is_near_threshold` using `<=`/`>=` in `services/rule_engine.py`.

## Flask debug must stay OFF in this project
`app.run(debug=...)` is env-gated and defaults to **False** (opt in with
`FLASK_DEBUG=1`). **Why:** the PRD security requirement forbids leaking stack
traces / the interactive debugger. Do not re-enable `debug=True` unconditionally
in any future prompt.

## Test-data hygiene between prompts
After QA testing, reset `data/readings.json`, `data/alerts.json`,
`data/system_logs.json`, and `data/automation_actions.json` to `[]`, and reset
`data/actuators.json` so every actuator is `status:"inactive"` with
`last_activation_time:null` and `last_trigger_reason:null`. This keeps stale
records (readings, alerts, logs, automation actions, latched actuator state) from
polluting the dashboard or the next prompt's verification.

## Automation is server-derived and CRITICAL-only
Automation responses are created only in `services/automation_service`, triggered
from the reading POST and **only when the rule-engine status is `critical`**
(warning/normal never trigger). The reason→actuator map is fixed
(temperature_too_high→ventilation, soil_moisture_too_low→irrigation,
light_intensity_too_low→lighting, humidity_too_high→air_circulation); unmapped
critical reasons log `unsupported_automation_rule` and do nothing.
**Why:** same server-owns-classification model as alerts — clients submit raw
readings only; the server decides whether to actuate.
**How to apply:** never trigger automation from client input or on warning; keep
the action_type `activate_<actuator_type>` convention. Reset is the only client
mutation and just flips status back to inactive + deactivates its active actions.

## Alerts are server-derived, never client-trusted
Alerts are created only in `services/alert_service.create_alert`, called from the
reading POST when rule-engine status is `warning`/`critical`. Severity == the
rule-engine `reading_status`; never read severity/alert fields from the request.
**Why:** PRD security model — clients submit raw readings only; the server owns
classification and alerting.
**How to apply:** if a future prompt adds alert mutation, keep severity sourced
from server-side evaluation. Resolve only ever changes `status` + `resolved_at`.

## Alert generation failure must stay observable
The reading POST swallows alert-creation exceptions (the reading is already
stored) but logs an `alert_generation_failed` system-log entry before continuing.
**Why:** code review flagged silently dropping a required alert as an operational
blind spot. Do not remove that failure log when refactoring the POST flow.

## Sensor model expanded + communication status is derived
The sensor record uses sensor_id, greenhouse_id, sensor_type, sensor_name, unit,
location, status (enabled/disabled), expected_frequency_seconds,
last_valid_reading_at, communication_status, created_at, updated_at.
`communication_status` is DERIVED, never client-set: no last_valid_reading_at →
`no_data`; (now − last) <= expected_frequency_seconds*2 → `active`; older →
`inactive`. A valid reading refreshes last_valid_reading_at (set from SERVER ingestion time,
NEVER the client-supplied reading timestamp, so activity cannot be spoofed) +
recomputes status but does NOT bump updated_at (updated_at = config edits only).
**Why:** PRD wants activity/offline detection independent of config audit trail.
**How to apply:** keep the staleness multiplier (×2) and the derive logic in
`services/sensor_service.calculate_sensor_activity_status`.

## Sensor config edits are admin-gated; only 3 fields editable
`PUT /api/sensors/<sensor_id>` is admin-gated (system_administrator). NOTE: as of
Prompt 10 the role comes from the `X-User-Role` HEADER via
`permission_required("update_sensor_configuration")`, NOT the request body (the
older body-`role` check was removed). Only sensor_name, unit, status are editable;
sensor_id & sensor_type are
IMMUTABLE (attempting to change them → 400 with errors[]), and unit must match
the sensor type (temp C/F, humidity %, soil %, light lux). Route order:
auth(403) → sensor_found(404) → validation(400). Logs:
sensor_configuration_updated / unauthorized_sensor_update / invalid_sensor_update.
**Why:** same server-owns-truth model as thresholds; identity fields must be stable.
**How to apply:** keep validate/update in `services/sensor_service.py`.

## check-activity logging: inactive on transition, no_data every check
`POST /api/sensors/check-activity` recomputes + persists statuses. It logs
`sensor_became_inactive` ONLY on transition (previous != inactive), but logs
`sensor_no_data` every time a sensor has no data during the check (it is a manual
QA/demo endpoint, so visibility beats dedup).
**Why:** "becomes inactive" is transitional per PRD; "has no data yet during
activity check" reads as per-check, not transitional.
**How to apply:** keep this asymmetry in the check-activity route in app.py.

## Analytics layer is read-only and derives from a SINGLE state snapshot
`services/analytics_service.py` computes averages (valid readings only — rejected
readings are never stored, so exclusion is automatic), alert counts per type,
most-frequent abnormal condition, recent trends, greenhouse health status, and a
0–100 health score. It NEVER mutates state. Health status AND score must be
derived from ONE `collect_current_state()` snapshot (pass it into both
`calculate_greenhouse_health_status(state)` and
`calculate_greenhouse_health_score(state)`) so they cannot diverge within one
response. Trend: up to 5 newest readings, latest vs oldest with a
magnitude-scaled tolerance for `stable`, `insufficient_data` when <2 readings.
Score starts 100 with weighted penalties (warning/critical sensors, active
warning/critical alerts, inactive/no_data), clamped 0–100, interp
good>=80/moderate>=50/poor.
**Why:** code review flagged that computing status and score from two separate
snapshots lets them diverge if a sensor crosses active/inactive or an alert
changes between calls. The score is server-only; clients never compute or submit it.
**How to apply:** keep analytics read-only; route-level try/except logs
`analytics_calculation_failed` + returns a generic 500; summary logs
`analytics_summary_generated`, health logs `health_score_calculated`. Logging
lives in the routes, not the service, to keep the service pure/read-only.

## Dashboard refresh buttons need visible feedback (no-op refreshes look broken)
Refresh buttons whose work often produces NO visible change (e.g. Automation
Status when all actuators are inactive) are routed through `withButtonFeedback`
in `static/js/dashboard.js`, which disables the button + shows transient
"Refreshing…"→"Updated" text. For this to await real completion, fan-out loaders
must RETURN their promises (e.g. `loadAutomation` returns
`Promise.all([loadActuators(), loadAutomationHistory()])`), not fire-and-forget.
**Why:** a user reported the refresh "does nothing" — the fetch succeeded (200s
in logs) but inactive state re-rendered identically, so the button felt dead.
**How to apply:** keep new refresh buttons wrapped in `withButtonFeedback`; make
any awaited loader return its promise.

## Simulation scenarios reuse the real pipeline; values are threshold-relative
Predefined scenarios (`data/simulation_scenarios.json`: hot_day, dry_soil,
high_humidity, low_light) are run via `POST /api/simulation/run/<scenario_id>`
(list at `GET /api/simulation/scenarios`). The BACKEND generates the reading —
clients pick only a predefined scenario_id, never submit values or custom
scenarios. Value is computed RELATIVE to the CURRENT threshold read fresh
(above_max→max+offset, below_min→min−offset), so a scenario keeps breaching even
after an admin edits the threshold. The reading's sensor_type AND unit are also
read from the LIVE sensor config (`get_sensor_by_id`), NOT the scenario's static
fields — otherwise an admin editing a sensor's unit (e.g. temperature C↔F) makes
the scenario's hardcoded unit mismatch and validation rejects it. Generated
readings go through the SAME ingestion pipeline as normal readings — never a
shortcut. After running, the runner checks each pipeline outcome's `ok` flag and
raises ValueError if any reading was rejected (route maps that to a safe 422 +
`simulation_scenario_failed` log) — never report success on a rejected reading.
**Why:** PRD requires scenarios exercise real validate→rule-engine→storage→
alerts→automation logic, not fabricated alerts.
**How to apply:** the shared flow lives in `services/reading_pipeline.process_reading`
(extracted from the reading POST so both routes share one path);
`services/simulation_service.py` stays pure (no logging, no HTTP). Readings/alerts/
automation_actions carry `source="simulation_scenario"` + `scenario_id` provenance
(alert inherits from reading, action inherits from alert). Route logs lifecycle
(unknown→404, started, completed, failed→500); service raises ValueError on
unknown/ungeneratable scenario.

## Access control is demo RBAC via header, backend-enforced, no body-role
Three roles (greenhouse_manager, farm_owner, system_administrator) gate every
protected endpoint. The active role comes from the `X-User-Role` REQUEST HEADER —
never the request body. `services/access_control_service.py` is PURE (matrix +
helpers, no Flask/logging); `app.py`'s `permission_required(*actions)` decorator
is the single enforcement point: missing/invalid role → 401 "Missing or invalid
user role"; valid role lacking the action → 403 "You are not authorized to
perform this action"; both log a denial (role, attempted_action, endpoint) via
`log_unauthorized_access_attempt` / `log_invalid_role_attempt`. Permissions are
any-of (a route can list multiple actions). Public routes (NO decorator): GET /,
GET /api/health, POST /api/sensors/<id>/reading (device ingestion). The threshold
and sensor PUTs were SWITCHED from body `role:` to the header in this prompt, so a
spoofed body role can no longer escalate — do not reintroduce body-role checks.
**Why:** PRD wants role-based permissions; the server must own enforcement and the
role channel must be un-spoofable from the JSON payload. Demo-level only — no
passwords/JWT/sessions; users.json stays metadata.
**How to apply:** add new protected routes by decorating with the matching
action(s); add the action→roles entry to ROLE_PERMISSIONS. Frontend mirrors (not
enforces) this: `apiFetch` injects the header, `data-roles` attributes +
`applyRoleVisibility()` hide sections, and `loadForRole()` only fetches what the
role may access so the UI never fires a request the backend would deny. Admin-only
`GET /api/logs` (action view_system_logs) exposes the system log to the dashboard.
