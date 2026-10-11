"""Live forecast: Open-Meteo (ECMWF IFS, GFS, ICON + ECMWF ENS 51 members) -> alert + matched scenario.

Usage: python -m pipeline.forecast.live [--meta web/public/data/meta.json]
       (--meta: run from the published bundle only - numpy, pandas, requests - as the 6-hourly
        GitHub Actions job does; without it the pipeline outputs in data/ are used)
Writes web/public/data/forecast/latest.json and forecast/archive/<issued>.json.
The browser runs the same logic live (web/src/model/forecast.ts); this file is the server-side copy and
the archive for later verification.
"""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from pipeline import config
from pipeline.forecast import core

UA = {"User-Agent": "Atlas-flood-DSS/2.0 (MSc Geomatics research prototype)"}
MODELS = {"ecmwf_ifs025": "ECMWF IFS", "gfs_seamless": "NOAA GFS", "icon_seamless": "DWD ICON"}
REFERENCE = "ecmwf_ifs025"
OUT = config.WEB_DATA / "forecast"


def points():
    """The ERA5-Land cell centres over the catchment and their areal weights (same as the design rain)."""
    if "rain_points" in core._CTX:
        pts = np.array(core._CTX["rain_points"])
        return pts[:, :2], pts[:, 2] / pts[:, 2].sum()
    from pipeline.data import rainfall
    d = np.load(config.RAW / "era5land_hourly.npz")
    w = rainfall.catchment_weights(d["lonlat"])
    keep = w > 0
    return d["lonlat"][keep], w[keep] / w[keep].sum()


def _areal(per_point, weights):
    return sum(w * s for w, s in zip(weights, per_point))


def fetch(lonlat, weights):
    lat = ",".join(f"{p[1]:.3f}" for p in lonlat)
    lon = ",".join(f"{p[0]:.3f}" for p in lonlat)
    f = requests.get("https://api.open-meteo.com/v1/forecast", headers=UA, timeout=120, params={
        "latitude": lat, "longitude": lon, "hourly": "rain,showers,snowfall", "models": ",".join(MODELS),
        "past_days": 5, "forecast_days": 7, "timezone": "UTC"}).json()
    e = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", headers=UA, timeout=120, params={
        "latitude": lat, "longitude": lon, "hourly": "precipitation,snowfall", "models": "ecmwf_ifs025",
        "forecast_days": 7, "timezone": "UTC"}).json()
    f, e = (x if isinstance(x, list) else [x] for x in (f, e))
    t = pd.DatetimeIndex(f[0]["hourly"]["time"], tz="UTC")
    det = {}
    for m in MODELS:
        series = [np.nan_to_num(np.array(p["hourly"][f"rain_{m}"], dtype=float)) +
                  np.nan_to_num(np.array(p["hourly"][f"showers_{m}"], dtype=float)) for p in f]
        det[m] = pd.Series(_areal(series, weights), index=t)
    te = pd.DatetimeIndex(e[0]["hourly"]["time"], tz="UTC")
    members = []
    keys = [k for k in e[0]["hourly"] if k.startswith("precipitation")]
    for k in keys:
        sk = k.replace("precipitation", "snowfall")
        series = [np.clip(np.nan_to_num(np.array(p["hourly"][k], dtype=float)) -
                          np.nan_to_num(np.array(p["hourly"].get(sk, [0] * len(te)), dtype=float)) * 10 / 7, 0, None)
                  for p in e]                                     # Open-Meteo snowfall cm -> mm w.e.: x 10/7
        members.append(pd.Series(_areal(series, weights), index=te))
    return det, members


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "archive").mkdir(exist_ok=True)
    lonlat, weights = points()
    det, members = fetch(lonlat, weights)
    f = core.correction()
    now = pd.Timestamp(datetime.now(timezone.utc)).floor("h")
    ref_past = det[REFERENCE][det[REFERENCE].index < now]
    antecedent = float(ref_past.tail(120).sum() * f)
    assess = {m: core.assess(s[s.index >= now] * f, antecedent) for m, s in det.items()}
    ens = [core.assess(s[s.index >= now] * f, antecedent) for s in members]
    al = core.alert(assess[REFERENCE], ens)
    fut = {m: s[s.index >= now] * f for m, s in det.items()}
    ens_mat = np.array([s[s.index >= now].values * f for s in members])
    out = {
        "issued": now.isoformat(), "source": "Open-Meteo: ECMWF IFS 0.25, NOAA GFS, DWD ICON; ECMWF ENS (51)",
        "correction_factor": f, "antecedent_5d_mm": round(antecedent, 1), "alert": al,
        "deterministic": {MODELS[m]: a for m, a in assess.items()}, "reference_model": MODELS[REFERENCE],
        "ensemble_p24_equivalent_mm": sorted(m["p24_equivalent_mm"] for m in ens),
        "hourly": {"time": [t.isoformat() for t in fut[REFERENCE].index],
                   **{MODELS[m]: np.round(s.values, 2).tolist() for m, s in fut.items()},
                   "ens_p10": np.round(np.percentile(ens_mat, 10, axis=0), 2).tolist(),
                   "ens_p50": np.round(np.percentile(ens_mat, 50, axis=0), 2).tolist(),
                   "ens_p90": np.round(np.percentile(ens_mat, 90, axis=0), 2).tolist()},
    }
    (OUT / "latest.json").write_text(json.dumps(out, indent=1), encoding="utf8")
    (OUT / "archive" / f"{now.strftime('%Y%m%dT%H')}.json").write_text(json.dumps(out), encoding="utf8")
    r = assess[REFERENCE]
    print(f"  {now:%Y-%m-%d %H}Z alert {al['level'].upper()} | {MODELS[REFERENCE]} P24 {r['p24_mm']} mm "
          f"(AMC {r['amc']}, equiv {r['p24_equivalent_mm']}) -> {r['scenario']} | ensemble P(T2) "
          f"{al['probabilities'].get('T2')}, P(T10) {al['probabilities'].get('T10')}")


if __name__ == "__main__":
    import sys
    if "--meta" in sys.argv:
        core.use_meta(sys.argv[sys.argv.index("--meta") + 1])
    run()
