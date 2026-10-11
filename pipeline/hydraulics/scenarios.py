"""2D flood scenario library: domain, hydrology coupling, runs, outputs.

Usage: python -m pipeline.hydraulics.scenarios [scenario ...]     (default: the whole library)

Domain: valley corridors - catchment cells within 1050 m of a channel draining >= 2 km2 and at most
20 m above the nearest drainage (HAND) - plus a 2 km extension downstream of Ait Ben Haddou so the outflow boundary
does not affect the ksar. Hillslopes stay in the hydrology model: each sub-basin's local HMS
hydrograph enters the 2D domain spread over the cells where its hillslopes drain (D8). Routing
between sub-basins is done by the 2D solver, not Muskingum-Cunge.

Outputs per scenario in data/runs/hydraulics/<name>/:
  hmax.tif, vmax.tif, hvmax.tif (max of d*(v+0.5)), t_arrival_01.tif, t_arrival_03.tif (h from storm
  start, -1 = never), duration_03.tif (h), snaps.npz (depth every 30 min on active cells), run.json
"""

import heapq
import json
import sys
import time

import numpy as np
from scipy import ndimage

from pipeline import config, grid
from pipeline.data import rainfall as rf
from pipeline.hydraulics import lisflood2d as lf
from pipeline.hydrology import hms, storms

OUT = config.RUNS / "hydraulics"
CHANNEL_KM2, CORRIDOR_CELLS, HAND_MAX = 2.0, 35, 20.0      # 1050 m corridor, limited by HAND
EXT_CELLS = 70                    # downstream extension below the outlet (2.1 km)
SIM_T1_H = 36.0
DIRMAP = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}

# Library: design return periods (central rainfall) + a sweep of 24 h depths for forecast matching
SWEEP_MM = (20, 25, 120, 140, 160)


def library():
    idf = storms.idf()
    i24, j = rf.DURATIONS_H.index(24), {T: k for k, T in enumerate(rf.RETURN_PERIODS)}
    lib = {f"T{T}": float(idf["scales"]["catchment"]["depth_mm"][i24][j[T]]) for T in rf.RETURN_PERIODS}
    lib.update({f"P{p}": float(p) for p in SWEEP_MM})
    return dict(sorted(lib.items(), key=lambda kv: kv[1]))


def build_domain():
    acc = grid.read(config.INTERIM / "acc_km2.tif")
    hand = grid.read(config.INTERIM / "hand.tif")
    catch = grid.read(config.INTERIM / "catchment.tif").astype(bool)
    z = grid.read(config.RAW / "dem.tif").astype(np.float64)       # raw DEM: channels are carved below
    fd = grid.read(config.INTERIM / "fdir.tif")
    nman = grid.read(config.INTERIM / "manning.tif").astype(np.float64)
    nr, nc = catch.shape

    near = ndimage.binary_dilation(acc >= CHANNEL_KM2, iterations=CORRIDOR_CELLS)
    active = catch & near & (hand >= 0) & (hand <= HAND_MAX)
    z, active = carve_flow_paths(z, fd, acc, active)

    # downstream extension along the D8 path from the outlet cell
    r, c = np.unravel_index(np.argmax(np.where(catch, acc, -1)), acc.shape)
    outlet_rc = (r, c)
    path = []
    for _ in range(EXT_CELLS):
        dr, dc = DIRMAP.get(int(fd[r, c]), (0, 0))
        if not (dr or dc):
            break
        r, c = r + dr, c + dc
        path.append((r, c))
    ext = np.zeros_like(active)
    ext_r = 10                                            # 300 m either side of the downstream path
    rr, cc = np.mgrid[-ext_r:ext_r + 1, -ext_r:ext_r + 1]
    disk = np.hypot(rr, cc) <= ext_r
    for (pr, pc) in path:
        sub = (slice(pr - ext_r, pr + ext_r + 1), slice(pc - ext_r, pc + ext_r + 1))
        ext[sub] |= disk & (z[sub] - z[pr, pc] <= HAND_MAX)
    active |= ext & ~catch

    lab, _ = ndimage.label(active)                        # keep the component connected to the outlet
    active = lab == lab[outlet_rc]

    # outflow line: extension cells near the last path cell and within 5 m of its elevation
    pr, pc = path[-1]
    s_end = max((z[path[-10]] - z[pr, pc]) / (9 * config.GRID_RES_M), 1e-3)
    out_rc = [(r, c) for (r, c) in zip(*np.nonzero(active & ext))
              if np.hypot(r - pr, c - pc) <= 3 and z[r, c] - z[pr, pc] <= 5]
    # every active cell must drain to the outflow line through 4-connected faces
    z2d = fill_4conn(z, active, out_rc)
    fill = (z2d - z)[active]
    dom = lf.build(active, z2d, nman)
    out_cells = [dom["idx"][r, c] for (r, c) in out_rc]
    dom.update(active=active, outlet_rc=outlet_rc, ext=ext & active, outlets=(out_cells, [s_end] * len(out_cells)),
               fill_stats={"cells_raised": int((fill > 0.01).sum()), "mean_raise_m": round(float(fill[fill > 0.01].mean()), 2)
                           if (fill > 0.01).any() else 0.0, "max_raise_m": round(float(fill.max()), 2)})
    return dom, fd, catch, acc


CARVE_KM2 = 0.25


def carve_flow_paths(z, fd, acc, active):
    """Breach false dams along every D8 path draining >= CARVE_KM2 inside the domain, walking from
    upstream to downstream (increasing drainage) and lowering the receiver so the bed never rises.
    A diagonal D8 step is made 4-connected for the 2D faces by activating and carving the lower of
    the two orthogonal cells between donor and receiver.
    Why breach, not fill: GLO-30 is a radar DSM; narrow gorges carry spurious highs (radar shadow,
    vegetation, bridges) that a fill would turn into artificial reservoirs."""
    z, active = z.copy(), active.copy()
    nr, nc = z.shape
    rows, cols = np.nonzero(active & (acc >= CARVE_KM2))
    for i in np.argsort(acc[rows, cols], kind="stable"):
        r, c = rows[i], cols[i]
        dr, dc = DIRMAP.get(int(fd[r, c]), (0, 0))
        r2, c2 = r + dr, c + dc
        if not (dr or dc) or not (0 <= r2 < nr and 0 <= c2 < nc):
            continue
        if dr and dc and not (active[r, c2] and z[r, c2] <= z[r, c]) and not (active[r2, c] and z[r2, c] <= z[r, c]):
            rm, cm = (r, c2) if z[r, c2] <= z[r2, c] else (r2, c)
            active[rm, cm] = True
            z[rm, cm] = min(z[rm, cm], z[r, c])
        active[r2, c2] = active[r2, c2] or active[r, c]
        z[r2, c2] = min(z[r2, c2], z[r, c])
    return z, active


def fill_4conn(z, active, seeds):
    """Priority-flood depression filling (Barnes et al. 2014) restricted to the active domain with
    4-connectivity, seeded at the outflow cells."""
    zf = z.copy()
    done = ~active
    heap = []
    for r, c in seeds:
        heapq.heappush(heap, (zf[r, c], r, c))
        done[r, c] = True
    nr, nc = z.shape
    while heap:
        e, r, c = heapq.heappop(heap)
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            r2, c2 = r + dr, c + dc
            if 0 <= r2 < nr and 0 <= c2 < nc and not done[r2, c2]:
                done[r2, c2] = True
                if zf[r2, c2] < e:
                    zf[r2, c2] = e
                heapq.heappush(heap, (zf[r2, c2], r2, c2))
    return zf


def build_sources(dom, fd, catch, acc, basin):
    """Map every catchment cell to the first active cell on its D8 path; weight by sub-basin share."""
    labels = grid.read(config.INTERIM / "subbasins.tif")
    active, idx = dom["active"], dom["idx"]
    nr, nc = catch.shape
    entry = -np.ones(catch.shape, dtype=np.int64)
    rows, cols = np.nonzero(catch)
    for i in np.argsort(-acc[rows, cols], kind="stable"):          # downstream cells first
        r, c = rows[i], cols[i]
        if active[r, c]:
            entry[r, c] = idx[r, c]
            continue
        dr, dc = DIRMAP.get(int(fd[r, c]), (0, 0))
        r2, c2 = r + dr, c + dc
        if (dr or dc) and 0 <= r2 < nr and 0 <= c2 < nc:
            entry[r, c] = entry[r2, c2] if catch[r2, c2] else (idx[r2, c2] if active[r2, c2] else -1)
    row_of = {sb.id: k for k, sb in enumerate(basin)}
    src_cell, src_sb, src_w = [], [], []
    for sb in basin:
        m = (labels == sb.id) & (entry >= 0)
        cells, counts = np.unique(entry[m], return_counts=True)
        src_cell += cells.tolist()
        src_sb += [row_of[sb.id]] * len(cells)
        src_w += (counts / (labels == sb.id).sum()).tolist()
    lost = float(1.0 - (entry[catch] >= 0).mean())
    return (np.array(src_cell), np.array(src_sb), np.array(src_w)), lost


def _dem2d(dom):
    a = np.full(dom["active"].shape, -9999.0, dtype="float32")
    a[dom["rows"], dom["cols"]] = dom["z"]
    return a


def boundary_cells(active, ext):
    inner = ndimage.binary_erosion(active, structure=np.ones((3, 3)))
    return active & ~inner & ~ext


def write_outputs(name, dom, res, p24, hydro_peak, meta):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    rows, cols = dom["rows"], dom["cols"]
    shape = dom["active"].shape

    def to_grid(v, fill, scale=1.0):
        a = np.full(shape, fill, dtype="float32")
        a[rows, cols] = np.where(v >= 0, v * scale, fill) if fill < 0 else v * scale
        return a

    grid.write(d / "hmax.tif", to_grid(res["hmax"], 0.0), "float32", 0.0)
    grid.write(d / "vmax.tif", to_grid(res["vmax"], 0.0), "float32", 0.0)
    grid.write(d / "hvmax.tif", to_grid(res["hvmax"], 0.0), "float32", 0.0)
    grid.write(d / "t_arrival_01.tif", to_grid(res["t_arrival_01"], -1.0, 1 / 3600), "float32", -1.0)
    grid.write(d / "t_arrival_03.tif", to_grid(res["t_arrival_03"], -1.0, 1 / 3600), "float32", -1.0)
    grid.write(d / "duration_03.tif", to_grid(res["duration_03"], 0.0, 1 / 3600), "float32", 0.0)
    np.savez_compressed(d / "snaps.npz", depth=res["snaps"].astype(np.float16), outflow=res["outflow"],
                        snap_every_s=1800.0)
    bnd = boundary_cells(dom["active"], dom["ext"])[rows, cols]
    wet = res["hmax"] > 0.1
    info = {
        "name": name, "p24_mm": p24, **meta,
        "mass_error": round(res["mass_error"], 5),
        "vol_in_hm3": round(res["vol_in"] / 1e6, 3), "vol_out_hm3": round(res["vol_out"] / 1e6, 3),
        "peak_outflow_m3s": round(float(res["outflow"].max()), 1),
        "hms_outlet_peak_m3s": round(hydro_peak, 1),
        "flooded_km2_gt_0.1m": round(float(wet.sum() * 0.0009), 2),
        "flooded_km2_gt_0.3m": round(float((res["hmax"] > 0.3).sum() * 0.0009), 2),
        "max_depth_m": round(float(res["hmax"].max()), 2),
        "max_velocity_ms": round(float(res["vmax"].max()), 2),
        "boundary_cells_wet_gt_0.3m_pct": round(float(100 * (res["hmax"][bnd] > 0.3).mean()), 2),
        "boundary_max_depth_m": round(float(res["hmax"][bnd].max()), 2),
    }
    (d / "run.json").write_text(json.dumps(info, indent=1), encoding="utf8")
    return info


def run(names=None):
    OUT.mkdir(parents=True, exist_ok=True)
    basin = hms.load_basin()
    dom, fd, catch, acc = build_domain()
    sources, lost = build_sources(dom, fd, catch, acc, basin)
    print(f"  domain {len(dom['z'])} cells ({len(dom['z']) * 0.0009:.1f} km2), {len(dom['fa'])} faces, "
          f"{len(sources[0])} inflow cells, {len(dom['outlets'][0])} outflow cells, unmapped area {lost:.2%}, "
          f"4-conn fill {dom['fill_stats']}")
    (OUT / "domain.json").write_text(json.dumps({"cells": len(dom["z"]), "area_km2": round(len(dom["z"]) * 0.0009, 2),
                                                 "fill": dom["fill_stats"], "corridor_m": CORRIDOR_CELLS * 30,
                                                 "hand_max_m": HAND_MAX, "channel_km2": CHANNEL_KM2}), encoding="utf8")
    grid.write(OUT / "dem_2d.tif", _dem2d(dom), "float32", -9999.0)
    np.save(OUT / "domain_active.npy", dom["active"])
    lib = library()
    for name, p24 in lib.items():
        if names and name not in names:
            continue
        rain = storms.hyetograph_for_depth(p24, 731.0)
        res_h = hms.run_network(basin, lambda sb: rain)
        q_local = np.array([res_h[sb.id]["local"] for sb in basin])
        t = time.time()
        res = lf.simulate(dom, sources, q_local, hms.DT_S, 0.0, SIM_T1_H * 3600, dom["outlets"])
        info = write_outputs(name, dom, res, p24, float(res_h[1]["total"].max()),
                             {"runtime_s": round(time.time() - t, 1), "rain_mm": round(float(rain.sum()), 1)})
        print(f"  {name:6s} P24 {p24:6.1f} mm | peak out {info['peak_outflow_m3s']:7.1f} (HMS {info['hms_outlet_peak_m3s']:7.1f}) m3/s"
              f" | flooded {info['flooded_km2_gt_0.1m']:5.2f} km2 | hmax {info['max_depth_m']:5.2f} m | vmax {info['max_velocity_ms']:4.1f}"
              f" | mass err {info['mass_error']:+.4f} | boundary wet {info['boundary_cells_wet_gt_0.3m_pct']:.1f}% "
              f"| {info['runtime_s']} s")


if __name__ == "__main__":
    run(sys.argv[1:] or None)
