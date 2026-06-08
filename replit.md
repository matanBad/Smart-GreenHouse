# Smart Greenhouse IoT System

An IoT-based smart greenhouse simulation. Four virtual sensors feed a REST API that will (over future prompts) validate readings, evaluate threshold rules, raise alerts, simulate automation, store data, and visualize it on a dashboard.

## Status

**Prompt 10 — Role-Based Access Control (demo).** Three roles — `greenhouse_manager`, `farm_owner`, `system_administrator` — now gate every protected endpoint. The active role is declared per request via the `X-User-Role` header (demo-level only: NO passwords, JWT, or sessions; `users.json` stays metadata). `services/access_control_service.py` (pure) holds the `ROLE_PERMISSIONS` matrix, `VALID_ROLES`, and helpers: `get_role_from_request` (reads the header), `normalize_role`, `is_valid_role`, `has_permission` (any-of), `require_permission(role, action|actions) → {"allowed", "error": None/"invalid_role"/"forbidden"}`, `get_allowed_actions_for_role`, and `log_unauthorized_attempt` (branches to invalid-role vs unauthorized). The backend is the single source of truth: a `permission_required(*actions)` decorator in `app.py` wraps each protected route, returning 401 ("Missing or invalid user role") when the role is missing/invalid and 403 ("You are not authorized to perform this action") when the role lacks the action, logging every denial. The threshold and sensor PUTs now read the role from the header (no longer from the request body), so a body-spoofed role can no longer escalate. Public routes remain open: `GET /`, `GET /api/health`, and `POST /api/sensors/<id>/reading` (device ingestion). A new admin-only `GET /api/logs` (action `view_system_logs`) exposes the system log. The dashboard gained a header role selector (persisted to localStorage); all API calls flow through an `apiFetch` wrapper that injects the `X-User-Role` header; sections carry `data-roles` and are shown/hidden per role; and the client only loads data the active role may access (never firing requests it would be denied). A new System Logs section (admin only) renders the log table. Full authentication and ML/prediction remain out of scope for future prompts.

**Prompt 9 — Predefined Simulation Scenarios.** Four predefined scenarios (Hot Day, Dry Soil, High Humidity, Low Light) let users demonstrate the full system end to end. The reading-ingestion flow was extracted into `services/reading_pipeline.py` (`process_reading`) so the reading POST and the simulation runner share ONE path — simulated readings go through the exact same logic (validate → rule engine → storage → alerts → automation), never a shortcut. `services/simulation_service.py` (pure: no logging, no HTTP) lists scenarios, generates the controlled reading for a scenario, and runs it. Crucially, the backend generates each reading's value RELATIVE to the current threshold read fresh (`above_max` → max+offset, `below_min` → min−offset), so a scenario keeps breaching even after an admin edits the threshold; clients only pick a predefined `scenario_id` and never submit values or custom scenarios. Readings, alerts, and automation actions carry `source="simulation_scenario"` + `scenario_id` provenance (alert inherits from its reading, action from its alert). Two endpoints expose this: `GET /api/simulation/scenarios` (list) and `POST /api/simulation/run/<scenario_id>` (run; unknown id → safe 404). The route logs lifecycle (`simulation_scenario_started/completed/failed`, `unknown_simulation_scenario`) and returns safe generic messages on failure. The dashboard gained a Simulation Scenarios section (one card + Run button per scenario, plus a result panel) that refreshes readings, alerts, automation, and analytics after a run. Full authentication, role-based permissions, and ML/prediction remain out of scope for future prompts.

**Prompt 8 — Dashboard Analytics & Greenhouse Health Score.** A read-only analytics layer derives insights from already-stored data. `services/analytics_service.py` (previously a placeholder) now computes: average value per sensor type (valid readings only), alert counts per sensor type (active + total), the most frequent abnormal condition (alert type), recent trend per sensor type (up to the 5 newest readings; latest vs. oldest with a magnitude-scaled tolerance → `increasing`/`decreasing`/`stable`, and `insufficient_data` when fewer than 2 readings), an overall greenhouse health status (`healthy`/`needs_attention`/`critical` with a plain-language explanation), and a 0–100 greenhouse health score (starts at 100, weighted penalties for warning/critical sensors, active warning/critical alerts, and inactive/no_data sensors, clamped to 0–100, interpreted `good`/`moderate`/`poor`). Health status and score are derived from a SINGLE current-state snapshot (`collect_current_state()`) so they never diverge within one response. Three new read-only endpoints expose this (`GET /api/analytics/summary`, `/api/analytics/health`, `/api/analytics/trends`), each wrapped in safe error handling that logs `analytics_calculation_failed` and returns a generic 500. The dashboard gained a Farm Owner Summary section (health status, score, active-alert count, most frequent issue) and a Dashboard Analytics section (averages, alert counts, trends, score) with a Refresh Analytics button. All analytics are computed server-side; the client only renders.

- Prompt 1 — Project foundation (dashboard, health, sensors endpoint).
- Prompt 2 — Reading ingestion, validation, storage, latest/history APIs, rejected-reading logs.
- Prompt 3 — Threshold rules, rule engine, server-side status evaluation, thresholds API, dashboard status display.
- Prompt 4 — Alert generation on warning/critical readings, recommended actions, alert query + resolve APIs, dashboard Active Alerts UI, alert lifecycle logging.
- Prompt 5 — Simulated automation on critical readings, virtual actuators, automation action records, actuator/automation query + reset APIs, dashboard Automation Status + History UI, automation lifecycle logging.
- Prompt 6 — Admin-gated threshold editing (PUT with demo admin role), server-side validation, threshold-change logging, forward-only application, dashboard Threshold Management UI.
- Prompt 7 — Expanded sensor model, admin-gated sensor config editing (PUT), derived communication status (active/inactive/no_data), activity refresh on valid readings, sensor status + check-activity APIs, sensor-management logging, dashboard Sensor Management UI.
- Prompt 8 — Read-only dashboard analytics (averages, alert counts, most frequent abnormal condition, recent trends), greenhouse health status + 0–100 health score from a single state snapshot, analytics APIs, analytics logging, dashboard Farm Owner Summary + Dashboard Analytics UI.
- Prompt 9 — Predefined simulation scenarios (Hot Day, Dry Soil, High Humidity, Low Light), shared reading pipeline so simulated readings run through the real validate→rule-engine→storage→alerts→automation flow, threshold-relative value generation, source/scenario_id provenance, scenario list + run APIs, simulation lifecycle logging, dashboard Simulation Scenarios UI.
- Prompt 10 — Demo role-based access control (`greenhouse_manager`, `farm_owner`, `system_administrator`) via `X-User-Role` header, backend-enforced `permission_required` decorator (401 missing/invalid, 403 forbidden, denial logging), threshold/sensor PUTs read role from header (no body spoof), admin-only `GET /api/logs`, dashboard role selector + role-gated sections + System Logs UI.

## Run & Operate

- The app runs via the `Start application` workflow: `python app.py`
- Binds to `0.0.0.0:5000` (or `$PORT`)
- Manual run: `python app.py`

## Stack

- Python 3.11 + Flask (REST API + server-rendered dashboard)
- HTML / CSS / vanilla JavaScript frontend
- JSON file storage under `/data` — no database (per MVP requirement)

## APIs

- `GET /` — renders the dashboard (`templates/index.html`)
- `GET /api/health` — `{ "status": "ok", "message": "..." }`
- `GET /api/sensors` — returns the four virtual sensors from `data/sensors.json` (full config + `communication_status`)
- `GET /api/sensors/status` — sensors with derived `communication_status` (active/inactive/no_data) plus `current_reading`
- `PUT /api/sensors/<sensor_id>` — update one sensor's config (demo admin mode: body must include `role: "system_administrator"`). Only `sensor_name`, `unit`, `status` are editable; `sensor_id`/`sensor_type` are immutable and `unit` must match the type. 403 if not admin; 404 if sensor missing; 400 "Invalid sensor update" with `errors[]`; success returns the updated `sensor`. Bumps `updated_at`
- `POST /api/sensors/check-activity` — recompute + persist each sensor's `communication_status` on demand; returns the updated statuses. Logs inactive transitions and no-data sensors
- `POST /api/sensors/<sensor_id>/reading` — validate → rule-engine evaluate → store; sets `reading_status` to `normal`/`warning`/`critical`. A valid reading also refreshes the sensor's `last_valid_reading_at` and `communication_status` (does not bump `updated_at`)
- `GET /api/readings/latest` — latest reading per sensor, including `reading_status`, `threshold_min`, `threshold_max`
- `GET /api/sensors/<sensor_id>/readings` — reading history (newest first) with `reading_status`
- `GET /api/thresholds` — all threshold rules
- `GET /api/thresholds/<sensor_type>` — one threshold rule (404 if missing)
- `PUT /api/thresholds/<sensor_type>` — update one rule (demo admin mode: body must include `role: "system_administrator"`, plus numeric `min_value`, `max_value`, `warning_margin`). 403 if not admin; 400 "Unsupported sensor type"; 400 "Invalid threshold update" with `errors[]`; success returns the updated `threshold`. Only the matched rule changes; applies to future readings only
- The reading POST also returns `alert` (the generated alert for warning/critical, else `null`) and `automation_action` (the action for critical-triggered automation, else `null`). Messages: normal "Sensor reading saved successfully"; warning "Sensor reading saved and warning alert generated"; critical with automation "Sensor reading saved, critical alert generated, and automation response triggered"; critical without automation "Sensor reading saved and critical alert generated"
- `GET /api/alerts/active` — active alerts, critical-first then newest-first
- `GET /api/alerts/history` — all alerts (active + resolved), newest-first
- `GET /api/sensors/<sensor_id>/alerts` — alerts for one sensor (404 if sensor missing)
- `PATCH /api/alerts/<alert_id>/resolve` — resolve an active alert (404 if missing; safe no-op if already resolved)
- `GET /api/actuators` — the four virtual actuators from `data/actuators.json` with current status
- `GET /api/automation/actions` — all automation actions (history), newest-first
- `GET /api/automation/active` — currently active automation actions
- `PATCH /api/actuators/<actuator_id>/reset` — reset an actuator to inactive (404 if missing; safe no-op if already inactive)
- `GET /api/analytics/summary` — full read-only analytics payload: `average_values`, `alert_counts_by_sensor_type`, `most_frequent_abnormal_condition`, `recent_trends`, `greenhouse_health_status`, `greenhouse_health_score`. Logs `analytics_summary_generated`; safe 500 on failure
- `GET /api/analytics/health` — greenhouse `health_status` + `explanation` + `score` + `interpretation`, all from one state snapshot. Logs `health_score_calculated`; safe 500 on failure
- `GET /api/analytics/trends` — `recent_trends` per sensor type (`increasing`/`decreasing`/`stable`/`insufficient_data` with `sample_size`). Safe 500 on failure
- `GET /api/simulation/scenarios` — list predefined simulation scenarios (public fields only: `scenario_id`, `name`, `description`, `expected_result`, `sensor_id`, `sensor_type`, `unit`). Safe 500 on failure
- `GET /api/logs` — system log (admin only, action `view_system_logs`). Returns `{ "success": true, "logs": [...] }`, newest-first. 401 if role missing/invalid; 403 if not authorized
- `POST /api/simulation/run/<scenario_id>` — run one predefined scenario. The backend generates the reading value relative to the CURRENT threshold (`above_max` → max+offset, `below_min` → min−offset) and processes it through the shared ingestion pipeline (validate → rule engine → storage → alerts → automation). Returns `generated_readings`, `alerts`, `automation_actions`, `scenario_name`, `expected_result`. Unknown id → safe 404 (`unknown_simulation_scenario` logged). Logs `simulation_scenario_started`/`completed`; failures log `simulation_scenario_failed` and return a generic 500

## Where things live

- `app.py` — Flask app + routes
- `templates/index.html`, `static/css/style.css`, `static/js/dashboard.js` — dashboard
- `data/*.json` — JSON storage (sensors, readings, alerts, actuators, automation_actions, system_logs, threshold_rules, simulation_scenarios, users)
- `services/*.py` — business logic. `storage_service.py`, `sensor_service.py`, `validation_service.py`, `log_service.py`, `rule_engine.py`, `alert_service.py`, `automation_service.py`, `threshold_service.py`, `analytics_service.py`, `reading_pipeline.py`, and `simulation_service.py` are all implemented. `analytics_service.py` is read-only (derives insights without mutating state). `reading_pipeline.py` holds the shared reading-ingestion flow (`process_reading`) used by both the reading POST and the simulation runner. `simulation_service.py` is pure orchestration (no logging, no HTTP).
- `models/*.py` — record shape definitions + `make_*` helpers (no ORM)

## Architecture decisions

- All file IO is centralized in `services/storage_service.py` so JSON can later be swapped for a database without touching other modules.
- `init_storage()` runs at startup to create any missing data file with a safe default, so reads never crash on a missing file.
- Each service file documents which future PRD area it will support (see module docstrings).
- The Node `api-server` scaffold artifact was repointed off `/api` (to `/__scaffold-api`) so the Flask app owns `/api/*` through the preview proxy. It is not part of this product.

## Security notes

- No passwords/credentials are stored (`users.json` is metadata only).
- Storage helpers verify files exist before reading and fall back to safe defaults.
- API errors return generic messages without leaking internal details.
- Access control is enforced server-side (the `permission_required` decorator), never trusting the client. The role comes from the `X-User-Role` header, not the request body, so a spoofed body role cannot escalate privileges. This is demo-level RBAC only (no authentication/identity verification); real auth, sessions, and credentials remain out of scope.
- Every authorization denial (missing/invalid role and forbidden action) is logged with role, attempted action, and endpoint for auditing.

## User preferences

- This is a multi-prompt academic MVP. Do NOT implement features ahead of the current prompt's scope. Keep modules separate — do not remove or merge them. No database until explicitly requested.
