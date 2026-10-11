"""
07_action_generator.py
======================
Issue #35 — Rule-based action card generator.

Reads exposure_T*.geojson, road_passability_T*.geojson, and
evacuation_summary.json, then produces a ranked list of recommended
actions for emergency planners.

Priority levels: CRITICAL → HIGH → MEDIUM

Outputs:
  data/outputs/action_cards.json

Usage:
    python 07_action_generator.py
"""

import os
import sys
import json
import uuid
import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# Default scenario for action generation (worst credible event)
DEFAULT_SCENARIO = "T100"


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

def _rules_buildings(buildings: gpd.GeoDataFrame,
                     scenario: str, label: str) -> list:
    """Generate action cards from building exposure data."""
    cards = []
    if buildings is None or buildings.empty:
        return cards

    # R1: Hospital / clinic at any flood risk
    critical = buildings[
        (buildings.get("vuln_weight", 0) >= 3.0) &
        (buildings.get("depth_m", 0) >= config.PARAMS["flood_min_m"])
    ] if "vuln_weight" in buildings.columns else gpd.GeoDataFrame()

    for _, row in critical.iterrows():
        name = row.get("name") or row.get("amenity") or "Critical facility"
        depth = round(float(row.get("depth_m", 0)), 2)
        lon, lat = row.geometry.centroid.x, row.geometry.centroid.y
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "CRITICAL",
            "scenario": scenario,
            "action":   f"Pre-position evacuation and install flood barrier at {name}",
            "reason":   f"Critical facility exposed to {depth} m flooding ({label} event)",
            "asset":    name,
            "lat":      round(lat, 5),
            "lon":      round(lon, 5),
            "tags":     ["critical_infrastructure", "evacuation"],
        })

    # R2: School at risk → school closure + pupil evacuation
    schools = buildings[
        buildings.get("amenity", "").astype(str).str.contains("school", na=False) &
        (buildings.get("depth_m", 0) >= config.PARAMS["flood_min_m"])
    ] if "amenity" in buildings.columns else gpd.GeoDataFrame()

    for _, row in schools.iterrows():
        name = row.get("name") or "School"
        depth = round(float(row.get("depth_m", 0)), 2)
        lon, lat = row.geometry.centroid.x, row.geometry.centroid.y
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "HIGH",
            "scenario": scenario,
            "action":   f"Close {name} and evacuate pupils before flood peak",
            "reason":   f"School exposed to {depth} m flooding ({label})",
            "asset":    name,
            "lat":      round(lat, 5),
            "lon":      round(lon, 5),
            "tags":     ["school", "evacuation"],
        })

    # R3: High-risk residential clusters → evacuation order
    high_res = buildings[
        (buildings.get("risk_level", "") == "High") &
        (buildings.get("vuln_weight", 0).between(1.5, 2.5))
    ] if "risk_level" in buildings.columns else gpd.GeoDataFrame()

    if len(high_res) >= 3:
        centroid = high_res.geometry.centroid
        lat = float(centroid.y.mean())
        lon = float(centroid.x.mean())
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "HIGH",
            "scenario": scenario,
            "action":   f"Issue evacuation order for {len(high_res)} high-risk residential buildings",
            "reason":   f"Residential area exposed to high hazard scores ({label})",
            "asset":    "Residential cluster",
            "lat":      round(lat, 5),
            "lon":      round(lon, 5),
            "tags":     ["residential", "evacuation"],
        })

    return cards


def _rules_roads(roads: gpd.GeoDataFrame,
                 evac_summary: dict,
                 scenario: str, label: str) -> list:
    """Generate action cards from road passability data."""
    cards = []
    if roads is None or roads.empty:
        return cards

    # R4: Impassable bridge or major road → close + assess
    major_highways = {"primary", "secondary", "trunk", "motorway"}
    blocked_major = roads[
        (roads.get("status", "") == "impassable") &
        (roads.get("highway", "").astype(str).isin(major_highways))
    ] if "highway" in roads.columns else gpd.GeoDataFrame()

    for _, row in blocked_major.iterrows():
        name = row.get("name") or f"{row.get('highway', 'road').title()} segment"
        depth = round(float(row.get("flood_depth_m", 0)), 2)
        geom = row.geometry
        pt = geom.interpolate(0.5, normalized=True)
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "HIGH",
            "scenario": scenario,
            "action":   f"Close {name} and place barriers; assess structural integrity",
            "reason":   f"Major road impassable ({depth} m depth, {label})",
            "asset":    name,
            "lat":      round(pt.y, 5),
            "lon":      round(pt.x, 5),
            "tags":     ["road", "closure"],
        })

    # R5: Isolated communities → pre-position supplies / open shelter
    sc_data = evac_summary.get(scenario, {})
    n_isolated = sc_data.get("isolated_communities", 0)
    if n_isolated > 0:
        for detail in sc_data.get("isolated_details", [])[:5]:   # max 5 cards
            coords = detail.get("centroid_utm", [0, 0])
            cards.append({
                "id":       str(uuid.uuid4())[:8],
                "priority": "CRITICAL" if n_isolated >= 3 else "HIGH",
                "scenario": scenario,
                "action":   "Pre-position emergency supplies; open nearest shelter",
                "reason":   f"Community loses all road access ({label}). "
                            f"{detail.get('node_count', '?')} road nodes isolated.",
                "asset":    "Isolated community",
                "lat":      None,   # UTM coords — frontend can approximate
                "lon":      None,
                "tags":     ["isolation", "supply", "shelter"],
            })

    # R6: Emergency-only corridor exists → notify emergency services
    emergency_segs = roads[
        roads.get("status", "") == "emergency_only"
    ] if "status" in roads.columns else gpd.GeoDataFrame()

    if len(emergency_segs) > 0:
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "MEDIUM",
            "scenario": scenario,
            "action":   f"Notify emergency services: {len(emergency_segs)} segments passable by emergency vehicles only",
            "reason":   f"Partial flooding on {len(emergency_segs)} road segments ({label})",
            "asset":    "Road network",
            "lat":      None,
            "lon":      None,
            "tags":     ["road", "emergency_access"],
        })

    return cards


def _rules_general(scenario: str, label: str,
                   n_buildings: int, n_critical: int) -> list:
    """Generate general protocol cards based on aggregate stats."""
    cards = []

    # R7: Any critical assets at risk → activate EOC
    if n_critical > 0:
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "CRITICAL",
            "scenario": scenario,
            "action":   "Activate Emergency Operations Centre (EOC)",
            "reason":   f"{n_critical} critical assets exposed in {label} scenario",
            "asset":    "EOC",
            "lat":      None,
            "lon":      None,
            "tags":     ["eoc", "coordination"],
        })

    # R8: Large number of buildings → issue public alert
    if n_buildings >= 10:
        cards.append({
            "id":       str(uuid.uuid4())[:8],
            "priority": "HIGH",
            "scenario": scenario,
            "action":   "Issue public warning via radio and SMS broadcast",
            "reason":   f"{n_buildings} buildings in flood zone ({label})",
            "asset":    "Public communications",
            "lat":      None,
            "lon":      None,
            "tags":     ["warning", "communications"],
        })

    # R9: Install upstream gauge reminder
    cards.append({
        "id":       str(uuid.uuid4())[:8],
        "priority": "MEDIUM",
        "scenario": scenario,
        "action":   "Install or verify upstream stream gauge operation",
        "reason":   "No real-time gauge data exists for Ounila — "
                    "early warning relies entirely on rainfall forecast.",
        "asset":    "Stream gauge",
        "lat":      31.55,
        "lon":      -7.12,
        "tags":     ["monitoring", "infrastructure"],
    })

    return cards


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}


def _sort_cards(cards: list) -> list:
    return sorted(cards, key=lambda c: _PRIORITY_ORDER.get(c["priority"], 99))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_action_cards(scenario: str = DEFAULT_SCENARIO) -> list:
    """
    Generate ranked action cards for the given scenario.
    Falls back gracefully if output files are missing.
    """
    label = config.SCENARIOS.get(scenario, {}).get("label", scenario)
    print(f"   🃏  Generating action cards for {label} …")

    # --- Load exposure data ---
    exposure_path = os.path.join(config.DATA_OUT, f"exposure_{scenario}.geojson")
    buildings = None
    n_buildings = 0
    n_critical  = 0
    if os.path.exists(exposure_path):
        buildings = gpd.read_file(exposure_path)
        n_buildings = len(buildings)
        n_critical  = int(buildings.get("is_critical", False).sum()) if "is_critical" in buildings.columns else 0
    else:
        print(f"      ⚠️  Exposure file missing for {scenario} — skipping building rules.")

    # --- Load road data ---
    road_path = os.path.join(config.DATA_OUT, f"road_passability_{scenario}.geojson")
    roads = None
    if os.path.exists(road_path):
        roads = gpd.read_file(road_path)
    else:
        print(f"      ⚠️  Road passability file missing for {scenario} — skipping road rules.")

    # --- Load evacuation summary ---
    evac_path = os.path.join(config.DATA_OUT, "evacuation_summary.json")
    evac_summary = {}
    if os.path.exists(evac_path):
        with open(evac_path) as f:
            evac_summary = json.load(f)

    # --- Apply rules ---
    cards = []
    cards += _rules_buildings(buildings, scenario, label)
    cards += _rules_roads(roads, evac_summary, scenario, label)
    cards += _rules_general(scenario, label, n_buildings, n_critical)

    # --- Sort and deduplicate ---
    cards = _sort_cards(cards)

    print(f"      ✅  {len(cards)} action cards generated "
          f"({sum(1 for c in cards if c['priority']=='CRITICAL')} CRITICAL, "
          f"{sum(1 for c in cards if c['priority']=='HIGH')} HIGH, "
          f"{sum(1 for c in cards if c['priority']=='MEDIUM')} MEDIUM)")

    return cards


def write_action_cards(scenario: str = DEFAULT_SCENARIO) -> str:
    """Generate cards and write to data/outputs/action_cards.json."""
    cards = generate_action_cards(scenario)
    out_path = os.path.join(config.DATA_OUT, "action_cards.json")
    with open(out_path, "w") as f:
        json.dump(cards, f, indent=2)
    print(f"   📋  Action cards → {out_path}")
    return out_path


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("🃏  ACTION GENERATOR  (Issue #35)")
    print("=" * 55)
    write_action_cards()