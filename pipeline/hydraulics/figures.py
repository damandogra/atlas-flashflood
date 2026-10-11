"""Phase 3 review figures -> docs/figures/. Usage: python -m pipeline.hydraulics.figures"""

import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LightSource  # noqa: E402
from pyproj import Transformer  # noqa: E402

from pipeline import config, grid  # noqa: E402
from pipeline.hydraulics.scenarios import OUT, library  # noqa: E402

FIG = config.REPO / "docs" / "figures"
VILLAGES = ["Télouet", "Tighza", "Anmiter", "Tajeguite", "Assaka", "Ait Fars", "Taifest", "Ankhsa", "Tazlaft",
            "Tamdakhte", "Aït Ben Haddou"]


def _base():
    dem = grid.read(config.RAW / "dem.tif")
    act = np.load(OUT / "domain_active.npy")
    rows, cols = np.nonzero(act)
    win = (rows.min() - 15, rows.max() + 15, cols.min() - 15, cols.max() + 15)
    hs = LightSource(315, 45).hillshade(dem, dx=30, dy=30)
    return hs, act, win


def _villages(ax, win):
    t, _, _ = grid.model_grid()
    to_utm = Transformer.from_crs(config.CRS_WEB, config.CRS_WORK, always_xy=True)
    places = json.loads((config.RAW / "osm_places.geojson").read_text(encoding="utf8"))["features"]
    for f in places:
        if f["properties"]["name"] in VILLAGES and f["properties"]["place"] in ("town", "village"):
            col, row = ~t * to_utm.transform(*f["geometry"]["coordinates"])
            if win[0] <= row < win[1] and win[2] <= col < win[3]:
                ax.plot(col - win[2], row - win[0], "o", color="crimson", ms=3)
                ax.annotate(f["properties"]["name"], (col - win[2], row - win[0]), fontsize=7, color="crimson",
                            xytext=(3, 3), textcoords="offset points")


def overview():
    hs, act, w = _base()
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    for ax, name in zip(axes, ("T10", "T100")):
        h = grid.read(OUT / name / "hmax.tif")
        info = json.loads((OUT / name / "run.json").read_text(encoding="utf8"))
        ax.imshow(hs[w[0]:w[1], w[2]:w[3]], cmap="gray")
        im = ax.imshow(np.ma.masked_less(h[w[0]:w[1], w[2]:w[3]], 0.1), cmap="Blues", vmin=0, vmax=3)
        _villages(ax, w)
        ax.set_title(f"{name}: max depth (> 0.1 m) | {info['flooded_km2_gt_0.1m']} km2 flooded, "
                     f"peak outflow {info['peak_outflow_m3s']:.0f} m3/s", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.colorbar(im, ax=axes, shrink=0.5, label="Max depth (m)")
    fig.savefig(FIG / "phase3_overview.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def zoom():
    hs, act, _ = _base()
    t, _, _ = grid.model_grid()
    to_utm = Transformer.from_crs(config.CRS_WEB, config.CRS_WORK, always_xy=True)
    col, row = ~t * to_utm.transform(-7.135, 31.065)          # between Tamdaght and Ait Ben Haddou
    w = (int(row) - 110, int(row) + 110, int(col) - 90, int(col) + 90)
    fig, axes = plt.subplots(1, 3, figsize=(18, 7.5))
    h = grid.read(OUT / "T100" / "hmax.tif")
    v = grid.read(OUT / "T100" / "vmax.tif")
    ta = grid.read(OUT / "T100" / "t_arrival_03.tif")
    panels = [(np.ma.masked_less(h, 0.1), "Blues", (0, 4), "T100 max depth (m)"),
              (np.ma.masked_where(h < 0.1, v), "magma_r", (0, 5), "T100 max velocity (m/s)"),
              (np.ma.masked_less(ta, 0), "viridis", (12, 20), "T100: time water first exceeds 0.3 m (h from storm start)")]
    for ax, (data, cmap, (lo, hi), title) in zip(axes, panels):
        ax.imshow(hs[w[0]:w[1], w[2]:w[3]], cmap="gray")
        im = ax.imshow(data[w[0]:w[1], w[2]:w[3]], cmap=cmap, vmin=lo, vmax=hi)
        _villages(ax, w)
        fig.colorbar(im, ax=ax, shrink=0.6)
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Tamdaght -> Ait Ben Haddou (UNESCO ksar), 30 m 2D model")
    fig.savefig(FIG / "phase3_zoom_aitbenhaddou.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def library_curves():
    rows = []
    for name, p24 in library().items():
        f = OUT / name / "run.json"
        if f.exists():
            rows.append(json.loads(f.read_text(encoding="utf8")))
    p = [r["p24_mm"] for r in rows]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    ax.plot(p, [r["peak_outflow_m3s"] for r in rows], "o-", label="2D model (floodplain storage)")
    ax.plot(p, [r["hms_outlet_peak_m3s"] for r in rows], "s--", label="HMS (Muskingum-Cunge)")
    for r in rows:
        ax.annotate(r["name"], (r["p24_mm"], r["peak_outflow_m3s"]), fontsize=7, xytext=(3, -10), textcoords="offset points")
    ax.set_xlabel("Catchment 24 h rainfall (mm)")
    ax.set_ylabel("Peak discharge below Ait Ben Haddou (m3/s)")
    ax.legend()
    ax.grid(alpha=0.3)
    ax2.plot(p, [r["flooded_km2_gt_0.1m"] for r in rows], "o-", label="> 0.1 m")
    ax2.plot(p, [r["flooded_km2_gt_0.3m"] for r in rows], "s-", label="> 0.3 m")
    ax2.set_xlabel("Catchment 24 h rainfall (mm)")
    ax2.set_ylabel("Flooded area in the valley corridors (km2)")
    ax2.legend()
    ax2.grid(alpha=0.3)
    fig.suptitle("Scenario library response (used to match live forecasts to a precomputed flood map)")
    fig.savefig(FIG / "phase3_library.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    overview()
    zoom()
    library_curves()
    print(f"  figures -> {FIG}")
