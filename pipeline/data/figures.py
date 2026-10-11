"""Phase 1 review figures -> docs/figures/. Usage: python -m pipeline.data.figures"""

import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LightSource  # noqa: E402

from pipeline import config, grid  # noqa: E402

FIG = config.REPO / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)


def subbasin_map():
    dem = grid.read(config.INTERIM / "dem_cond.tif")
    lab = grid.read(config.INTERIM / "subbasins.tif")
    acc = grid.read(config.INTERIM / "acc_km2.tif")
    cn = grid.read(config.INTERIM / "cn_amc2.tif")
    t, _, _ = grid.model_grid()
    rows, cols = np.where(lab.any(1))[0], np.where(lab.any(0))[0]
    r0, r1, c0, c1 = rows.min() - 20, rows.max() + 20, cols.min() - 20, cols.max() + 20
    ext = [t.c + c0 * 30, t.c + c1 * 30, t.f - r1 * 30, t.f - r0 * 30]
    hs = LightSource(315, 45).hillshade(dem, dx=30, dy=30)[r0:r1, c0:c1]
    model = json.loads((config.INTERIM / "basin_model.json").read_text(encoding="utf8"))

    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    for ax, title in zip(axes, ("Sub-basins and control points", "SCS Curve Number (AMC II)")):
        ax.imshow(hs, cmap="gray", extent=ext)
        if "Curve" in title:
            im = ax.imshow(np.ma.masked_equal(cn, 0)[r0:r1, c0:c1], cmap="YlOrBr", alpha=0.65, extent=ext, vmin=60, vmax=95)
            fig.colorbar(im, ax=ax, shrink=0.6, label="CN")
        else:
            ax.imshow(np.ma.masked_equal(lab, 0)[r0:r1, c0:c1] % 10, cmap="tab10", alpha=0.35, extent=ext,
                      interpolation="nearest")
        ax.imshow(np.ma.masked_less(np.log10(np.maximum(acc, 1e-3)), 0)[r0:r1, c0:c1], cmap="Blues", extent=ext,
                  vmin=-0.5, vmax=3)
        for sb in model["subbasins"]:
            x, y = sb["outlet_xy"]
            ax.plot(x, y, "o", color="orange" if sb["kind"] == "confluence" else "red", ms=4)
            if sb["kind"] != "confluence" and "Sub" in title:
                ax.annotate(f"{sb['id']} {sb['name']}", (x, y), fontsize=7, xytext=(4, 3), textcoords="offset points")
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.ticklabel_format(style="plain")
    fig.suptitle(f"Ounila catchment at Ait Ben Haddou - {model['catchment_km2']} km2, "
                 f"{len(model['subbasins'])} sub-basins (UTM 29N)")
    fig.savefig(FIG / "phase1_subbasins_cn.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def idf_plot():
    idf = json.loads((config.INTERIM / "rainfall" / "idf.json").read_text(encoding="utf8"))
    d = np.array(idf["durations_h"])
    T = idf["return_periods"]
    sc = idf["scales"]["catchment"]
    central, lo, hi = (np.array(sc[f"depth_mm_{lv}"]) for lv in ("central", "low", "high"))
    native = np.array(sc["era5_native_depth_mm"])
    shape = idf["storm_shape"]

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1.6, 1]})
    colors = plt.cm.viridis(np.linspace(0, 0.9, len(T)))
    for j, (t, c) in enumerate(zip(T, colors)):
        ax.plot(d, central[:, j], "-o", color=c, ms=3, label=f"T{t}")
        if t in (10, 100):
            ax.fill_between(d, lo[:, j], hi[:, j], color=c, alpha=0.15)
        ax.plot(d, native[:, j], ":", color=c, lw=1)
    ax.set_xscale("log")
    ax.set_xticks(d, [f"{x} h" for x in d])
    ax.set_xlabel("Duration")
    ax.set_ylabel("Catchment-average liquid rainfall (mm)")
    lv = idf["correction_levels"]
    ax.set_title(f"Design depth-duration-frequency (ERA5-Land {idf['years'][0]}-{idf['years'][1]}, liquid)\n"
                 f"solid = central (x{lv['central']}, IMERG storm shape); band = low-high for T10, T100 "
                 f"(x{lv['low']}-{lv['high']}); dotted = ERA5 uncorrected", fontsize=9)
    ax.legend(ncol=2, fontsize=8)
    ax.grid(alpha=0.3, which="both")

    sd = np.array(shape["durations_h"])
    ax2.fill_between(sd, shape["imerg_ratio_p5"], shape["imerg_ratio_p95"], alpha=0.25, label="IMERG 90% CI (bootstrap)")
    ax2.plot(sd, shape["imerg_ratio_to_24h"], "o-", label="IMERG V07 - used for design")
    ax2.plot(sd, shape["era5_ratio_to_24h"], "s--", label="ERA5-Land (too flat, not used)")
    ax2.plot(sd, (sd / 24) ** (1 - shape["montana_b_summary"]), "k:", lw=1,
             label=f"Montana summary b = {shape['montana_b_summary']}")
    ax2.set_xscale("log")
    ax2.set_xticks(sd, [f"{x} h" for x in sd])
    ax2.set_ylabel("Mean annual max D-hour depth / 24 h depth")
    ax2.set_title("Storm shape: how much of a day's rain falls in the peak D hours", fontsize=9)
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3, which="both")
    fig.savefig(FIG / "phase1_idf.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def design_storm_plot():
    s = json.loads((config.INTERIM / "rainfall" / "design_storms.json").read_text(encoding="utf8"))
    fig, ax = plt.subplots(figsize=(9, 4))
    for T in ("10", "50", "100", "500"):
        h = np.array(s["scales"]["catchment"][T])
        t = np.arange(len(h)) * s["dt_min"] / 60
        ax.step(t, h * 60 / s["dt_min"], where="post", label=f"T{T}: {h.sum():.0f} mm / 24 h")
    ax.set_xlim(8, 16)
    ax.set_xlabel("Hour of storm")
    ax.set_ylabel("Intensity (mm/h)")
    ax.set_title("Design hyetographs (alternating block, 15 min), catchment scale")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.savefig(FIG / "phase1_design_storms.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    subbasin_map()
    idf_plot()
    design_storm_plot()
    print(f"  figures -> {FIG}")
