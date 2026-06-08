"""
access_control_service.py -> User Access & Role-Based Permissions

PRD area: User Access and Role-Based Permissions (Prompt 10).

This service is the single source of truth for *who may do what*. It defines the
permission matrix for the three project roles and exposes small, pure helpers the
route layer uses to authorize each request.

Security model for this stage (academic MVP):
    - There is no production login / password / JWT yet. The caller declares its
      role with the request header "X-User-Role".
    - Supported roles: greenhouse_manager, farm_owner, system_administrator.
    - The role from any JSON body is IGNORED for authorization — only the header
      is trusted as the role source, and every protected request is validated.
    - Frontend UI hiding is never trusted; the backend enforces permissions and
      logs every unauthorized / invalid-role attempt.

Keeping this logic here (rather than scattered through app.py) means the route
layer stays thin and the permission rules live in one auditable place.

This module is intentionally PURE: it makes authorization decisions only and has
no side effects (no HTTP, no logging, no storage). The route layer is responsible
for turning a decision into an HTTP response and for writing the audit log.
"""

# The header that carries the demo role for this MVP.
ROLE_HEADER = "X-User-Role"

# Canonical role identifiers.
GREENHOUSE_MANAGER = "greenhouse_manager"
FARM_OWNER = "farm_owner"
SYSTEM_ADMINISTRATOR = "system_administrator"

VALID_ROLES = (GREENHOUSE_MANAGER, FARM_OWNER, SYSTEM_ADMINISTRATOR)

# Permission matrix: role -> set of allowed action names. Actions are coarse,
# human-readable capability names that the route layer maps onto endpoints.
ROLE_PERMISSIONS = {
    GREENHOUSE_MANAGER: {
        "view_dashboard",
        "view_current_readings",
        "view_active_alerts",
        "resolve_alerts",
        "view_reading_history",
        "view_alert_history",
        "view_automation_status",
        "view_automation_history",
        "run_simulation_scenarios",
        "view_sensor_status",
    },
    FARM_OWNER: {
        "view_farm_owner_summary",
        "view_greenhouse_health_status",
        "view_greenhouse_health_score",
        "view_basic_analytics",
        "view_most_frequent_abnormal_condition",
    },
    SYSTEM_ADMINISTRATOR: {
        "view_dashboard",
        "view_current_readings",
        "view_sensor_status",
        "update_sensor_configuration",
        "update_thresholds",
        "view_admin_logs",
        "view_rejected_readings",
        "view_system_logs",
        "check_sensor_activity",
        "reset_actuators",
        "view_threshold_history",
    },
}


def normalize_role(role):
    """
    Normalise a raw role value to its canonical form.

    Trims surrounding whitespace and lowercases so header casing / padding does
    not matter. Returns "" for None so callers never deal with None.
    """
    if not isinstance(role, str):
        return ""
    return role.strip().lower()


def is_valid_role(role):
    """True if the (normalised) role is one of the supported project roles."""
    return normalize_role(role) in VALID_ROLES


def get_role_from_request(request):
    """
    Read the caller's role from the X-User-Role request header.

    The role is ALWAYS taken from the header — never from the JSON body — so a
    request cannot escalate its privileges by putting a role in the payload.
    Returns the normalised role string (possibly "" if the header is absent).
    """
    return normalize_role(request.headers.get(ROLE_HEADER))


def has_permission(role, action):
    """True if `role` is allowed to perform `action`."""
    return action in ROLE_PERMISSIONS.get(normalize_role(role), set())


def get_allowed_actions_for_role(role):
    """Return the sorted list of actions a role is allowed to perform."""
    return sorted(ROLE_PERMISSIONS.get(normalize_role(role), set()))


def require_permission(role, action):
    """
    Decide whether a role may perform an action (pure; no HTTP, no logging).

    `action` may be a single action name or an iterable of action names; access
    is granted if the role holds ANY of them (this lets one endpoint serve more
    than one capability, e.g. an admin who may reset actuators also needs to
    read them).

    Returns a small result dict the route layer maps onto an HTTP response:
        {"allowed": True,  "error": None}
        {"allowed": False, "error": "invalid_role"}  # missing / unknown role
        {"allowed": False, "error": "forbidden"}     # valid role, no permission
    """
    actions = [action] if isinstance(action, str) else list(action)

    if not is_valid_role(role):
        return {"allowed": False, "error": "invalid_role"}

    if any(has_permission(role, a) for a in actions):
        return {"allowed": True, "error": None}

    return {"allowed": False, "error": "forbidden"}
