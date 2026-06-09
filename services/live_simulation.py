"""
live_simulation.py -> Live sensor simulator (background)

Provides a simple background loop that generates periodic readings for all
configured sensors to simulate live hardware. The loop sends each generated
reading through the normal ingestion pipeline (`process_reading`) so validation,
rule-evaluation, alerts and automation behave exactly as they would with real
hardware.

API:
- start_live_simulation(interval_seconds=5)
- stop_live_simulation()
- get_live_simulation_status() -> dict

This module uses a background Thread and an Event to stop gracefully. It is
intended for demo/demo-admin usage only.
"""
from threading import Thread, Event
import time
import random
from datetime import datetime, timezone

from services.storage_service import read_json
from services.rule_engine import get_threshold_rule
from services.reading_pipeline import process_reading
from services.sensor_service import get_all_sensors

_thread = None
_stop_event = None
_interval = 5


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _generate_value_for_sensor(sensor):
    """Return a value to emit for a sensor dict.

    Strategy:
    - If there is a threshold rule, usually generate a value inside the range
      (80% chance). Occasionally (20%) produce an out-of-range value to test
      alerts and automation.
    - If no rule, generate a reasonable default value based on type.
    """
    sensor_type = sensor.get("sensor_type")
    rule = get_threshold_rule(sensor_type)
    if rule:
        min_v = rule.get("min_value")
        max_v = rule.get("max_value")
        warning_margin = rule.get("warning_margin") or 1
        # 20% chance to breach
        if random.random() < 0.2:
            # breach either below min or above max
            if random.random() < 0.5:
                return float(min_v - (warning_margin + random.uniform(1, 5)))
            else:
                return float(max_v + (warning_margin + random.uniform(1, 5)))
        else:
            # inside range, pick evenly across [min, max]
            return float(round(min_v + random.random() * (max_v - min_v), 2))
    # fallbacks by type
    if sensor_type == "temperature":
        return float(round(20 + random.random() * 8, 2))
    if sensor_type == "humidity":
        return float(round(45 + random.random() * 20, 2))
    if sensor_type == "soil_moisture":
        return float(round(35 + random.random() * 20, 2))
    if sensor_type == "light_intensity":
        return float(round(3000 + random.random() * 4000, 2))
    return 0.0


def _live_loop(interval_seconds, stop_event):
    sensors = get_all_sensors()
    while not stop_event.is_set():
        for sensor in sensors:
            if stop_event.is_set():
                break
            # Only simulate for enabled sensors
            if sensor.get("status") != "enabled":
                continue
            value = _generate_value_for_sensor(sensor)
            payload = {
                "sensor_id": sensor.get("sensor_id"),
                "sensor_type": sensor.get("sensor_type"),
                "value": value,
                "unit": sensor.get("unit"),
                "timestamp": _now_iso(),
            }
            try:
                # Run through the real pipeline so everything is tested the same.
                # Use source=None to better emulate a real hardware sensor so
                # generated readings are indistinguishable from device-origin.
                process_reading(sensor.get("sensor_id"), payload, source=None)
            except Exception:
                # Never crash the loop on a single failure; continue.
                pass
            # small spacing between sensors so timestamps differ
            time.sleep(max(0.1, interval_seconds / max(4, len(sensors))))
        # sleep until next round
        for _ in range(int(max(1, interval_seconds))):
            if stop_event.is_set():
                break
            time.sleep(1)


def start_live_simulation(interval_seconds=5):
    """Start the live simulation background loop.

    Returns True if started, False if already running.
    """
    global _thread, _stop_event, _interval
    if _thread and _thread.is_alive():
        return False
    _interval = max(1, int(interval_seconds))
    _stop_event = Event()
    _thread = Thread(target=_live_loop, args=(_interval, _stop_event), daemon=True)
    _thread.start()
    return True


def stop_live_simulation():
    """Stop the live simulation if running. Returns True if stopped, False if not running."""
    global _thread, _stop_event
    if not _thread:
        return False
    if not _thread.is_alive():
        _thread = None
        _stop_event = None
        return False
    _stop_event.set()
    _thread.join(timeout=5)
    _thread = None
    _stop_event = None
    return True


def get_live_simulation_status():
    """Return status dict: {running: bool, interval_seconds: int}"""
    return {"running": bool(_thread and _thread.is_alive()), "interval_seconds": _interval}


