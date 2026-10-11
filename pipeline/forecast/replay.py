"""Replay / exercise events: past storms run through the same assessment as live forecasts.

Usage: python -m pipeline.forecast.replay
Writes web/public/data/replay/index.json and <event_id>.json (hourly ERA5-Land liquid areal rain x the
areal correction, with GPM IMERG alongside as an independent estimate, and the assessment).
"""

import json

import numpy as np
import pandas as pd

from pipeline import config
from pipeline.data import rainfall as rf
from pipeline.forecast import core

OUT = config.WEB_DATA / "replay"
N_TOP = 8
NAMED = {"2014-11-22": "November 2014 southern Morocco floods (first pulse)"}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    f = core.correction()
    t_e, ll_e, liq = rf.load_era5()
    era = pd.Series((rf.catchment_weights(ll_e)[:, None] * liq).sum(axis=0), index=t_e.tz_localize("UTC"))
    t_i, ll_i, p_i = rf.load_imerg()
    imerg = pd.Series((rf.catchment_weights(ll_i)[:, None] * p_i).sum(axis=0), index=t_i.tz_localize("UTC"))
    imerg = imerg.resample("h").sum()
    events = json.loads((config.INTERIM / "rainfall" / "events.json").read_text(encoding="utf8"))[:N_TOP]
    index = []
    for ev in events:
        end = pd.Timestamp(ev["end"])
        start, stop = end - pd.Timedelta(days=4), end + pd.Timedelta(days=2)
        series = era[start:stop] * f
        antecedent = float(era[start - pd.Timedelta(days=5):start].sum() * f)
        a = core.assess(series, antecedent)
        ev_id = end.strftime("%Y%m%d")
        im = imerg[start:stop] if start >= imerg.index[0] else None
        rec = {"id": ev_id, "title": NAMED.get(end.strftime("%Y-%m-%d"), f"Storm of {end:%d %B %Y}"),
               "source": "ERA5-Land hourly (liquid, x areal correction); GPM IMERG V07 raw for comparison",
               "correction_factor": f, "assessment": a,
               "hourly": {"time": [t.isoformat() for t in series.index], "era5": np.round(series.values, 2).tolist(),
                          "imerg_raw": np.round(im.reindex(series.index).fillna(0).values, 2).tolist() if im is not None else None}}
        (OUT / f"{ev_id}.json").write_text(json.dumps(rec), encoding="utf8")
        index.append({"id": ev_id, "title": rec["title"], "date": end.strftime("%Y-%m-%d"),
                      "p24_mm": a["p24_mm"], "p24_equivalent_mm": a["p24_equivalent_mm"], "scenario": a["scenario"],
                      "imerg_24h_mm": ev.get("imerg_areal_24h_mm")})
        print(f"  {end:%Y-%m-%d}: P24 {a['p24_mm']:5.1f} mm, AMC {a['amc']} -> equiv {a['p24_equivalent_mm']:5.1f} "
              f"-> {a['scenario']} | IMERG raw {ev.get('imerg_areal_24h_mm')}")
    (OUT / "index.json").write_text(json.dumps(sorted(index, key=lambda x: x["date"], reverse=True), ensure_ascii=False,
                                               indent=1), encoding="utf8")


if __name__ == "__main__":
    run()
