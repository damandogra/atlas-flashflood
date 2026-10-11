"""Generate the early-action list for every scenario from playbook.yaml and the impact results.

Usage: python -m pipeline.impact.actions          (after pipeline.impact.engine)
Output: data/runs/impact/actions_<scenario>.json - actions sorted by deadline (hours from storm start).
"""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from pyproj import Transformer

from pipeline import config
from pipeline.impact.engine import OUT, PREP

PLAYBOOK = yaml.safe_load((Path(__file__).parent / "playbook.yaml").read_text(encoding="utf8"))["actions"]
PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
_wgs = Transformer.from_crs(config.CRS_WORK, config.CRS_WEB, always_xy=True)



def _label(s, i):
    for col in ("name", "ref"):
        v = s[col].iloc[i]
        if pd.notna(v) and v:
            return str(v)
    return f"{s['highway'].iloc[i]} road"

def _act(key, deadline, where, lonlat=None, reason="", count=None):
    p = PLAYBOOK[key]
    return {"id": key, "title": p["title"], "owner": p["owner"], "priority": p["priority"],
            "deadline_h": round(float(deadline), 2), "where": where,
            "lonlat": [round(lonlat[0], 5), round(lonlat[1], 5)] if lonlat else None,
            "reason": reason, "count": count}


def scenario_actions(name, s, b, places, villages, seg):
    acts = []
    status, closed_from, closed_to = np.array(seg["status"]), np.array(seg["closed_from"]), np.array(seg["closed_to"])
    ford = s["ford"].values.astype(bool)
    ford_closed = np.flatnonzero(ford & (status == 2))
    road_closed = np.flatnonzero(~ford & (status == 2) & s["ref"].fillna("").str.match(r"^R[NP]").values)
    first_water = [v["first_water_h"] for v in villages.values() if v["first_water_h"] is not None]
    t_first = min(first_water + [closed_from[i] for i in ford_closed if closed_from[i] >= 0] or [None]) \
        if (first_water or len(ford_closed)) else None
    if t_first is None:
        return acts
    acts.append(_act("vigilance", t_first + PLAYBOOK["vigilance"]["lead_h"], "Ounila basin",
                     reason=f"first modelled impact at +{t_first:.1f} h"))
    if len(ford_closed):
        tf = min(closed_from[i] for i in ford_closed)
        acts.append(_act("broadcast", tf + PLAYBOOK["broadcast"]["lead_h"], "All valley communes",
                         reason=f"{len(ford_closed)} fords impassable, first at +{tf:.1f} h"))
    for kind, idxs in (("close_ford", ford_closed), ("close_road", road_closed)):
        for i in idxs:
            g = s.geometry.iloc[i].interpolate(0.5, normalized=True)
            label = _label(s, i)
            acts.append(_act(kind, closed_from[i] + PLAYBOOK[kind]["lead_h"], f"{label} ({s['highway'].iloc[i]})",
                             _wgs.transform(g.x, g.y), f"unsafe for 4WD +{closed_from[i]:.1f} h to +{closed_to[i]:.1f} h"))
            acts.append(_act("reopen", closed_to[i] + PLAYBOOK["reopen"]["lead_h"], f"{label} ({s['highway'].iloc[i]})",
                             _wgs.transform(g.x, g.y), "water receded"))
    for v, m in villages.items():
        pl = places.get(v)
        ll = _wgs.transform(pl.x, pl.y) if pl is not None else None
        haz = m["by_hazard"]["significant"] + m["by_hazard"]["extreme"]
        if m["first_water_h"] is not None:
            acts.append(_act("warn_households", m["first_water_h"] + PLAYBOOK["warn_households"]["lead_h"], v, ll,
                             f"{m['buildings_affected']} buildings, ~{m['people_affected']:.0f} residents", m["buildings_affected"]))
            if haz or m["collapse_possible"]:
                acts.append(_act("evacuate", m["first_water_h"] + PLAYBOOK["evacuate"]["lead_h"], v, ll,
                                 f"{haz} buildings in significant/extreme hazard, {m['collapse_possible']} at risk of collapse",
                                 haz))
        if m["isolation"]:
            acts.append(_act("prepare_isolation", m["isolation"]["from_h"] + PLAYBOOK["prepare_isolation"]["lead_h"], v, ll,
                             f"no 4WD route to RN9 from +{m['isolation']['from_h']:.1f} h for {m['isolation']['hours']:.1f} h"))
        if m["facilities_affected"]["school"] or (m["isolation"] and (b[b["village"] == v]["type"] == "school").any()):
            acts.append(_act("schools", t_first + PLAYBOOK["schools"]["lead_h"], v, ll, "school affected or cut off"))
        if m["facilities_affected"]["tourism"] or ("Ben Haddou" in v and m["isolation"]):
            acts.append(_act("tourism", t_first + PLAYBOOK["tourism"]["lead_h"], v, ll,
                             f"{m['facilities_affected']['tourism']} tourism buildings affected"))
    return sorted(acts, key=lambda a: (a["deadline_h"], PRIORITY[a["priority"]]))


def run():
    s = gpd.read_file(PREP / "roads.gpkg")
    b = gpd.read_file(PREP / "buildings.gpkg")
    p = gpd.read_file(PREP / "pois.gpkg")
    places = {r["name"]: r.geometry for _, r in p[(p["kind"] == "place") & p["name"].notna()].iterrows()}
    villages = json.loads((OUT / "villages.json").read_text(encoding="utf8"))
    for name, vt in villages.items():
        seg = json.loads((OUT / f"scenario_{name}.json").read_text(encoding="utf8"))["segments"]
        acts = scenario_actions(name, s, b, places, vt, seg)
        (OUT / f"actions_{name}.json").write_text(json.dumps(acts, ensure_ascii=False), encoding="utf8")
        crit = sum(a["priority"] == "CRITICAL" for a in acts)
        print(f"  {name:5s}: {len(acts):4d} actions ({crit} critical), first deadline "
              f"{acts[0]['deadline_h'] if acts else '-'} h")


if __name__ == "__main__":
    run()
