"""
04_early_warning.py
===================
Issue #17 — Early warning: live rainfall forecast → EU Floods Directive alert level.

Fetches the 24-hour accumulated precipitation forecast from Open-Meteo (no API key)
for the Ounila catchment centroid, maps it to one of four alert levels, and returns
a structured alert dict that the FastAPI /alert endpoint serves directly.

Also exposes a pure function `classify_alert(rainfall_mm)` used by tests and the API.

Usage:
    python 04_early_warning.py          # prints current live alert
    import early_warning; early_warning.get_alert()  # returns dict
"""

import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ---------------------------------------------------------------------------
# Catchment centroid (approx centre of CATCHMENT_COORDS bbox)
# ---------------------------------------------------------------------------
_LAT = 31.33
_LON = -7.09

# ---------------------------------------------------------------------------
# Alert level definitions (EU Floods Directive 4-colour framework)
# ---------------------------------------------------------------------------
LEVELS = [
    {
        "level":       "red",
        "label":       "RED — Emergency",
        "description": "Extreme flooding likely. Act immediately.",
        "min_mm":      config.ALERT_THRESHOLDS["red"],
    },
    {
        "level":       "orange",
        "label":       "ORANGE — Warning",
        "description": "Significant flooding expected. Prepare to act.",
        "min_mm":      config.ALERT_THRESHOLDS["orange"],
    },
    {
        "level":       "yellow",
        "label":       "YELLOW — Watch",
        "description": "Elevated risk. Monitor conditions closely.",
        "min_mm":      config.ALERT_THRESHOLDS["yellow"],
    },
    {
        "level":       "green",
        "label":       "GREEN — Routine",
        "description": "No significant flood risk forecast.",
        "min_mm":      config.ALERT_THRESHOLDS["green"],
    },
]


def classify_alert(rainfall_mm: float) -> dict:
    """
    Map a 24-hour forecast rainfall total (mm) to an alert level.

    Thresholds from config.ALERT_THRESHOLDS, calibrated against the
    HEC-HMS hydrograph peak discharges.

    Returns a dict with: level, label, description, threshold_mm, rainfall_mm.
    """
    for lvl in LEVELS:           # LEVELS is ordered red → green (highest first)
        if rainfall_mm >= lvl["min_mm"]:
            return {
                "level":         lvl["level"],
                "label":         lvl["label"],
                "description":   lvl["description"],
                "threshold_mm":  lvl["min_mm"],
                "rainfall_mm":   round(rainfall_mm, 1),
            }
    # Fallback (should never reach here)
    return {
        "level":       "green",
        "label":       "GREEN — Routine",
        "description": "No significant flood risk forecast.",
        "threshold_mm": 0,
        "rainfall_mm":  round(rainfall_mm, 1),
    }


def fetch_forecast_rainfall(lat: float = _LAT, lon: float = _LON,
                             hours: int = 24) -> float:
    """
    Fetch accumulated precipitation forecast (mm) over the next `hours` hours
    from Open-Meteo (https://open-meteo.com) — no API key required.

    Returns the sum of hourly precipitation values.
    Raises requests.RequestException if the API is unreachable.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":            lat,
        "longitude":           lon,
        "hourly":              "precipitation",
        "forecast_days":       2,
        "timezone":            "Africa/Casablanca",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    hourly_precip = data["hourly"]["precipitation"][:hours]
    return float(sum(hourly_precip))


def get_alert(lat: float = _LAT, lon: float = _LON) -> dict:
    """
    Fetch live forecast and return the current alert dict.
    Falls back to green alert if the API is unreachable (fail-safe).
    """
    try:
        rainfall_mm = fetch_forecast_rainfall(lat, lon)
        alert = classify_alert(rainfall_mm)
        alert["source"]    = "open-meteo.com (live)"
        alert["timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
        alert["lat"]       = lat
        alert["lon"]       = lon
        return alert
    except Exception as exc:
        return {
            "level":       "green",
            "label":       "GREEN — Routine (API unavailable)",
            "description": f"Could not reach Open-Meteo: {exc}",
            "threshold_mm": 0,
            "rainfall_mm":  None,
            "source":      "fallback",
            "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
            "lat":         lat,
            "lon":         lon,
        }


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("⚡  EARLY WARNING ENGINE  (Issue #17)")
    print("=" * 55)
    alert = get_alert()
    print(json.dumps(alert, indent=2))