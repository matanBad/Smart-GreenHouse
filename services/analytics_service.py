"""
analytics_service.py -> Dashboard Analytics and Health Score

PRD area: Dashboard Analytics and Greenhouse Health Score (Prompt 8).

Aggregates the data the rest of the system already produced — valid readings,
alerts, and derived sensor statuses — into simple, read-only dashboard metrics:
average values, alert counts, the most frequent abnormal condition, recent
trends, an overall greenhouse health status, and a 0-100 health score.

Design notes:
- This service is READ-ONLY. It never mutates stored data and never trusts the
  client; every number is computed on the server from stored records.
- Only valid readings are ever considered: rejected readings are never written to
  readings.json (they live only in system_logs.json), so reading-based metrics
  are valid-only by construction.
- Health status and score are derived from CURRENT state (latest reading status
  per sensor, active alerts, and communication status) — not historical records.
- No machine learning, no prediction. Trends are a plain first-vs-last comparison
  over the most recent few readings, suitable for an academic MVP.
"""

from collections import Counter

from services.alert_service import get_active_alerts
from services.sensor_service import VALID_SENSOR_TYPES, get_all_sensor_statuses
from services.storage_service import read_json

READINGS_FILE = "readings.json"
ALERTS_FILE = "alerts.json"

# How many of the most recent readings to use when computing a trend.
TREND_WINDOW = 5
# Minimum readings needed to compute a trend at all.
TREND_MIN_SAMPLES = 2

# Score weights (points subtracted from a starting score of 100).
SCORE_START = 100
PENALTY_WARNING_SENSOR = 10
PENALTY_CRITICAL_SENSOR = 25
PENALTY_ACTIVE_WARNING_ALERT = 10
PENALTY_ACTIVE_CRITICAL_ALERT = 25
PENALTY_INACTIVE_SENSOR = 10
PENALTY_NO_DATA_SENSOR = 5


def _valid_readings():
    """All stored readings (readings.json holds validated readings only)."""
    return list(read_json(READINGS_FILE, default=[]))


def _all_alerts():
    """All alerts (active + resolved)."""
    return list(read_json(ALERTS_FILE, default=[]))


def _is_number(value):
    """True for real numeric values (excludes bools, which are int subclasses)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# --------------------------------------------------------------------------- #
# Average sensor values
# --------------------------------------------------------------------------- #
def get_average_value_by_sensor_type(sensor_type):
    """
    Average of all valid reading values for one sensor type.

    Returns {sensor_type, average, count}. When no valid readings exist,
    `average` is None and a friendly message is included.
    """
    values = [
        r.get("value")
        for r in _valid_readings()
        if r.get("sensor_type") == sensor_type and _is_number(r.get("value"))
    ]
    if not values:
        return {
            "sensor_type": sensor_type,
            "average": None,
            "count": 0,
            "message": "No valid readings available",
        }
    return {
        "sensor_type": sensor_type,
        "average": round(sum(values) / len(values), 2),
        "count": len(values),
    }


def get_average_values_for_all_sensors():
    """Average value per supported sensor type, keyed by sensor type."""
    return {
        sensor_type: get_average_value_by_sensor_type(sensor_type)
        for sensor_type in VALID_SENSOR_TYPES
    }


# --------------------------------------------------------------------------- #
# Alert counts
# --------------------------------------------------------------------------- #
def count_alerts_by_sensor_type():
    """
    Total and active alert counts per supported sensor type.

    Returns { sensor_type: {"total": int, "active": int} }.
    """
    counts = {
        sensor_type: {"total": 0, "active": 0} for sensor_type in VALID_SENSOR_TYPES
    }
    for alert in _all_alerts():
        sensor_type = alert.get("sensor_type")
        if sensor_type not in counts:
            continue
        counts[sensor_type]["total"] += 1
        if alert.get("status") == "active":
            counts[sensor_type]["active"] += 1
    return counts


# --------------------------------------------------------------------------- #
# Most frequent abnormal condition
# --------------------------------------------------------------------------- #
def get_most_frequent_abnormal_condition():
    """
    The single most common alert_type across all alerts.

    Returns {alert_type, count}; when there are no alerts, alert_type is None
    with a friendly message.
    """
    alert_types = [a.get("alert_type") for a in _all_alerts() if a.get("alert_type")]
    if not alert_types:
        return {
            "alert_type": None,
            "count": 0,
            "message": "No abnormal conditions detected yet",
        }
    alert_type, count = Counter(alert_types).most_common(1)[0]
    return {"alert_type": alert_type, "count": count}


# --------------------------------------------------------------------------- #
# Recent trends
# --------------------------------------------------------------------------- #
def _reading_sort_key(reading):
    """Order readings oldest-first, preferring created_at, then timestamp."""
    return (reading.get("created_at") or "", reading.get("timestamp") or "")


def get_recent_trend_by_sensor_type(sensor_type):
    """
    A simple trend for one sensor type from its most recent valid readings.

    Uses up to TREND_WINDOW newest readings and compares the latest value to the
    oldest in that window:
        increasing / decreasing / stable / insufficient_data
    """
    readings = sorted(
        (
            r
            for r in _valid_readings()
            if r.get("sensor_type") == sensor_type and _is_number(r.get("value"))
        ),
        key=_reading_sort_key,
    )
    window = readings[-TREND_WINDOW:]
    if len(window) < TREND_MIN_SAMPLES:
        return {
            "sensor_type": sensor_type,
            "trend": "insufficient_data",
            "sample_size": len(window),
            "message": "Not enough readings to determine a trend",
        }

    oldest = window[0]["value"]
    latest = window[-1]["value"]
    diff = latest - oldest
    # "Almost equal" is treated as stable. Tolerance scales with magnitude so the
    # same rule works for both small (%) and large (lux) sensor ranges.
    tolerance = max(abs(oldest) * 0.02, 0.01)
    if abs(diff) <= tolerance:
        trend = "stable"
    elif diff > 0:
        trend = "increasing"
    else:
        trend = "decreasing"

    return {
        "sensor_type": sensor_type,
        "trend": trend,
        "sample_size": len(window),
        "oldest_value": oldest,
        "latest_value": latest,
    }


def get_recent_trends_for_all_sensors():
    """Recent trend per supported sensor type, keyed by sensor type."""
    return {
        sensor_type: get_recent_trend_by_sensor_type(sensor_type)
        for sensor_type in VALID_SENSOR_TYPES
    }


# --------------------------------------------------------------------------- #
# Current-state helpers (shared by health status + score)
# --------------------------------------------------------------------------- #
def _current_reading_status(sensor_status):
    """The reading_status of a sensor's latest reading, or None if no reading."""
    current = sensor_status.get("current_reading")
    if isinstance(current, dict):
        return current.get("reading_status")
    return None


def collect_current_state():
    """
    Snapshot of the current state used for health status + score.

    Returns a dict of counts/flags so status and score stay consistent.
    """
    statuses = get_all_sensor_statuses()
    active_alerts = get_active_alerts()

    warning_sensors = 0
    critical_sensors = 0
    inactive_sensors = 0
    no_data_sensors = 0
    for sensor in statuses:
        reading_status = _current_reading_status(sensor)
        if reading_status == "warning":
            warning_sensors += 1
        elif reading_status == "critical":
            critical_sensors += 1

        communication = sensor.get("communication_status")
        if communication == "inactive":
            inactive_sensors += 1
        elif communication == "no_data":
            no_data_sensors += 1

    active_warning_alerts = sum(1 for a in active_alerts if a.get("severity") == "warning")
    active_critical_alerts = sum(
        1 for a in active_alerts if a.get("severity") == "critical"
    )

    return {
        "warning_sensors": warning_sensors,
        "critical_sensors": critical_sensors,
        "inactive_sensors": inactive_sensors,
        "no_data_sensors": no_data_sensors,
        "active_warning_alerts": active_warning_alerts,
        "active_critical_alerts": active_critical_alerts,
    }


# --------------------------------------------------------------------------- #
# Greenhouse health status
# --------------------------------------------------------------------------- #
def calculate_greenhouse_health_status(state=None):
    """
    Overall health status derived from current state.

    - critical:        any critical sensor reading or active critical alert
    - needs_attention: any warning sensor reading, active warning alert, or
                       inactive sensor
    - healthy:         otherwise
    Returns {health_status, explanation}.

    Pass a precomputed `state` (from `collect_current_state()`) to derive status
    and score from the SAME snapshot; otherwise a fresh snapshot is taken.
    """
    if state is None:
        state = collect_current_state()

    if state["critical_sensors"] or state["active_critical_alerts"]:
        return {
            "health_status": "critical",
            "explanation": "Greenhouse is critical because at least one active "
            "critical alert or critical sensor reading exists.",
        }

    if (
        state["warning_sensors"]
        or state["active_warning_alerts"]
        or state["inactive_sensors"]
    ):
        return {
            "health_status": "needs_attention",
            "explanation": "Greenhouse needs attention because at least one sensor "
            "is in a warning state, has an active warning alert, or is inactive.",
        }

    return {
        "health_status": "healthy",
        "explanation": "Greenhouse is healthy because all current readings are "
        "normal and all sensors are reporting.",
    }


# --------------------------------------------------------------------------- #
# Greenhouse health score
# --------------------------------------------------------------------------- #
def _score_interpretation(score):
    """Map a 0-100 score to good / moderate / poor."""
    if score >= 80:
        return "good"
    if score >= 50:
        return "moderate"
    return "poor"


def calculate_greenhouse_health_score(state=None):
    """
    A simple 0-100 greenhouse health score derived from current state.

    Starts at 100 and subtracts weighted penalties for warning/critical sensors,
    active warning/critical alerts, and inactive/no_data sensors. Clamped to
    [0, 100]. Returns {score, interpretation, breakdown}.

    Pass a precomputed `state` (from `collect_current_state()`) to derive status
    and score from the SAME snapshot; otherwise a fresh snapshot is taken.
    """
    if state is None:
        state = collect_current_state()

    raw = (
        SCORE_START
        - state["warning_sensors"] * PENALTY_WARNING_SENSOR
        - state["critical_sensors"] * PENALTY_CRITICAL_SENSOR
        - state["active_warning_alerts"] * PENALTY_ACTIVE_WARNING_ALERT
        - state["active_critical_alerts"] * PENALTY_ACTIVE_CRITICAL_ALERT
        - state["inactive_sensors"] * PENALTY_INACTIVE_SENSOR
        - state["no_data_sensors"] * PENALTY_NO_DATA_SENSOR
    )
    score = max(0, min(100, raw))

    return {
        "score": score,
        "interpretation": _score_interpretation(score),
        "breakdown": state,
    }


# --------------------------------------------------------------------------- #
# Combined dashboard summary
# --------------------------------------------------------------------------- #
def get_dashboard_analytics_summary():
    """
    The full analytics payload for the dashboard (read-only).

    Combines averages, alert counts, the most frequent abnormal condition,
    recent trends, the greenhouse health status, and the health score.
    """
    state = collect_current_state()
    health_status = calculate_greenhouse_health_status(state)
    health_score = calculate_greenhouse_health_score(state)
    return {
        "average_values": get_average_values_for_all_sensors(),
        "alert_counts_by_sensor_type": count_alerts_by_sensor_type(),
        "most_frequent_abnormal_condition": get_most_frequent_abnormal_condition(),
        "recent_trends": get_recent_trends_for_all_sensors(),
        "greenhouse_health_status": health_status,
        "greenhouse_health_score": health_score,
    }
