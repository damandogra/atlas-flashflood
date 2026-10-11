"""
05_citizen.py
=============
Issue #19 — Community observation store using SQLite.

Provides:
  - init_db()            — creates the SQLite schema on first run
  - add_observation()    — insert a new community report
  - get_observations()   — retrieve all reports (optionally filtered)
  - as_geojson()         — return a GeoJSON FeatureCollection

Schema:
  observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT,
    lat         REAL,
    lon         REAL,
    event_type  TEXT,   -- e.g. "flooding", "road_blocked", "structure_damage"
    severity    INTEGER,-- 1=minor 2=moderate 3=severe
    description TEXT,
    reporter    TEXT    -- optional, anonymous by default
  )

Usage:
    import citizen
    citizen.init_db()
    citizen.add_observation(lat=31.42, lon=-7.05,
                            event_type="road_blocked", severity=3,
                            description="R304 bridge under water")
    print(citizen.as_geojson())
"""

import os
import sys
import sqlite3
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

DB_PATH = config.DB_PATH


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    lat         REAL    NOT NULL,
    lon         REAL    NOT NULL,
    event_type  TEXT    NOT NULL,
    severity    INTEGER NOT NULL CHECK(severity IN (1, 2, 3)),
    description TEXT,
    reporter    TEXT    DEFAULT 'anonymous'
);
"""

VALID_EVENT_TYPES = {
    "flooding", "road_blocked", "structure_damage",
    "evacuation_needed", "infrastructure_damage", "other"
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(db_path: str = DB_PATH) -> None:
    """Create the database and schema if they don't already exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_CREATE_SQL)
        conn.commit()
    print(f"   ✅  Database ready: {db_path}")


def add_observation(lat: float, lon: float,
                    event_type: str, severity: int,
                    description: str = "",
                    reporter: str = "anonymous",
                    db_path: str = DB_PATH) -> int:
    """
    Insert a new community observation.

    Returns the new row id.
    Raises ValueError for invalid inputs.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Invalid coordinates: lat={lat}, lon={lon}")
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{event_type}'. "
                         f"Valid types: {sorted(VALID_EVENT_TYPES)}")
    if severity not in (1, 2, 3):
        raise ValueError("Severity must be 1 (minor), 2 (moderate), or 3 (severe).")

    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    sql = """
        INSERT INTO observations (timestamp, lat, lon, event_type, severity, description, reporter)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, (timestamp, lat, lon, event_type,
                                 severity, description, reporter))
        conn.commit()
        return cur.lastrowid


def get_observations(event_type: str = None,
                     min_severity: int = 1,
                     db_path: str = DB_PATH) -> list:
    """
    Retrieve observations as a list of dicts.

    Args:
        event_type:   Filter by event type (None = all).
        min_severity: Minimum severity level (1-3).
    """
    sql  = "SELECT * FROM observations WHERE severity >= ?"
    args = [min_severity]
    if event_type:
        sql  += " AND event_type = ?"
        args.append(event_type)
    sql += " ORDER BY timestamp DESC"

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


def as_geojson(event_type: str = None,
               min_severity: int = 1,
               db_path: str = DB_PATH) -> dict:
    """
    Return all observations as a GeoJSON FeatureCollection.
    Suitable for direct serving from the /citizen API endpoint.
    """
    rows = get_observations(event_type=event_type,
                            min_severity=min_severity,
                            db_path=db_path)
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["lon"], r["lat"]],
            },
            "properties": {
                "id":          r["id"],
                "timestamp":   r["timestamp"],
                "event_type":  r["event_type"],
                "severity":    r["severity"],
                "description": r["description"],
                "reporter":    r["reporter"],
            },
        })
    return {
        "type":     "FeatureCollection",
        "features": features,
    }


def delete_observation(obs_id: int, db_path: str = DB_PATH) -> bool:
    """Delete a single observation by id. Returns True if deleted."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM observations WHERE id = ?", (obs_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("📋  CITIZEN OBSERVATION STORE  (Issue #19)")
    print("=" * 55)
    init_db()

    # Demo: insert a sample observation
    rid = add_observation(
        lat=31.42, lon=-7.05,
        event_type="road_blocked",
        severity=3,
        description="R304 bridge under 0.8 m of water. Impassable.",
        reporter="demo",
    )
    print(f"   Inserted demo observation id={rid}")

    # Show as GeoJSON
    geojson = as_geojson()
    print(f"\n   GeoJSON FeatureCollection ({len(geojson['features'])} features):")
    print(json.dumps(geojson, indent=2))