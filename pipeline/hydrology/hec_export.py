"""Export the basin model to an HEC-HMS 4.x project for an independent cross-check.

Usage: python -m pipeline.hydrology.hec_export    (after pipeline.hydrology.scenarios)

Writes hec/hms/Ounila/:
  Ounila.hms, Ounila.basin, Ounila.control, Ounila.gage, T10_central.met, T100_central.met
  parameters_subbasins.csv, parameters_reaches.csv   - every value, for manual entry if a file won't load
  hyetograph_T10_central.csv, hyetograph_T100_central.csv - 15 min incremental rain to paste into the gages
  expected_results.csv                               - this engine's peaks for the same runs
The gage tables are stored in DSS by HEC-HMS itself: paste the hyetograph CSV into each gage
(Time-Series Data > Table) as described in README.md.
"""

import csv
import json
import re
import unicodedata

import numpy as np

from pipeline import config
from pipeline.hydrology import hms
from pipeline.hydrology.scenarios import OUT as RUNS

HMS_DIR = config.HEC / "hms" / "Ounila"
VERSION = "4.12"
STORMS = ("10", "100")
START = "01Jan2000, 00:00"
END = "03Jan2000, 00:00"


def _ascii(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9 ]", "", s).strip()


def element_names(basin):
    return {sb.id: {"sb": f"SB{sb.id:02d} {_ascii(sb.name)}", "j": f"J{sb.id:02d} {_ascii(sb.name)}",
                    "r": f"R{sb.id:02d} {_ascii(sb.name)}"} for sb in basin}


def write_basin(basin, names, xy):
    lines = [f"Basin: Ounila", "     Description: Ounila at Ait Ben Haddou, exported by the Atlas pipeline",
             f"     Version: {VERSION}", "     Filepath Separator: \\", "     Unit System: Metric",
             "     Missing Flow To Zero: No", "     Enable Flow Ratio: No",
             "     Compute Local Flow At Junctions: No", "End:", ""]
    for sb in sorted(basin, key=lambda s: s.id):
        x, y = xy[sb.id]
        n = names[sb.id]
        lines += [f"Subbasin: {n['sb']}", f"     Canvas X: {x - 400:.1f}", f"     Canvas Y: {y + 400:.1f}",
                  f"     Area: {sb.area_km2:.3f}", f"     Downstream: {n['j']}", "",
                  "     Canopy: None", "     Surface: None", "     LossRate: SCS", "     Percent Impervious Area: 0.0",
                  f"     Curve Number: {sb.cn:.1f}", "",
                  "     Transform: Clark", f"     Time of Concentration: {sb.tc_h:.3f}",
                  f"     Storage Coefficient: {sb.r_h:.3f}", "", "     Baseflow: None", "End:", ""]
        lines += [f"Junction: {n['j']}", f"     Canvas X: {x:.1f}", f"     Canvas Y: {y:.1f}",
                  f"     Downstream: {n['r'] if sb.downstream else 'Outlet'}", "End:", ""]
        if sb.downstream:
            dx, dy = xy[sb.downstream]
            r = sb.reach
            lines += [f"Reach: {n['r']}", f"     Canvas X: {dx:.1f}", f"     Canvas Y: {dy:.1f}",
                      f"     From Canvas X: {x:.1f}", f"     From Canvas Y: {y:.1f}",
                      f"     Downstream: {names[sb.downstream]['j']}", "",
                      "     Route: Muskingum Cunge", "     Channel Loss: None", "     Channel: Rectangle",
                      f"     Length: {r['length_m']:.1f}", f"     Energy Slope: {r['slope']:.5f}",
                      f"     Mannings n: {r['n']:.3f}", f"     Width: {r['width_m']:.1f}",
                      "     Space-Time Method: Automatic DX and DT", "End:", ""]
    ox, oy = xy[1]
    lines += ["Sink: Outlet", f"     Canvas X: {ox:.1f}", f"     Canvas Y: {oy - 800:.1f}", "End:", ""]
    (HMS_DIR / "Ounila.basin").write_text("\n".join(lines), encoding="ascii")


def write_project(basin, names):
    (HMS_DIR / "Ounila.hms").write_text("\n".join([
        "Project: Ounila", "     Description: Atlas v2 cross-check of the Python HMS-equivalent engine",
        f"     Version: {VERSION}", "     Filepath Separator: \\", "     DSS File Name: Ounila.dss",
        "     Time Zone ID: UTC", "     Time Zone GMT Offset: 0", "End:", "",
        "Basin: Ounila", "     Filename: Ounila.basin", "End:", ""] +
        sum([[f"Precipitation: T{T}_central", f"     Filename: T{T}_central.met", "End:", ""] for T in STORMS], []) +
        ["Control: Design_48h", "     FileName: Ounila.control", "End:", ""]), encoding="ascii")
    (HMS_DIR / "Ounila.control").write_text("\n".join([
        "Control: Design_48h", "     Description: 48 h design run, 5 min step",
        f"     Start Date: {START.split(',')[0]}", f"     Start Time: {START.split(', ')[1]}",
        f"     End Date: {END.split(',')[0]}", f"     End Time: {END.split(', ')[1]}",
        "     Time Interval: 5", "End:", ""]), encoding="ascii")
    gages = ["Gage Manager: Ounila", f"     Version: {VERSION}", "     Filepath Separator: \\", "End:", ""]
    for T in STORMS:
        gages += [f"Gage: T{T}_central", "     Gage Type: Precipitation", "     Precipitation Type: Incremental",
                  "     Units: MM", "     Data Source Type: Manual Entry", "     Local to Project: Yes",
                  f"     Start Time: {START}", f"     End Time: {END}", "     DSS File: Ounila.dss",
                  f"     Pathname: /OUNILA/T{T}_CENTRAL/PRECIP-INC//15MIN/DESIGN/", "End:", ""]
    (HMS_DIR / "Ounila.gage").write_text("\n".join(gages), encoding="ascii")
    for T in STORMS:
        met = [f"Meteorology: T{T}_central", f"     Description: T{T} central design storm (outlet storm area)",
               f"     Version: {VERSION}", "     Unit System: Metric", "     Set Missing Data to Default: Yes",
               "     Precipitation Method: Specified Hyetograph", "     Air Temperature Method: None",
               "     Evapotranspiration Method: No Evapotranspiration", "     Snowmelt Method: None",
               "     Use Basin Model: Ounila", "End:", "", "Precip Method Parameters: Specified Hyetograph", "End:", ""]
        for sb in sorted(basin, key=lambda s: s.id):
            met += [f"Subbasin: {names[sb.id]['sb']}", f"     Gage: T{T}_central", "End:", ""]
        (HMS_DIR / f"T{T}_central.met").write_text("\n".join(met), encoding="ascii")


def write_tables(basin, names, design):
    with open(HMS_DIR / "parameters_subbasins.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["subbasin", "name", "area_km2", "curve_number", "initial_abstraction", "tc_h", "storage_coefficient_h",
                    "downstream_junction", "tc_kirpich_h", "tc_giandotti_h", "tc_temez_h"])
        for sb in sorted(basin, key=lambda s: s.id):
            t = sb.tc_formulas_h
            w.writerow([names[sb.id]["sb"], sb.name, round(sb.area_km2, 3), sb.cn, "blank (=0.2 S)", round(sb.tc_h, 3),
                        round(sb.r_h, 3), names[sb.id]["j"], t["kirpich"], t["giandotti"], t["temez"]])
    with open(HMS_DIR / "parameters_reaches.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["reach", "from_junction", "to_junction", "method", "length_m", "energy_slope", "mannings_n",
                    "shape", "width_m"])
        for sb in sorted(basin, key=lambda s: s.id):
            if sb.downstream:
                r = sb.reach
                w.writerow([names[sb.id]["r"], names[sb.id]["j"], names[sb.downstream]["j"], "Muskingum-Cunge",
                            round(r["length_m"], 1), round(r["slope"], 5), r["n"], "Rectangle", round(r["width_m"], 1)])
    dt = design["meta"]["stored_dt_min"]
    for T in STORMS:
        rain = design["results"]["central"][T]["outlet_storm_rain_mm"]
        with open(HMS_DIR / f"hyetograph_T{T}_central.csv", "w", newline="", encoding="utf8") as f:
            w = csv.writer(f)
            w.writerow(["minutes_from_start", "incremental_mm"])
            for i, v in enumerate(rain):
                w.writerow([(i + 1) * dt, v])
    with open(HMS_DIR / "expected_results.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["element", "storm", "peak_m3s", "time_to_peak_h", "volume_hm3"])
        for T in STORMS:
            res = design["results"]["central"][T]["outlet_storm"]
            for sb in sorted(basin, key=lambda s: s.id):
                r = res[str(sb.id)]
                w.writerow([names[sb.id]["j"], f"T{T}_central", r["peak_m3s"], r["time_to_peak_h"], r["volume_hm3"]])


def run():
    HMS_DIR.mkdir(parents=True, exist_ok=True)
    basin = hms.load_basin()
    names = element_names(basin)
    model = json.loads((config.INTERIM / "basin_model.json").read_text(encoding="utf8"))
    xy = {sb["id"]: tuple(sb["outlet_xy"]) for sb in model["subbasins"]}
    design = json.loads((RUNS / "design.json").read_text(encoding="utf8"))
    write_basin(basin, names, xy)
    write_project(basin, names)
    write_tables(basin, names, design)
    print(f"  HEC-HMS project -> {HMS_DIR}")


if __name__ == "__main__":
    run()
