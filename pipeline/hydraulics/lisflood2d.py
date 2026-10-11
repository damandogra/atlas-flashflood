"""2D local-inertia flood solver (Bates, Horritt & Fewtrell 2010; LISFLOOD-FP formulation).

Momentum on cell faces (explicit, semi-implicit friction):
    q_{t+dt} = (q_t - g h_f dt dEta/dx) / (1 + g dt n^2 |q_t| / h_f^(7/3))
with h_f = max(eta_i, eta_j) - max(z_i, z_j), Froude-limited (|q| <= Fr_max h_f sqrt(g h_f)) for the
steep wadi reaches. Continuity by flux differencing. Adaptive dt = alpha dx / sqrt(g h_max).
Free (normal-depth) outflow where D8 flow leaves the domain at the catchment outlet.

The grid is any boolean `active` mask on the model grid; only active cells and faces between two
active cells are computed (index lists), so a valley-corridor domain is cheap.
"""

import numpy as np
from numba import njit

G = 9.81
ALPHA = 0.7
FR_MAX = 1.0
H_DRY = 1e-3


def build(active, z, n):
    """Index structures for the active domain. Returns a dict of arrays used by simulate()."""
    nr, nc = active.shape
    idx = -np.ones(active.shape, dtype=np.int64)
    rows, cols = np.nonzero(active)
    idx[rows, cols] = np.arange(len(rows))
    fa, fb, fdir = [], [], []
    for (dr, dc, d) in ((0, 1, 0), (1, 0, 1)):            # east faces (d=0), south faces (d=1)
        a = idx[: nr - dr, : nc - dc]
        b = idx[dr:, dc:]
        m = (a >= 0) & (b >= 0)
        fa.append(a[m])
        fb.append(b[m])
        fdir.append(np.full(m.sum(), d))
    fa, fb, fdir = np.concatenate(fa), np.concatenate(fb), np.concatenate(fdir)
    zc, nc_ = z[rows, cols].astype(np.float64), n[rows, cols].astype(np.float64)
    # per-cell face lookup for velocities: [west, east, north, south] face index or -1
    cell_faces = -np.ones((len(rows), 4), dtype=np.int64)
    for f, (a, b, d) in enumerate(zip(fa, fb, fdir)):
        if d == 0:
            cell_faces[a, 1] = f
            cell_faces[b, 0] = f
        else:
            cell_faces[a, 3] = f
            cell_faces[b, 2] = f
    return {"idx": idx, "rows": rows, "cols": cols, "z": zc, "n": nc_, "fa": fa, "fb": fb,
            "fn": 0.5 * (nc_[fa] + nc_[fb]), "cell_faces": cell_faces}


@njit(cache=True)
def _run(z, n_cell, fa, fb, fn, cell_faces, dx,
         src_cell, src_sb, src_w, q_local, q_dt, t0, t1,
         out_cell, out_slope, snap_every, h_init):
    nc = len(z)
    nf = len(fa)
    h = h_init.copy()
    q = np.zeros(nf)
    hmax = np.zeros(nc)
    vmax = np.zeros(nc)
    hvmax = np.zeros(nc)
    t_01 = np.full(nc, -1.0)
    t_03 = np.full(nc, -1.0)
    dur_03 = np.zeros(nc)
    n_snaps = int((t1 - t0) // snap_every) + 1
    snaps = np.zeros((n_snaps, nc), dtype=np.float32)
    outflow = np.zeros(n_snaps)
    vol_in = 0.0
    vol_out = 0.0
    t = t0
    next_snap = t0
    k = 0
    out_acc = 0.0
    out_acc_t = 0.0
    area = dx * dx
    while t < t1:
        # adaptive time step
        hm = 0.0
        for i in range(nc):
            if h[i] > hm:
                hm = h[i]
        dt = ALPHA * dx / np.sqrt(G * max(hm, 0.01))
        dt = min(dt, 10.0, t1 - t)
        # face fluxes
        for f in range(nf):
            a = fa[f]
            b = fb[f]
            ea = z[a] + h[a]
            eb = z[b] + h[b]
            hf = max(ea, eb) - max(z[a], z[b])
            if hf <= H_DRY:
                q[f] = 0.0
                continue
            s = (eb - ea) / dx
            qn = (q[f] - G * hf * dt * s) / (1.0 + G * dt * fn[f] * fn[f] * abs(q[f]) / hf ** (7.0 / 3.0))
            qlim = FR_MAX * hf * np.sqrt(G * hf)
            if qn > qlim:
                qn = qlim
            elif qn < -qlim:
                qn = -qlim
            q[f] = qn
        # continuity
        for f in range(nf):
            dv = q[f] * dt / dx                   # depth change (m) for a dx-wide face
            h[fa[f]] -= dv
            h[fb[f]] += dv
        # lateral inflow from the hydrology model (linear interpolation in time)
        j = int(t // q_dt)
        w = (t - j * q_dt) / q_dt
        nq = q_local.shape[1]
        for s_ in range(len(src_cell)):
            sb = src_sb[s_]
            if j + 1 < nq:
                qq = (1 - w) * q_local[sb, j] + w * q_local[sb, j + 1]
            elif j < nq:
                qq = q_local[sb, j]
            else:
                qq = 0.0
            dv = src_w[s_] * qq * dt
            h[src_cell[s_]] += dv / area
            vol_in += dv
        # free outflow (normal depth) where flow leaves the domain at the outlet
        for o in range(len(out_cell)):
            c = out_cell[o]
            if h[c] > H_DRY:
                qo = h[c] ** (5.0 / 3.0) * np.sqrt(out_slope[o]) / n_cell[c]
                dv = min(qo * dt / dx, h[c])
                h[c] -= dv
                vol_out += dv * area
                out_acc += dv * area
        out_acc_t += dt
        # clip tiny negatives (counted in the mass-balance check)
        for i in range(nc):
            if h[i] < 0.0:
                h[i] = 0.0
        t += dt
        # maxima, velocities, arrival times
        for i in range(nc):
            hi = h[i]
            if hi > hmax[i]:
                hmax[i] = hi
            if hi > 0.1 and t_01[i] < 0:
                t_01[i] = t
            if hi > 0.3:
                if t_03[i] < 0:
                    t_03[i] = t
                dur_03[i] += dt
            if hi > 0.05:
                qx = 0.0
                qy = 0.0
                if cell_faces[i, 0] >= 0:
                    qx += 0.5 * q[cell_faces[i, 0]]
                if cell_faces[i, 1] >= 0:
                    qx += 0.5 * q[cell_faces[i, 1]]
                if cell_faces[i, 2] >= 0:
                    qy += 0.5 * q[cell_faces[i, 2]]
                if cell_faces[i, 3] >= 0:
                    qy += 0.5 * q[cell_faces[i, 3]]
                # cell velocity from face discharges; capped at Froude 1.5 of the cell depth, because a
                # face can carry a deep neighbour's flux past a barely-wet cell (q/h spike, not physical)
                v = min(np.sqrt(qx * qx + qy * qy) / hi, 1.5 * np.sqrt(G * hi))
                if v > vmax[i]:
                    vmax[i] = v
                hv = hi * (v + 0.5)
                if hv > hvmax[i]:
                    hvmax[i] = hv
        if t >= next_snap and k < n_snaps:
            snaps[k] = h.astype(np.float32)
            outflow[k] = out_acc / max(out_acc_t, 1e-9)
            out_acc = 0.0
            out_acc_t = 0.0
            k += 1
            next_snap += snap_every
    return h, hmax, vmax, hvmax, t_01, t_03, dur_03, snaps, outflow, vol_in, vol_out


def simulate(dom, sources, q_local, q_dt, t0, t1, outlets, dx=30.0, snap_every=1800.0, h_init=None):
    """sources: (cell, subbasin_row, weight); q_local: [n_subbasins, n_steps] m3/s at q_dt seconds;
    outlets: (cell, slope). Times in seconds from storm start."""
    nc = len(dom["z"])
    h0 = np.zeros(nc) if h_init is None else h_init
    src_cell, src_sb, src_w = (np.asarray(x) for x in sources)
    out_cell, out_slope = (np.asarray(x) for x in outlets)
    res = _run(dom["z"], dom["n"], dom["fa"], dom["fb"], dom["fn"], dom["cell_faces"], float(dx),
               src_cell.astype(np.int64), src_sb.astype(np.int64), src_w.astype(np.float64),
               np.ascontiguousarray(q_local, dtype=np.float64), float(q_dt), float(t0), float(t1),
               out_cell.astype(np.int64), out_slope.astype(np.float64), float(snap_every), h0.astype(np.float64))
    keys = ("h_end", "hmax", "vmax", "hvmax", "t_arrival_01", "t_arrival_03", "duration_03", "snaps",
            "outflow", "vol_in", "vol_out")
    out = dict(zip(keys, res))
    out["vol_stored"] = float(out["h_end"].sum() * dx * dx)
    out["mass_error"] = float((out["vol_in"] - out["vol_out"] - out["vol_stored"]) / max(out["vol_in"], 1.0))
    return out
