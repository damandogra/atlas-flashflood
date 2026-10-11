"""Design storms on the HMS computation step, depth-area adjusted to a storm area."""

import json

import numpy as np

from pipeline import config
from pipeline.data import rainfall
from pipeline.hydrology.hms import DT_S, SIM_HOURS

_IDF = None


def idf():
    global _IDF
    if _IDF is None:
        _IDF = json.loads((config.INTERIM / "rainfall" / "idf.json").read_text(encoding="utf8"))
    return _IDF


def depth_table(T, level, area_km2):
    """Depths (mm) for idf durations at return period T, interpolated in log(area) between the
    ERA5 cell scale (~106 km2) and the whole catchment (731 km2). Smaller areas take the cell value."""
    d = idf()
    j = d["return_periods"].index(T)
    cell, catch = d["scales"]["cell"], d["scales"]["catchment"]
    dc = np.array(cell[f"depth_mm_{level}"])[:, j]
    dk = np.array(catch[f"depth_mm_{level}"])[:, j]
    a0, a1 = cell["area_km2"], catch["area_km2"]
    w = np.clip((np.log(area_km2) - np.log(a0)) / (np.log(a1) - np.log(a0)), 0.0, 1.0)
    return (1 - w) * dc + w * dk


def design_hyetograph(T, level="central", area_km2=731.0):
    """Incremental rainfall (mm) per DT_S step over SIM_HOURS; 24 h alternating-block storm first."""
    storm15 = rainfall.alternating_block(rainfall.depth_duration(depth_table(T, level, area_km2)))
    sub = rainfall.STORM_DT_MIN * 60 // DT_S
    storm = np.repeat(storm15 / sub, sub)
    out = np.zeros(SIM_HOURS * 3600 // DT_S)
    out[:len(storm)] = storm
    return out


def hyetograph_for_depth(p24_mm, area_km2=731.0):
    """Design-shaped storm scaled to a given 24 h depth (the IMERG duration ratios are the same for
    every return period, so one shape fits all depths). Used for the rainfall sweep of the 2D library."""
    base = depth_table(100, "central", area_km2)
    depths = base * p24_mm / base[rainfall.DURATIONS_H.index(24)]
    storm15 = rainfall.alternating_block(rainfall.depth_duration(depths))
    sub = rainfall.STORM_DT_MIN * 60 // DT_S
    out = np.zeros(SIM_HOURS * 3600 // DT_S)
    out[:len(storm15) * sub] = np.repeat(storm15 / sub, sub)
    return out
