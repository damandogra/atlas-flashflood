"""Rainfall analysis: areal series, gauge bias, storm shape, IDF curves, design storms, event catalogue.

Usage: python -m pipeline.data.rainfall      (after `download rain imerg`)

How the design rainfall is built (each piece from the data source best suited to it):
  magnitude   ERA5-Land hourly 1950-2025 (76 years), liquid only (total - snowfall)
              -> GEV (L-moments) of 24 h / 48 h annual maxima
  correction  Ouarzazate gauge / gridded product at the gauge (point bias)  x  point-to-cell ARF
  shape       GPM IMERG V07 half-hourly 1998-2025 -> measured ratio of mean annual-max D-hour depth
              to 24 h depth on the catchment cells (D = 1..12 h), applied directly to the 24 h depth
ERA5's own sub-daily structure is too flat (convective bursts smeared over ~11 km and 1 h), so it is
only used for the 24 h and 48 h magnitudes.

Inputs : data/raw/era5land_hourly.npz, imerg_halfhourly.npz, ghcn_MO000060265.csv.gz
Outputs: data/interim/rainfall/idf.json, design_storms.json, events.json, annual_maxima.csv
"""

import json
from math import gamma, log

import ee
import numpy as np
import pandas as pd
from pyproj import Transformer

from pipeline import config, grid

OUT = config.INTERIM / "rainfall"
OUT.mkdir(exist_ok=True)

DURATIONS_H = [1, 2, 3, 6, 12, 24, 48]
SHAPE_DURATIONS_H = [1, 2, 3, 6, 12, 24]
RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 200, 500]
LEVELS = ("low", "central", "high")
STATION = {"id": "MO000060265", "name": "Ouarzazate", "lon": -6.90, "lat": 30.93}
MIN_YEAR_DAYS = 330          # gauge year counted only if this complete
BELL_RATIOS = {15: 0.57, 30: 0.79, 60: 1.0}   # sub-hourly depth / 1 h depth (Bell 1969)
STORM_HOURS, STORM_DT_MIN = 24, 15
BOOTSTRAP = 500

# A gauge measures a point; the gridded products average ~106 km2. Part of the gauge/product ratio is
# this point-to-area effect, which must not be applied to areal design rainfall. Literature 24 h ARFs
# for ~100 km2 are ~0.9 in temperate climates and lower for convective semi-arid storms. ASSUMPTION,
# to be constrained in Phase 2 against regional flood envelopes and the Nov 2014 event.
ARF_POINT_TO_CELL = 0.85
ARF_POINT_TO_CELL_RANGE = (0.75, 0.95)


# --- GEV by L-moments (Hosking 1990) -----------------------------------------------

def gev_lmom(x):
    """Return (xi, alpha, k) in Hosking's parameterisation, x(F) = xi + alpha/k * (1 - (-ln F)^k)."""
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    i = np.arange(1, n + 1)
    b0 = x.mean()
    b1 = np.sum((i - 1) / (n - 1) * x) / n
    b2 = np.sum((i - 1) * (i - 2) / ((n - 1) * (n - 2)) * x) / n
    l1, l2, l3 = b0, 2 * b1 - b0, 6 * b2 - 6 * b1 + b0
    t3 = l3 / l2
    c = 2 / (3 + t3) - log(2) / log(3)
    k = 7.8590 * c + 2.9554 * c ** 2
    alpha = l2 * k / ((1 - 2 ** -k) * gamma(1 + k))
    xi = l1 - alpha * (1 - gamma(1 + k)) / k
    return xi, alpha, k


def gev_quantile(params, T):
    xi, alpha, k = params
    y = -np.log(1 - 1 / np.asarray(T, dtype=float))
    return xi + alpha / k * (1 - y ** k)


def fit_with_ci(annual_max, rng):
    q = gev_quantile(gev_lmom(annual_max), RETURN_PERIODS)
    boots = np.array([gev_quantile(gev_lmom(rng.choice(annual_max, len(annual_max))), RETURN_PERIODS)
                      for _ in range(BOOTSTRAP)])
    return q, np.percentile(boots, 5, axis=0), np.percentile(boots, 95, axis=0)


# --- inputs --------------------------------------------------------------------------

def _load(name):
    d = np.load(config.RAW / name)
    return pd.DatetimeIndex(d["time"]), d["lonlat"], np.nan_to_num(d["precip_mm"])


def load_era5(liquid=True):
    """ERA5-Land hourly. liquid=True removes snowfall: snow does not produce flash-flood runoff
    (it melts over days), and the catchment reaches 3600 m."""
    index, lonlat, precip = _load("era5land_hourly.npz")
    if liquid:
        precip = np.clip(precip - np.nan_to_num(np.load(config.RAW / "era5land_hourly.npz")["snow_mm"]), 0, None)
    return index, lonlat, precip


def load_imerg():
    return _load("imerg_halfhourly.npz")


def catchment_weights(lonlat):
    """Share of catchment model cells nearest to each 0.1 deg cell centre (Thiessen weights)."""
    catch = grid.read(config.INTERIM / "catchment.tif").astype(bool)
    transform, _, _ = grid.model_grid()
    rows, cols = np.nonzero(catch)
    xs, ys = transform * (cols + 0.5, rows + 0.5)
    px, py = Transformer.from_crs(config.CRS_WEB, config.CRS_WORK, always_xy=True).transform(lonlat[:, 0], lonlat[:, 1])
    nearest = np.argmin((xs[:, None] - px[None]) ** 2 + (ys[:, None] - py[None]) ** 2, axis=1)
    return np.bincount(nearest, minlength=len(lonlat)) / len(nearest)


def _gauge():
    st = pd.read_csv(config.RAW / f"ghcn_{STATION['id']}.csv.gz", header=None,
                     names=["id", "date", "el", "val", "m", "q", "s", "t"])
    st = st[(st.el == "PRCP") & st.q.isna()]
    st = pd.Series(st.val.values / 10.0, index=pd.to_datetime(st.date.astype(str)))
    ok_years = st.groupby(st.index.year).size().loc[lambda s: s >= MIN_YEAR_DAYS].index
    return st, ok_years


def _ee_point_cache(name, collection, band, years, to_mm, chunk_years):
    """Series at the gauge location from Earth Engine, cached as CSV (time_ms, mm)."""
    cache = config.RAW / name
    if not cache.exists():
        ee.Initialize(project=config.EE_PROJECT)
        point = ee.Geometry.Point([STATION["lon"], STATION["lat"]])
        rows = []
        for y0 in range(years[0], years[1], chunk_years):   # chunked: EE memory limits
            rows += (ee.ImageCollection(collection)
                     .filterDate(f"{y0}-01-01", f"{min(y0 + chunk_years, years[1])}-01-01")
                     .select(band).getRegion(point, 11132).getInfo())[1:]
        pd.DataFrame({"time_ms": [r[3] for r in rows],
                      "mm": [max(r[4] or 0, 0) * to_mm for r in rows]}).to_csv(cache, index=False)
    d = pd.read_csv(cache)
    return pd.Series(d.mm.values, index=pd.to_datetime(d.time_ms, unit="ms")).sort_index()


def gauge_check(rng):
    """Point bias: mean annual-max daily rainfall, Ouarzazate gauge / gridded product at the gauge."""
    st, ok_years = _gauge()
    era = _ee_point_cache("era5land_daily_ouarzazate.csv", "ECMWF/ERA5_LAND/DAILY_AGGR",
                          "total_precipitation_sum", (1973, 2026), 1000.0, 5)
    imerg = _ee_point_cache("imerg_halfhourly_ouarzazate.csv", "NASA/GPM_L3/IMERG_V07",
                            "precipitation", (1998, 2026), 0.5, 1).resample("D").sum()

    def annual_max(series, years):
        return series[series.index.year.isin(years)].groupby(lambda d: d.year).max()

    years = [y for y in ok_years if y in set(era.index.year)]
    g, e = annual_max(st, years), annual_max(era, years)
    boots = []
    for _ in range(BOOTSTRAP):
        yy = rng.choice(years, len(years))
        boots.append(g.loc[yy].mean() / e.loc[yy].mean())
    years_im = [y for y in years if y >= 1998]
    g_im, i_im, e_im = annual_max(st, years_im), annual_max(imerg, years_im), annual_max(era, years_im)
    return {
        "station": STATION, "years": [int(y) for y in years], "n_years": len(years),
        "gauge_mean_annual_max_mm": round(float(g.mean()), 1),
        "era5_mean_annual_max_mm": round(float(e.mean()), 1),
        "point_factor": round(float(g.mean() / e.mean()), 3),
        "point_factor_p5": round(float(np.percentile(boots, 5)), 3),
        "point_factor_p95": round(float(np.percentile(boots, 95)), 3),
        "imerg_check": {   # independent product; only the years where the gauge is complete
            "years": [int(y) for y in years_im],
            "gauge_mm": round(float(g_im.mean()), 1), "imerg_mm": round(float(i_im.mean()), 1),
            "era5_mm": round(float(e_im.mean()), 1),
        },
    }


def storm_shape(rng):
    """Storm shape from IMERG: ratio of mean annual-max D-hour depth to mean annual-max 24 h depth,
    median over catchment cells, for D in SHAPE_DURATIONS_H. Bootstrap over years for per-duration CIs.
    A Montana exponent b (fit through the 24 h point) is reported as a one-number summary only."""
    t_im, lonlat_im, p_im = load_imerg()
    t_er, _, p_er = load_era5()
    cells = np.nonzero(catchment_weights(lonlat_im) > 0)[0]
    years = np.arange(t_im.year.min(), t_im.year.max() + 1)

    def cell_am(series, index, steps_per_h):
        s = pd.Series(series, index=index)
        return np.array([s.rolling(d * steps_per_h).sum().groupby(index.year).max().reindex(years).values
                         for d in SHAPE_DURATIONS_H])                          # [duration, year]

    am_im = np.array([cell_am(p_im[c], t_im, 2) for c in cells])                # [cell, duration, year]
    sel = t_er.year >= years[0]
    am_er = np.array([cell_am(p_er[c][sel], t_er[sel], 1) for c in cells])

    def ratios(am, yidx):
        return np.median(np.nanmean(am[:, :, yidx], axis=2) / np.nanmean(am[:, -1:, yidx], axis=2), axis=0)

    def montana_b(r):   # least squares through (24 h, 1): log r = (1 - b) log(D/24)
        x = np.log(np.array(SHAPE_DURATIONS_H[:-1]) / 24)
        return 1 - np.sum(x * np.log(r[:-1])) / np.sum(x * x)

    all_years = np.arange(len(years))
    r = ratios(am_im, all_years)
    boots = np.array([ratios(am_im, rng.choice(all_years, len(all_years))) for _ in range(BOOTSTRAP)])
    r_era = ratios(am_er, all_years)
    return {"source": f"GPM IMERG V07 half-hourly, {years[0]}-{years[-1]}, {len(cells)} catchment cells",
            "durations_h": SHAPE_DURATIONS_H,
            "imerg_ratio_to_24h": np.round(r, 3).tolist(),
            "imerg_ratio_p5": np.round(np.percentile(boots, 5, axis=0), 3).tolist(),
            "imerg_ratio_p95": np.round(np.percentile(boots, 95, axis=0), 3).tolist(),
            "era5_ratio_to_24h": np.round(r_era, 3).tolist(),
            "montana_b_summary": round(float(montana_b(r)), 3), "era5_montana_b": round(float(montana_b(r_era)), 3)}


# --- analysis -------------------------------------------------------------------------

def annual_maxima(series, index):
    """Annual maxima of running D-hour totals for each duration. series: (n_hours,)"""
    s = pd.Series(series, index=index)
    return {d: s.rolling(d, min_periods=d).sum().groupby(index.year).max().values for d in DURATIONS_H}


def subdaily(depth_24, ratio_to_24h):
    """Depths for the DURATIONS_H up to 24 h: the 24 h depth times the measured IMERG ratios."""
    return depth_24 * np.asarray(ratio_to_24h)


def alternating_block(depth_by_minutes):
    """24 h alternating-block hyetograph at STORM_DT_MIN steps from a depth-duration function."""
    n = STORM_HOURS * 60 // STORM_DT_MIN
    cum = np.array([depth_by_minutes((i + 1) * STORM_DT_MIN) for i in range(n)])
    blocks = np.diff(np.concatenate([[0.0], cum]))
    centre = n // 2
    # largest block in the centre, then alternate right / left; drop positions past either end
    order = [centre]
    for offset in range(1, n):
        order += [p for p in (centre + offset, centre - offset) if 0 <= p < n]
    hyeto = np.zeros(n)
    hyeto[np.array(order[:n])] = np.sort(blocks)[::-1]
    return hyeto


def depth_duration(idf_depths):
    """Interpolate depth (mm) for any duration in minutes, log-log between IDF durations,
    with Bell (1969) ratios below 1 hour."""
    d_min = np.array([d * 60 for d in DURATIONS_H], dtype=float)
    depths = np.asarray(idf_depths, dtype=float)

    def f(minutes):
        if minutes < 60:
            lo = max(m for m in BELL_RATIOS if m <= max(minutes, 15))
            hi = min(m for m in BELL_RATIOS if m >= minutes)
            r = BELL_RATIOS[lo] if lo == hi else np.interp(minutes, [lo, hi], [BELL_RATIOS[lo], BELL_RATIOS[hi]])
            return depths[0] * r
        return float(np.exp(np.interp(np.log(minutes), np.log(d_min), np.log(depths))))
    return f


def run():
    rng = np.random.default_rng(42)
    index, lonlat, precip = load_era5()
    w = catchment_weights(lonlat)
    inside = w > 0
    areal = (w[:, None] * precip).sum(axis=0)
    print(f"  {inside.sum()} of {len(w)} ERA5-Land cells overlap the catchment; mean annual areal rain "
          f"{areal.sum() / (len(index) / 8766):.0f} mm")

    gauge = gauge_check(rng)
    shape = storm_shape(rng)
    lo_arf, hi_arf = ARF_POINT_TO_CELL_RANGE
    levels = {   # areal correction applied to ERA5 magnitudes
        "low": round(gauge["point_factor_p5"] * lo_arf, 3),
        "central": round(gauge["point_factor"] * ARF_POINT_TO_CELL, 3),
        "high": round(gauge["point_factor_p95"] * hi_arf, 3),
    }
    shape_levels = {"low": shape["imerg_ratio_p5"], "central": shape["imerg_ratio_to_24h"],
                    "high": shape["imerg_ratio_p95"]}
    f = levels["central"]
    print(f"  point bias (gauge / ERA5, {gauge['n_years']} yrs): {gauge['point_factor']} "
          f"[{gauge['point_factor_p5']}-{gauge['point_factor_p95']}]; IMERG check {gauge['imerg_check']}")
    print(f"  areal correction = point bias x ARF {ARF_POINT_TO_CELL}: {levels}")
    print(f"  storm shape, ratio to 24 h for {SHAPE_DURATIONS_H} h: IMERG {shape['imerg_ratio_to_24h']} "
          f"(p5 {shape['imerg_ratio_p5']}, p95 {shape['imerg_ratio_p95']}); ERA5 {shape['era5_ratio_to_24h']}")

    # GEV of ERA5 24 h and 48 h annual maxima, catchment (areal) and cell scale
    am_areal = annual_maxima(areal, index)
    am_cells = [annual_maxima(precip[i], index) for i in np.nonzero(inside)[0]]
    catchment_km2 = json.loads((config.INTERIM / "basin_model.json").read_text(encoding="utf8"))["catchment_km2"]
    lat = np.radians(lonlat[:, 1].mean())
    cell_km2 = (0.1 * 111.32 * np.cos(lat)) * (0.1 * 110.57)     # 0.1 deg cell
    i24 = DURATIONS_H.index(24)
    idf = {"durations_h": DURATIONS_H, "return_periods": RETURN_PERIODS,
           "years": [int(index.year.min()), int(index.year.max())],
           "gauge": gauge, "storm_shape": shape, "arf_point_to_cell": ARF_POINT_TO_CELL,
           "arf_point_to_cell_range": ARF_POINT_TO_CELL_RANGE,
           "correction_levels": levels, "shape_levels": shape_levels, "scales": {}}
    for scale, am_list in (("catchment", [am_areal]), ("cell", am_cells)):
        raw = {}
        for d in (24, 48):
            fits = [fit_with_ci(am[d], rng) for am in am_list]
            raw[d] = [np.median([x[k] for x in fits], axis=0) for k in range(3)]   # q, ci5, ci95
        entry = {"area_km2": round(catchment_km2 if scale == "catchment" else cell_km2, 1),
                 "era5_raw_24h_mm": np.round(raw[24][0], 1).tolist()}
        for level in LEVELS:
            fl, rl = levels[level], shape_levels[level]
            table = np.vstack([np.array([subdaily(fl * q24, rl) for q24 in raw[24][0]]).T,
                               fl * raw[48][0][None, :]])
            entry[f"depth_mm_{level}"] = np.round(table, 1).tolist()      # [duration][return period]
        entry["depth_mm"] = entry["depth_mm_central"]
        for k, name in ((1, "ci5_mm"), (2, "ci95_mm")):                  # GEV sampling CI, central level
            table = np.vstack([np.array([subdaily(f * q24, shape_levels["central"]) for q24 in raw[24][k]]).T,
                               f * raw[48][k][None, :]])
            entry[name] = np.round(table, 1).tolist()
        native = [np.median([gev_quantile(gev_lmom(am[d]), RETURN_PERIODS) for am in am_list], axis=0)
                  for d in DURATIONS_H]
        entry["era5_native_depth_mm"] = np.round(np.array(native), 1).tolist()   # uncorrected, for comparison
        idf["scales"][scale] = entry
    cell, catch = np.array(idf["scales"]["cell"]["depth_mm"]), np.array(idf["scales"]["catchment"]["depth_mm"])
    idf["arf_catchment_vs_cell"] = np.round(catch[i24] / cell[i24], 3).tolist()
    (OUT / "idf.json").write_text(json.dumps(idf, indent=1), encoding="utf8")

    rows = [{"duration_h": d, **{str(y): v for y, v in zip(range(index.year.min(), index.year.max() + 1),
                                                          np.round(am_areal[d], 1))}} for d in DURATIONS_H]
    pd.DataFrame(rows).set_index("duration_h").T.to_csv(OUT / "annual_maxima.csv")   # raw ERA5 areal

    # design storms per correction level and scale
    storms = {"dt_min": STORM_DT_MIN, "hours": STORM_HOURS, "method": "alternating block, 24 h, centred peak",
              "return_periods": RETURN_PERIODS, "levels": {}}
    for level in LEVELS:
        storms["levels"][level] = {
            scale: {str(T): np.round(alternating_block(depth_duration(
                np.array(idf["scales"][scale][f"depth_mm_{level}"])[:, j])), 3).tolist()
                for j, T in enumerate(RETURN_PERIODS)}
            for scale in ("catchment", "cell")}
    storms["scales"] = storms["levels"]["central"]
    (OUT / "design_storms.json").write_text(json.dumps(storms), encoding="utf8")

    # historical event catalogue: ERA5 areal 24 h maxima, with the independent IMERG estimate
    t_im, lonlat_im, p_im = load_imerg()
    imerg_24 = pd.Series((catchment_weights(lonlat_im)[:, None] * p_im).sum(axis=0), index=t_im).rolling(48).sum()
    s24 = pd.Series(areal, index=index).rolling(24).sum()
    events, used = [], s24.copy()
    for _ in range(25):
        t = used.idxmax()
        win = imerg_24[t - pd.Timedelta(hours=12):t + pd.Timedelta(hours=12)]
        events.append({"end": t.strftime("%Y-%m-%dT%H:00Z"),
                       "era5_areal_24h_mm": round(float(used.max()), 1),
                       "corrected_areal_24h_mm": round(float(used.max() * f), 1),
                       "imerg_areal_24h_mm": round(float(win.max()), 1) if len(win) else None,
                       "era5_peak_1h_mm": round(float(pd.Series(areal, index=index)[t - pd.Timedelta(hours=23):t].max()), 1)})
        used[t - pd.Timedelta(days=5):t + pd.Timedelta(days=5)] = 0
    (OUT / "events.json").write_text(json.dumps(events, indent=1), encoding="utf8")

    for scale in ("catchment", "cell"):
        print(f"  design depths, {scale} scale, central (mm); cols = T{RETURN_PERIODS}")
        for d, row in zip(DURATIONS_H, idf["scales"][scale]["depth_mm"]):
            print(f"    {d:>3} h  " + "  ".join(f"{v:6.1f}" for v in row))
    j100 = RETURN_PERIODS.index(100)
    print("  T100 catchment 24 h | 1 h, low / central / high: " + " / ".join(
        f"{idf['scales']['catchment'][f'depth_mm_{lv}'][i24][j100]} | {idf['scales']['catchment'][f'depth_mm_{lv}'][0][j100]}"
        for lv in LEVELS) + " mm")
    print("  top events, ERA5 corrected | IMERG raw (mm/24 h): " + ", ".join(
        f"{e['end'][:10]} {e['corrected_areal_24h_mm']}|{e['imerg_areal_24h_mm']}" for e in events[:8]))


if __name__ == "__main__":
    run()
