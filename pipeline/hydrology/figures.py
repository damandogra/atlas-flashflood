"""Phase 2 review figures -> docs/figures/. Usage: python -m pipeline.hydrology.figures"""

import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pipeline import config  # noqa: E402
from pipeline.hydrology.scenarios import OUT, francou_rodier_k  # noqa: E402

FIG = config.REPO / "docs" / "figures"
KEY_POINTS = ["Télouet", "Tighza", "Anmiter", "Assaka", "Tazlaft", "Tamdakhte", "Ait Ben Haddou"]


def load():
    design = json.loads((OUT / "design.json").read_text(encoding="utf8"))
    checks = json.loads((OUT / "checks.json").read_text(encoding="utf8"))
    return design, checks


def hydrographs(design):
    meta, res = design["meta"], design["results"]["central"]
    by_name = {p["name"]: p for p in meta["points"]}
    dt_h = meta["stored_dt_min"] / 60
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), sharey=False)
    for ax, T in zip(axes, ("10", "100")):
        rain = np.array(res[T]["outlet_storm_rain_mm"])
        t = np.arange(len(rain)) * dt_h
        ax2 = ax.twinx()
        ax2.bar(t, rain / dt_h, width=dt_h, color="steelblue", alpha=0.3, align="edge")
        ax2.set_ylim(80, 0)
        ax2.set_ylabel("Catchment rain intensity (mm/h)", color="steelblue")
        for name in KEY_POINTS:
            p = by_name[name]
            q = np.array(res[T]["point_specific"][str(p["id"])]["q"])
            ax.plot(np.arange(len(q)) * dt_h, q, label=f"{name} ({p['drainage_km2']:.0f} km2)")
        ax.set_xlim(8, 36)
        ax.set_xlabel("Hours from storm start")
        ax.set_ylabel("Discharge (m3/s)")
        ax.set_title(f"T{T} design flood, central rainfall, point-specific storms")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="center right")
    fig.savefig(FIG / "phase2_hydrographs.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def regional(design, checks):
    meta, res = design["meta"], design["results"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    a = np.logspace(0, 3.3, 50)
    for k in (3.0, 3.5, 4.0, 4.5, 5.0):
        ax.plot(a, 1e6 * (a / 1e8) ** (1 - k / 10), "k:", lw=0.8)
        ax.text(a[-1], 1e6 * (a[-1] / 1e8) ** (1 - k / 10), f" K={k}", fontsize=8, va="center")
    for T, mk in (("10", "o"), ("100", "s")):
        for lv, col in (("low", "tab:green"), ("central", "tab:blue"), ("high", "tab:red")):
            pts = [(p["drainage_km2"], res[lv][T]["point_specific"][str(p["id"])]["peak_m3s"]) for p in meta["points"]]
            ax.scatter(*zip(*pts), marker=mk, s=18, color=col, alpha=0.8 if lv == "central" else 0.35,
                       label=f"model T{T} {lv}")
    for r in checks["regional"]:
        ax.scatter(r["area_km2"], r["peak_m3s"], marker="*", s=140, color="black")
        ax.annotate(r["name"], (r["area_km2"], r["peak_m3s"]), fontsize=7, xytext=(-140, 3), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Drainage area (km2)")
    ax.set_ylabel("Peak discharge (m3/s)")
    ax.set_title("Design peaks at all 21 control points vs Francou-Rodier K lines and Ourika gauge data")
    ax.legend(fontsize=7, ncol=2, loc="lower right")
    ax.grid(alpha=0.3, which="both")

    T = np.array(meta["return_periods"])
    for lv, col in (("low", "tab:green"), ("central", "tab:blue"), ("high", "tab:red")):
        q = [checks["outlet_peaks"][lv][str(t)] for t in T]
        ax2.plot(T, q, "-o", color=col, label=f"{lv} rainfall (x{meta['rain_levels'][lv]})")
    for k, ls in ((3.0, ":"), (3.74, "--"), (4.1, "-.")):
        ax2.axhline(1e6 * (730.9 / 1e8) ** (1 - k / 10), color="gray", ls=ls, lw=1,
                    label={3.0: "K=3.0 (Rheraya T10)", 3.74: "K=3.74 (Ourika Q10)", 4.1: "K=4.1 (Rheraya T100)"}[k])
    wb = checks["water_balance"]
    ax2.set_xscale("log")
    ax2.set_xlabel("Return period (years)")
    ax2.set_ylabel("Outlet peak, Ait Ben Haddou (m3/s)")
    ax2.set_title("Outlet flood-frequency by rainfall level. Water balance (Agouillal gauge):\n"
                  f"storm runoff observed {wb['observed_storm_runoff_mm_yr'][0]}-{wb['observed_storm_runoff_mm_yr'][1]} "
                  f"mm/yr; model low {wb['levels']['low']['storm_runoff_mm_yr']}, central "
                  f"{wb['levels']['central']['storm_runoff_mm_yr']}, high {wb['levels']['high']['storm_runoff_mm_yr']}",
                  fontsize=9)
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3, which="both")
    fig.savefig(FIG / "phase2_regional_check.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    d, c = load()
    hydrographs(d)
    regional(d, c)
    print(f"  figures -> {FIG}")
