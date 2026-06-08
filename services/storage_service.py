"""
storage_service.py -> JSON Storage

Future PRD area: JSON Storage.

This service is the single place that reads and writes the JSON files in /data.
Centralizing file access keeps the rest of the app simple and makes it easy to
swap JSON for a real database in a later prompt without touching other modules.

Prompt 2 adds an `append_json` helper so services can store new records (such as
sensor readings and system logs) without re-implementing read/modify/write.
"""

import json
import os

# Absolute path to the /data directory, resolved relative to the project root.
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Default contents used when a data file is missing.
# Sensors, threshold rules, users, and actuators have seeded defaults; everything
# else starts as an empty list.
DEFAULT_ACTUATORS = [
    {
        "actuator_id": "ACT-VENT-001",
        "actuator_type": "ventilation",
        "actuator_name": "Ventilation Fan",
        "status": "inactive",
        "greenhouse_id": "GH-001",
        "last_activation_time": None,
        "last_trigger_reason": None,
    },
    {
        "actuator_id": "ACT-IRR-001",
        "actuator_type": "irrigation",
        "actuator_name": "Irrigation System",
        "status": "inactive",
        "greenhouse_id": "GH-001",
        "last_activation_time": None,
        "last_trigger_reason": None,
    },
    {
        "actuator_id": "ACT-LIGHT-001",
        "actuator_type": "lighting",
        "actuator_name": "Artificial Lighting",
        "status": "inactive",
        "greenhouse_id": "GH-001",
        "last_activation_time": None,
        "last_trigger_reason": None,
    },
    {
        "actuator_id": "ACT-AIR-001",
        "actuator_type": "air_circulation",
        "actuator_name": "Air Circulation Fan",
        "status": "inactive",
        "greenhouse_id": "GH-001",
        "last_activation_time": None,
        "last_trigger_reason": None,
    },
]

DEFAULT_FILES = {
    "sensors.json": [],
    "readings.json": [],
    "alerts.json": [],
    "actuators.json": DEFAULT_ACTUATORS,
    "automation_actions.json": [],
    "system_logs.json": [],
    "threshold_rules.json": [],
    "simulation_scenarios.json": [],
    "users.json": [],
}


def _file_path(filename):
    """Build the absolute path for a data file inside /data."""
    return os.path.join(DATA_DIR, filename)


def init_storage():
    """
    Ensure the /data directory and all expected JSON files exist.

    Called once at application startup. Missing files are created with a safe
    default so later reads never crash on a missing file.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    for filename, default in DEFAULT_FILES.items():
        path = _file_path(filename)
        if not os.path.exists(path):
            write_json(filename, default)


def read_json(filename, default=None):
    """
    Safely read a JSON file from /data.

    Returns `default` (or an empty list) if the file is missing or unreadable,
    so callers never have to worry about missing-file errors.
    """
    if default is None:
        default = []

    path = _file_path(filename)
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable file — fall back to the safe default.
        return default


def write_json(filename, data):
    """Safely write JSON data to a file in /data."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _file_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def append_json(filename, item):
    """
    Append a single record to a JSON file that holds a list.

    Reads the current list (falling back to an empty list), appends the item,
    and writes it back. Returns the stored item.
    """
    items = read_json(filename, default=[])
    if not isinstance(items, list):
        items = []
    items.append(item)
    write_json(filename, items)
    return item
