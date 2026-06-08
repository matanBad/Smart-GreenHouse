// dashboard.js
// Prompt 3: render the latest reading per sensor with its rule-engine status
// (normal / warning / critical) and allowed threshold range, refresh on demand,
// and offer demo buttons that submit valid sample readings across the range so
// every status is easy to see.

// Build URLs relative to where the page is served so it works behind a proxy.
const API_BASE = window.location.pathname.replace(/\/+$/, "");

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

// ---- Role-based access (Prompt 10) ----------------------------------------
// The dashboard declares the active role with the X-User-Role header on every
// request. The backend is the source of truth for permissions; the UI simply
// hides sections the role may not use and avoids calling endpoints it cannot
// access. Switching role here is purely a demo convenience.
const VALID_ROLES = [
  "greenhouse_manager",
  "farm_owner",
  "system_administrator",
];
const ROLE_STORAGE_KEY = "greenhouse_active_role";

function loadStoredRole() {
  try {
    const stored = localStorage.getItem(ROLE_STORAGE_KEY);
    if (stored && VALID_ROLES.includes(stored)) return stored;
  } catch (err) {
    /* localStorage may be unavailable; fall back to the default role. */
  }
  return "greenhouse_manager";
}

let currentRole = loadStoredRole();

function setCurrentRole(role) {
  currentRole = VALID_ROLES.includes(role) ? role : "greenhouse_manager";
  try {
    localStorage.setItem(ROLE_STORAGE_KEY, currentRole);
  } catch (err) {
    /* Persisting the role is best-effort only. */
  }
}

// Every API request goes through here so the active role header is always sent.
function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {}, {
    "X-User-Role": currentRole,
  });
  return fetch(url, Object.assign({}, options, { headers }));
}

// Sample value ranges used only by the demo buttons. These deliberately span a
// little beyond the threshold rules so demo readings exercise all three
// statuses (normal / warning / critical). They are still valid readings — only
// their value varies; the server computes the status.
const DEMO_SENSORS = {
  "TEMP-001": { type: "temperature", unit: "C", min: 14, max: 34 },
  "HUM-001": { type: "humidity", unit: "%", min: 34, max: 76 },
  "SOIL-001": { type: "soil_moisture", unit: "%", min: 24, max: 66 },
  "LIGHT-001": { type: "light_intensity", unit: "lux", min: 1200, max: 11000 },
};

function randomInRange(min, max) {
  return Math.round((min + Math.random() * (max - min)) * 10) / 10;
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

async function checkHealth() {
  const pill = document.getElementById("health-pill");
  try {
    const res = await apiFetch(apiUrl("/api/health"));
    const data = await res.json();
    if (data.status === "ok") {
      pill.textContent = "System Online";
      pill.classList.remove("error");
      pill.classList.add("ok");
    } else {
      throw new Error("unhealthy");
    }
  } catch (err) {
    pill.textContent = "System Offline";
    pill.classList.remove("ok");
    pill.classList.add("error");
  }
}

function renderSensors(entries) {
  const grid = document.getElementById("sensor-grid");
  grid.innerHTML = "";

  if (!Array.isArray(entries) || entries.length === 0) {
    grid.innerHTML = '<p class="placeholder">No sensors configured.</p>';
    return;
  }

  entries.forEach((entry) => {
    const reading = entry.latest_reading;
    const hasReading = entry.has_reading && reading;
    const status = hasReading ? reading.reading_status : null;

    const valueBlock = hasReading
      ? `<span class="value">${reading.value}</span>
         <span class="unit">${entry.unit ?? ""}</span>`
      : `<span class="no-reading">No reading received yet</span>`;

    const lastUpdate = hasReading
      ? formatTime(reading.timestamp || reading.created_at)
      : "—";

    const statusBlock = hasReading
      ? `<span class="status-badge ${status}">${status}</span>`
      : `<span class="status-badge none">no status</span>`;

    const range =
      entry.threshold_min !== null &&
      entry.threshold_min !== undefined &&
      entry.threshold_max !== null &&
      entry.threshold_max !== undefined
        ? `Allowed range: ${entry.threshold_min}–${entry.threshold_max} ${entry.unit ?? ""}`
        : "Allowed range: —";

    const availability = hasReading
      ? `<span class="status-dot ok">reading available</span>`
      : `<span class="status-dot idle">awaiting reading</span>`;

    const card = document.createElement("article");
    // Status drives the card highlight (normal / warning / critical).
    card.className = `sensor-card${status ? ` is-${status}` : ""}`;
    card.innerHTML = `
      <div class="sensor-card-head">
        <div class="sensor-type">${entry.sensor_type ?? "sensor"}</div>
        ${statusBlock}
      </div>
      <div class="sensor-name">${entry.name ?? entry.sensor_id}</div>
      <div class="sensor-meta">${entry.location ?? ""}</div>
      <div class="sensor-reading">${valueBlock}</div>
      <div class="sensor-range">${range}</div>
      <div class="sensor-update">Last update: ${lastUpdate}</div>
      <div class="sensor-footer">
        <span class="sensor-id">${entry.sensor_id ?? ""}</span>
        ${availability}
      </div>
    `;
    grid.appendChild(card);
  });
}

function escapeHtml(str) {
  return String(str ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
}

function renderAlerts(alerts) {
  const list = document.getElementById("alerts-list");
  list.innerHTML = "";

  if (!Array.isArray(alerts) || alerts.length === 0) {
    list.innerHTML = '<p class="placeholder">No active alerts</p>';
    return;
  }

  alerts.forEach((alert) => {
    const severity = alert.severity === "critical" ? "critical" : "warning";
    const range =
      alert.min_threshold !== null && alert.max_threshold !== null
        ? `${alert.min_threshold}–${alert.max_threshold} ${alert.unit ?? ""}`
        : "—";

    const card = document.createElement("article");
    card.className = `alert-card is-${severity}`;
    card.innerHTML = `
      <div class="alert-head">
        <div>
          <span class="alert-sensor">${escapeHtml(alert.sensor_name ?? alert.sensor_id)}</span>
          <span class="alert-type">${escapeHtml(alert.alert_type ?? "")}</span>
        </div>
        <span class="status-badge ${severity}">${severity}</span>
      </div>
      <div class="alert-measured">
        <span class="value">${escapeHtml(alert.measured_value)}</span>
        <span class="unit">${escapeHtml(alert.unit ?? "")}</span>
        <span class="alert-range">Allowed range: ${escapeHtml(range)}</span>
      </div>
      <p class="alert-message">${escapeHtml(alert.message ?? "")}</p>
      <p class="alert-action"><strong>Recommended:</strong> ${escapeHtml(alert.recommended_action ?? "")}</p>
      <div class="alert-foot">
        <span class="alert-time">${formatTime(alert.created_at)}</span>
        <button class="btn btn-resolve" data-alert="${escapeHtml(alert.alert_id)}">
          Resolve
        </button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".btn-resolve").forEach((btn) => {
    btn.addEventListener("click", () => resolveAlert(btn.dataset.alert));
  });
}

async function loadAlerts() {
  const list = document.getElementById("alerts-list");
  try {
    const res = await apiFetch(apiUrl("/api/alerts/active"));
    if (!res.ok) throw new Error("Failed to load alerts");
    renderAlerts(await res.json());
  } catch (err) {
    list.innerHTML =
      '<p class="placeholder">Unable to load alerts right now.</p>';
  }
}

async function resolveAlert(alertId) {
  if (!alertId) return;
  try {
    await apiFetch(apiUrl(`/api/alerts/${alertId}/resolve`), { method: "PATCH" });
  } catch (err) {
    console.warn("Failed to resolve alert:", err);
  }
  await loadAlerts();
}

function renderActuators(actuators) {
  const list = document.getElementById("actuators-list");
  list.innerHTML = "";

  if (!Array.isArray(actuators) || actuators.length === 0) {
    list.innerHTML = '<p class="placeholder">No actuators configured.</p>';
    return;
  }

  actuators.forEach((act) => {
    const isActive = act.status === "active";
    const card = document.createElement("article");
    card.className = `actuator-card is-${isActive ? "active" : "inactive"}`;
    card.innerHTML = `
      <div class="actuator-head">
        <div>
          <span class="actuator-name">${escapeHtml(act.actuator_name ?? act.actuator_id)}</span>
          <span class="actuator-type">${escapeHtml(act.actuator_type ?? "")}</span>
        </div>
        <span class="status-badge ${isActive ? "critical" : "normal"}">${escapeHtml(act.status ?? "")}</span>
      </div>
      <dl class="actuator-meta">
        <div><dt>Last activated</dt><dd>${formatTime(act.last_activation_time)}</dd></div>
        <div><dt>Last reason</dt><dd>${escapeHtml(act.last_trigger_reason ?? "—")}</dd></div>
      </dl>
      <div class="actuator-foot">
        <button class="btn btn-ghost btn-reset" data-actuator="${escapeHtml(act.actuator_id)}" ${isActive ? "" : "disabled"}>
          Reset
        </button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".btn-reset").forEach((btn) => {
    btn.addEventListener("click", () => resetActuator(btn.dataset.actuator));
  });
}

async function loadActuators() {
  const list = document.getElementById("actuators-list");
  try {
    const res = await apiFetch(apiUrl("/api/actuators"));
    if (!res.ok) throw new Error("Failed to load actuators");
    renderActuators(await res.json());
  } catch (err) {
    list.innerHTML =
      '<p class="placeholder">Unable to load actuators right now.</p>';
  }
}

function renderAutomationHistory(actions) {
  const wrap = document.getElementById("automation-history");
  wrap.innerHTML = "";

  if (!Array.isArray(actions) || actions.length === 0) {
    wrap.innerHTML = '<p class="placeholder">No automation actions yet</p>';
    return;
  }

  const rows = actions
    .map(
      (a) => `
      <tr>
        <td>${escapeHtml(a.actuator_name ?? a.actuator_id)}</td>
        <td><code>${escapeHtml(a.action_type ?? "")}</code></td>
        <td>${escapeHtml(a.trigger_reason ?? "—")}</td>
        <td>${formatTime(a.triggered_at)}</td>
      </tr>`,
    )
    .join("");

  wrap.innerHTML = `
    <table class="history-table">
      <thead>
        <tr><th>Actuator</th><th>Action</th><th>Trigger reason</th><th>Triggered at</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadAutomationHistory() {
  const wrap = document.getElementById("automation-history");
  try {
    const res = await apiFetch(apiUrl("/api/automation/actions"));
    if (!res.ok) throw new Error("Failed to load automation history");
    renderAutomationHistory(await res.json());
  } catch (err) {
    wrap.innerHTML =
      '<p class="placeholder">Unable to load automation history right now.</p>';
  }
}

function loadAutomation() {
  return Promise.all([loadActuators(), loadAutomationHistory()]);
}

async function resetActuator(actuatorId) {
  if (!actuatorId) return;
  try {
    await apiFetch(apiUrl(`/api/actuators/${actuatorId}/reset`), {
      method: "PATCH",
    });
  } catch (err) {
    console.warn("Failed to reset actuator:", err);
  }
  loadAutomation();
}

function renderThresholds(rules) {
  const list = document.getElementById("thresholds-list");
  list.innerHTML = "";

  if (!Array.isArray(rules) || rules.length === 0) {
    list.innerHTML = '<p class="placeholder">No threshold rules configured.</p>';
    return;
  }

  rules.forEach((rule) => {
    const type = rule.sensor_type ?? "";
    const card = document.createElement("article");
    card.className = "threshold-card";
    card.innerHTML = `
      <div class="threshold-head">
        <span class="threshold-type">${escapeHtml(type)}</span>
        <span class="threshold-unit">${escapeHtml(rule.unit ?? "")}</span>
      </div>
      <div class="threshold-fields">
        <label>
          <span>Min</span>
          <input type="number" step="any" class="th-min" value="${escapeHtml(String(rule.min_value ?? ""))}" />
        </label>
        <label>
          <span>Max</span>
          <input type="number" step="any" class="th-max" value="${escapeHtml(String(rule.max_value ?? ""))}" />
        </label>
        <label>
          <span>Warning margin</span>
          <input type="number" step="any" min="0" class="th-margin" value="${escapeHtml(String(rule.warning_margin ?? ""))}" />
        </label>
      </div>
      <div class="threshold-foot">
        <span class="threshold-msg" role="status"></span>
        <button class="btn btn-primary btn-update" data-type="${escapeHtml(type)}">Update</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".btn-update").forEach((btn) => {
    btn.addEventListener("click", () => updateThreshold(btn));
  });
}

async function loadThresholds() {
  const list = document.getElementById("thresholds-list");
  try {
    const res = await apiFetch(apiUrl("/api/thresholds"));
    if (!res.ok) throw new Error("Failed to load thresholds");
    renderThresholds(await res.json());
  } catch (err) {
    list.innerHTML =
      '<p class="placeholder">Unable to load threshold rules right now.</p>';
  }
}

async function updateThreshold(btn) {
  const sensorType = btn.dataset.type;
  const card = btn.closest(".threshold-card");
  const msg = card.querySelector(".threshold-msg");
  const minValue = Number(card.querySelector(".th-min").value);
  const maxValue = Number(card.querySelector(".th-max").value);
  const warningMargin = Number(card.querySelector(".th-margin").value);

  msg.className = "threshold-msg";
  msg.textContent = "Saving…";
  btn.disabled = true;

  try {
    const res = await apiFetch(apiUrl(`/api/thresholds/${sensorType}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        min_value: minValue,
        max_value: maxValue,
        warning_margin: warningMargin,
      }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      msg.classList.add("is-ok");
      msg.textContent = "Saved";
    } else {
      msg.classList.add("is-error");
      const errors = Array.isArray(data.errors) ? `: ${data.errors.join(", ")}` : "";
      msg.textContent = `${data.message ?? "Update failed"}${errors}`;
    }
  } catch (err) {
    msg.classList.add("is-error");
    msg.textContent = "Update failed. Please try again.";
  } finally {
    btn.disabled = false;
  }
}

async function loadLatest() {
  const grid = document.getElementById("sensor-grid");
  try {
    const res = await apiFetch(apiUrl("/api/readings/latest"));
    if (!res.ok) throw new Error("Failed to load readings");
    const entries = await res.json();
    renderSensors(entries);
  } catch (err) {
    grid.innerHTML =
      '<p class="placeholder">Unable to load sensor data right now.</p>';
  }
}

// ---- Sensor management (Prompt 7) ----------------------------------------

function commStatusLabel(status) {
  if (status === "active") return "active";
  if (status === "inactive") return "inactive";
  return "no data";
}

function renderSensorStatuses(sensors) {
  const list = document.getElementById("sensor-status-list");
  list.innerHTML = "";

  if (!Array.isArray(sensors) || sensors.length === 0) {
    list.innerHTML = '<p class="placeholder">No sensors configured.</p>';
    return;
  }

  sensors.forEach((sensor) => {
    const comm = sensor.communication_status ?? "no_data";
    const card = document.createElement("article");
    card.className = "sensor-status-card";
    card.dataset.sensorId = sensor.sensor_id ?? "";
    card.innerHTML = `
      <div class="sensor-status-head">
        <span class="sensor-status-type">${escapeHtml(sensor.sensor_type ?? "")}</span>
        <span class="comm-badge is-${escapeHtml(comm)}">${escapeHtml(commStatusLabel(comm))}</span>
      </div>
      <div class="sensor-status-grid">
        <label>
          <span>Sensor name</span>
          <input type="text" class="sm-name" value="${escapeHtml(sensor.sensor_name ?? "")}" />
        </label>
        <label>
          <span>Status</span>
          <select class="sm-status">
            <option value="enabled"${sensor.status === "enabled" ? " selected" : ""}>enabled</option>
            <option value="disabled"${sensor.status === "disabled" ? " selected" : ""}>disabled</option>
          </select>
        </label>
      </div>
      <dl class="sensor-status-meta">
        <div><dt>Sensor ID</dt><dd>${escapeHtml(sensor.sensor_id ?? "")}</dd></div>
        <div><dt>Unit</dt><dd>${escapeHtml(sensor.unit ?? "")}</dd></div>
        <div><dt>Expected frequency</dt><dd>${escapeHtml(String(sensor.expected_frequency_seconds ?? "—"))} s</dd></div>
        <div><dt>Last valid reading</dt><dd>${formatTime(sensor.last_valid_reading_at)}</dd></div>
      </dl>
      <div class="sensor-status-foot">
        <span class="sensor-status-msg" role="status"></span>
        <button class="btn btn-primary sm-save">Save</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".sm-save").forEach((btn) => {
    btn.addEventListener("click", () => updateSensorConfig(btn));
  });
}

async function loadSensorStatuses() {
  const list = document.getElementById("sensor-status-list");
  try {
    const res = await apiFetch(apiUrl("/api/sensors/status"));
    if (!res.ok) throw new Error("Failed to load sensor status");
    renderSensorStatuses(await res.json());
  } catch (err) {
    list.innerHTML =
      '<p class="placeholder">Unable to load sensor status right now.</p>';
  }
}

async function checkSensorActivity() {
  const btn = document.getElementById("check-activity-btn");
  btn.disabled = true;
  try {
    const res = await apiFetch(apiUrl("/api/sensors/check-activity"), {
      method: "POST",
    });
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.sensors)) {
        renderSensorStatuses(data.sensors);
        return;
      }
    }
    await loadSensorStatuses();
  } catch (err) {
    await loadSensorStatuses();
  } finally {
    btn.disabled = false;
  }
}

async function updateSensorConfig(btn) {
  const card = btn.closest(".sensor-status-card");
  const sensorId = card.dataset.sensorId;
  const msg = card.querySelector(".sensor-status-msg");
  const sensorName = card.querySelector(".sm-name").value;
  const status = card.querySelector(".sm-status").value;

  msg.className = "sensor-status-msg";
  msg.textContent = "Saving…";
  btn.disabled = true;

  try {
    const res = await apiFetch(apiUrl(`/api/sensors/${sensorId}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sensor_name: sensorName,
        status: status,
      }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      msg.classList.add("is-ok");
      msg.textContent = "Saved";
      loadLatest();
    } else {
      msg.classList.add("is-error");
      const errors = Array.isArray(data.errors) ? `: ${data.errors.join(", ")}` : "";
      msg.textContent = `${data.message ?? "Update failed"}${errors}`;
    }
  } catch (err) {
    msg.classList.add("is-error");
    msg.textContent = "Update failed. Please try again.";
  } finally {
    btn.disabled = false;
  }
}

async function sendDemoReading(sensorId) {
  const cfg = DEMO_SENSORS[sensorId];
  if (!cfg) return;

  const payload = {
    sensor_id: sensorId,
    sensor_type: cfg.type,
    value: randomInRange(cfg.min, cfg.max),
    unit: cfg.unit,
    timestamp: new Date().toISOString(),
  };

  try {
    const res = await apiFetch(apiUrl(`/api/sensors/${sensorId}/reading`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    // Refresh either way so the user sees the current state.
    await loadLatest();
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      console.warn("Reading rejected:", data);
    }
  } catch (err) {
    console.warn("Failed to send demo reading:", err);
  }
}

const SENSOR_TYPE_LABELS = {
  temperature: "Temperature",
  humidity: "Humidity",
  soil_moisture: "Soil moisture",
  light_intensity: "Light intensity",
};

function healthStatusLabel(status) {
  if (status === "healthy") return "Healthy";
  if (status === "needs_attention") return "Needs attention";
  if (status === "critical") return "Critical";
  return status || "Unknown";
}

function trendLabel(trend) {
  if (trend === "increasing") return "▲ Increasing";
  if (trend === "decreasing") return "▼ Decreasing";
  if (trend === "stable") return "→ Stable";
  return "– Insufficient data";
}

function prettyAlertType(alertType) {
  if (!alertType) return "None";
  return alertType.replace(/_/g, " ");
}

function renderOwnerSummary(analytics) {
  const el = document.getElementById("owner-summary");
  if (!el) return;
  const status = analytics.greenhouse_health_status || {};
  const score = analytics.greenhouse_health_score || {};
  const abnormal = analytics.most_frequent_abnormal_condition || {};
  const healthClass = `is-${status.health_status || "unknown"}`;
  const scoreClass = `is-${score.interpretation || "unknown"}`;

  el.innerHTML = `
    <div class="owner-card ${healthClass}">
      <span class="owner-label">Health status</span>
      <span class="owner-value">${escapeHtml(healthStatusLabel(status.health_status))}</span>
      <p class="owner-note">${escapeHtml(status.explanation || "")}</p>
    </div>
    <div class="owner-card ${scoreClass}">
      <span class="owner-label">Health score</span>
      <span class="owner-value">${score.score ?? "--"}<small>/100</small></span>
      <p class="owner-note">Condition: ${escapeHtml(score.interpretation || "unknown")}</p>
    </div>
    <div class="owner-card">
      <span class="owner-label">Most frequent issue</span>
      <span class="owner-value owner-value-sm">${escapeHtml(prettyAlertType(abnormal.alert_type))}</span>
      <p class="owner-note">${
        abnormal.alert_type
          ? `Seen ${abnormal.count} time(s)`
          : escapeHtml(abnormal.message || "No abnormal conditions detected yet")
      }</p>
    </div>`;
}

function renderAnalytics(analytics) {
  const el = document.getElementById("analytics-body");
  if (!el) return;

  const averages = analytics.average_values || {};
  const counts = analytics.alert_counts_by_sensor_type || {};
  const trends = analytics.recent_trends || {};
  const score = analytics.greenhouse_health_score || {};

  const types = Object.keys(SENSOR_TYPE_LABELS);

  const avgRows = types
    .map((t) => {
      const a = averages[t] || {};
      const value = a.average === null || a.average === undefined ? "—" : a.average;
      const note = a.average === null || a.average === undefined ? a.message || "No data" : `${a.count} reading(s)`;
      return `<tr><td>${SENSOR_TYPE_LABELS[t]}</td><td>${value}</td><td class="muted">${escapeHtml(note)}</td></tr>`;
    })
    .join("");

  const alertRows = types
    .map((t) => {
      const c = counts[t] || { total: 0, active: 0 };
      return `<tr><td>${SENSOR_TYPE_LABELS[t]}</td><td>${c.total}</td><td>${c.active}</td></tr>`;
    })
    .join("");

  const trendRows = types
    .map((t) => {
      const tr = trends[t] || {};
      return `<tr><td>${SENSOR_TYPE_LABELS[t]}</td><td class="trend-${tr.trend}">${trendLabel(tr.trend)}</td><td class="muted">${tr.sample_size ?? 0} sample(s)</td></tr>`;
    })
    .join("");

  el.innerHTML = `
    <div class="analytics-grid">
      <div class="analytics-card">
        <h3 class="analytics-card-title">Average values</h3>
        <table class="analytics-table">
          <thead><tr><th>Sensor</th><th>Average</th><th>Samples</th></tr></thead>
          <tbody>${avgRows}</tbody>
        </table>
      </div>
      <div class="analytics-card">
        <h3 class="analytics-card-title">Alerts by sensor type</h3>
        <table class="analytics-table">
          <thead><tr><th>Sensor</th><th>Total</th><th>Active</th></tr></thead>
          <tbody>${alertRows}</tbody>
        </table>
      </div>
      <div class="analytics-card">
        <h3 class="analytics-card-title">Recent trends</h3>
        <table class="analytics-table">
          <thead><tr><th>Sensor</th><th>Trend</th><th>Window</th></tr></thead>
          <tbody>${trendRows}</tbody>
        </table>
      </div>
      <div class="analytics-card analytics-score is-${score.interpretation || "unknown"}">
        <h3 class="analytics-card-title">Greenhouse Health Score</h3>
        <div class="score-big">${score.score ?? "--"}<small>/100</small></div>
        <div class="score-interp">${escapeHtml(score.interpretation || "unknown")}</div>
      </div>
    </div>`;
}

async function loadAnalytics() {
  const body = document.getElementById("analytics-body");
  try {
    const res = await apiFetch(apiUrl("/api/analytics/summary"));
    if (!res.ok) throw new Error("Failed to load analytics");
    const data = await res.json();
    const analytics = data.analytics || {};
    renderAnalytics(analytics);
    renderOwnerSummary(analytics);
  } catch (err) {
    if (body) {
      body.innerHTML = '<p class="placeholder">Unable to load analytics right now.</p>';
    }
    const owner = document.getElementById("owner-summary");
    if (owner) {
      owner.innerHTML = '<p class="placeholder">Unable to load summary right now.</p>';
    }
  }
}

function renderScenarios(scenarios) {
  const list = document.getElementById("scenario-list");
  if (!list) return;
  list.innerHTML = "";

  if (!Array.isArray(scenarios) || scenarios.length === 0) {
    list.innerHTML = '<p class="placeholder">No scenarios available</p>';
    return;
  }

  list.innerHTML = scenarios
    .map(
      (s) => `
      <div class="scenario-card">
        <div class="scenario-card-head">
          <h3 class="scenario-name">${escapeHtml(s.name ?? s.scenario_id)}</h3>
          <span class="scenario-sensor">${escapeHtml(s.sensor_id ?? "")}</span>
        </div>
        <p class="scenario-desc">${escapeHtml(s.description ?? "")}</p>
        <p class="scenario-expected">Expected: ${escapeHtml(s.expected_result ?? "")}</p>
        <button class="btn" data-scenario="${escapeHtml(s.scenario_id)}">Run scenario</button>
      </div>`,
    )
    .join("");

  list.querySelectorAll("[data-scenario]").forEach((btn) => {
    btn.addEventListener("click", () => runScenario(btn));
  });
}

async function loadScenarios() {
  const list = document.getElementById("scenario-list");
  if (!list) return;
  try {
    const res = await apiFetch(apiUrl("/api/simulation/scenarios"));
    if (!res.ok) throw new Error("Failed to load scenarios");
    const data = await res.json();
    renderScenarios(data.scenarios || []);
  } catch (err) {
    list.innerHTML =
      '<p class="placeholder">Unable to load scenarios right now.</p>';
  }
}

function renderScenarioResult(result) {
  const el = document.getElementById("scenario-result");
  if (!el) return;

  const readings = result.generated_readings || [];
  const alerts = result.alerts || [];
  const actions = result.automation_actions || [];

  const readingRows = readings
    .map(
      (r) => `
      <li>
        <code>${escapeHtml(r.sensor_id ?? "")}</code>
        value <strong>${escapeHtml(String(r.value))}</strong> ${escapeHtml(r.unit ?? "")}
        → <span class="status-${escapeHtml(r.reading_status ?? "")}">${escapeHtml(r.reading_status ?? "")}</span>
      </li>`,
    )
    .join("");

  const alertText = alerts.length
    ? alerts
        .map(
          (a) =>
            `${escapeHtml(prettyAlertType(a.alert_type))} (${escapeHtml(a.severity ?? "")})`,
        )
        .join(", ")
    : "None";

  const actionText = actions.length
    ? actions.map((a) => escapeHtml(a.action_type ?? "")).join(", ")
    : "None";

  el.innerHTML = `
    <div class="scenario-result-card">
      <p class="scenario-result-title">
        ${escapeHtml(result.scenario_name ?? result.scenario_id)} — completed
      </p>
      <ul class="scenario-result-readings">${readingRows}</ul>
      <p><span class="scenario-result-label">Alerts:</span> ${alertText}</p>
      <p><span class="scenario-result-label">Automation:</span> ${actionText}</p>
    </div>
  `;
}

async function runScenario(btn) {
  const scenarioId = btn.dataset.scenario;
  if (!scenarioId) return;
  const result = document.getElementById("scenario-result");
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Running…";
  try {
    const res = await apiFetch(apiUrl(`/api/simulation/run/${scenarioId}`), {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.message || "Scenario failed");
    }
    renderScenarioResult(data);
    // The scenario fed real readings through the pipeline, so refresh
    // everything it could have changed.
    loadLatest();
    loadSensorStatuses();
    loadAlerts();
    loadAutomation();
    loadAnalytics();
  } catch (err) {
    if (result) {
      result.innerHTML =
        '<p class="placeholder">Unable to run scenario right now.</p>';
    }
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// Give a refresh button visible feedback while its work runs, so a refresh that
// produces no on-screen change (e.g. automation status when everything is
// already inactive) still clearly registers as having happened.
async function withButtonFeedback(btn, work) {
  if (!btn) {
    await work();
    return;
  }
  if (btn._restoreTimer) {
    clearTimeout(btn._restoreTimer);
    btn._restoreTimer = null;
  }
  const originalText = btn.dataset.label ?? btn.textContent;
  btn.dataset.label = originalText;
  btn.disabled = true;
  btn.textContent = "Refreshing…";
  try {
    await work();
    btn.textContent = "Updated";
  } catch (err) {
    btn.textContent = originalText;
  } finally {
    btn.disabled = false;
    btn._restoreTimer = setTimeout(() => {
      btn.textContent = originalText;
      btn._restoreTimer = null;
    }, 1200);
  }
}

// ---- System logs (Prompt 10, System Administrator) ------------------------

const LOG_EVENT_LABELS = {
  unauthorized_access_attempt: "Unauthorized access",
  invalid_role_attempt: "Invalid role",
};

function renderLogs(logs) {
  const el = document.getElementById("logs-body");
  if (!el) return;

  if (!Array.isArray(logs) || logs.length === 0) {
    el.innerHTML = '<p class="placeholder">No system logs yet</p>';
    return;
  }

  const rows = logs
    .map((log) => {
      const event = log.event_type ?? "";
      const label = LOG_EVENT_LABELS[event] || event.replace(/_/g, " ");
      return `
      <tr>
        <td>${formatTime(log.created_at)}</td>
        <td><code>${escapeHtml(event)}</code></td>
        <td>${escapeHtml(label)}</td>
        <td>${escapeHtml(log.description ?? "")}</td>
      </tr>`;
    })
    .join("");

  el.innerHTML = `
    <table class="history-table logs-table">
      <thead>
        <tr><th>Time</th><th>Event type</th><th>Category</th><th>Description</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function loadLogs() {
  const el = document.getElementById("logs-body");
  if (!el) return;
  try {
    const res = await apiFetch(apiUrl("/api/logs"));
    if (!res.ok) throw new Error("Failed to load logs");
    const data = await res.json();
    renderLogs(data.logs || []);
  } catch (err) {
    el.innerHTML = '<p class="placeholder">Unable to load system logs right now.</p>';
  }
}

// ---- Role-aware visibility & loading --------------------------------------

// Show only the sections the active role is allowed to use. Any element with a
// data-roles attribute lists the roles permitted to see it.
function applyRoleVisibility() {
  document.querySelectorAll("[data-roles]").forEach((el) => {
    const roles = el.dataset.roles.split(/\s+/).filter(Boolean);
    el.hidden = !roles.includes(currentRole);
  });
}

// Load only the data the active role may access, so the dashboard never fires
// requests the backend would reject.
function loadForRole() {
  checkHealth();
  if (currentRole === "greenhouse_manager") {
    loadLatest();
    loadAlerts();
    loadAutomation();
    loadScenarios();
  } else if (currentRole === "farm_owner") {
    loadAnalytics();
  } else if (currentRole === "system_administrator") {
    loadLatest();
    loadSensorStatuses();
    loadAutomation();
    loadThresholds();
    loadLogs();
  }
}

function wireControls() {
  const roleSelect = document.getElementById("role-select");
  if (roleSelect) {
    roleSelect.value = currentRole;
    roleSelect.addEventListener("change", () => {
      setCurrentRole(roleSelect.value);
      applyRoleVisibility();
      loadForRole();
    });
  }

  const refreshBtn = document.getElementById("refresh-btn");
  refreshBtn.addEventListener("click", () => {
    withButtonFeedback(refreshBtn, async () => loadForRole());
  });

  const refreshLogsBtn = document.getElementById("refresh-logs-btn");
  if (refreshLogsBtn) {
    refreshLogsBtn.addEventListener("click", () =>
      withButtonFeedback(refreshLogsBtn, () => loadLogs()),
    );
  }

  const refreshAnalyticsBtn = document.getElementById("refresh-analytics-btn");
  if (refreshAnalyticsBtn) {
    refreshAnalyticsBtn.addEventListener("click", () =>
      withButtonFeedback(refreshAnalyticsBtn, () => loadAnalytics()),
    );
  }

  const refreshAlertsBtn = document.getElementById("refresh-alerts-btn");
  refreshAlertsBtn.addEventListener("click", () =>
    withButtonFeedback(refreshAlertsBtn, () => loadAlerts()),
  );

  const refreshAutomationBtn = document.getElementById("refresh-automation-btn");
  refreshAutomationBtn.addEventListener("click", () =>
    withButtonFeedback(refreshAutomationBtn, () => loadAutomation()),
  );

  const checkActivityBtn = document.getElementById("check-activity-btn");
  if (checkActivityBtn) {
    checkActivityBtn.addEventListener("click", () => checkSensorActivity());
  }

  document.querySelectorAll(".demo-buttons [data-sensor]").forEach((btn) => {
    btn.addEventListener("click", () => sendDemoReading(btn.dataset.sensor));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wireControls();
  applyRoleVisibility();
  loadForRole();
});
