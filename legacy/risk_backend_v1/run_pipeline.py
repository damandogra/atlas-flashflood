"""
run_pipeline.py
===============
Full risk-engine pipeline orchestrator (hackathon v1, formerly Exposure_Person_B).

Runs each stage in order, skipping steps whose output files already exist.

Usage:
    python run_pipeline.py              # run everything
    python run_pipeline.py --force      # re-run all steps even if outputs exist
    python run_pipeline.py --from risk  # start from a specific stage
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

from scripts.a_download_osm import download_osm_data            # 01
from scripts.a_download_worldpop import run_worldpop_ingestion   # 01
from scripts.b_analyse_exposure import analyze_exposure          # 02 (#13/#14)
from scripts.b_analyse_network import analyze_network            # 02 (#16)
from scripts.c_risk_index import build_risk_index                # 03 (#15)
from scripts.d_early_warning import get_alert                    # 04 (#17) — sanity check
from scripts.e_citizen import init_db                            # 05 (#19)
from scripts.f_citizen_fusion import fuse                        # 06 (#34)
from scripts.g_action_generator import write_action_cards        # 07 (#35)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _exists(*paths) -> bool:
    return all(os.path.exists(p) for p in paths)


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

STAGES = [
    "osm",
    "worldpop",
    "exposure",
    "network",
    "risk",
    "citizen_db",
    "fusion",
    "actions",
]


def run(force: bool = False, from_stage: str = None):
    start_idx = STAGES.index(from_stage) if from_stage in STAGES else 0

    _header("🚀 OUNILA FLOOD SYSTEM — PERSON B PIPELINE")

    # ------------------------------------------------------------------
    # STAGE 1: OSM data download
    # ------------------------------------------------------------------
    if STAGES.index("osm") >= start_idx:
        buildings_path = os.path.join(config.DATA_RAW, config.LAYERS["buildings"])
        if force or not _exists(buildings_path):
            _header("[1/8] 🛰️  OSM Data Ingestion  (Issue #11)")
            download_osm_data()
        else:
            print("\n✅  [1/8] OSM data already exists — skipping.")

    # ------------------------------------------------------------------
    # STAGE 2: WorldPop population raster
    # ------------------------------------------------------------------
    if STAGES.index("worldpop") >= start_idx:
        pop_path = os.path.join(config.DATA_RAW, config.LAYERS["population"])
        if force or not _exists(pop_path):
            _header("[2/8] 👥  WorldPop Ingestion  (Issue #12)")
            run_worldpop_ingestion()
        else:
            print("✅  [2/8] WorldPop raster already exists — skipping.")

    # ------------------------------------------------------------------
    # STAGE 3: Exposure analysis
    # ------------------------------------------------------------------
    if STAGES.index("exposure") >= start_idx:
        _header("[3/8] 🌊  Exposure Analysis  (Issues #13 / #14)")
        analyze_exposure()

    # ------------------------------------------------------------------
    # STAGE 4: Network / road analysis
    # ------------------------------------------------------------------
    if STAGES.index("network") >= start_idx:
        _header("[4/8] 🛣️   Network Analysis  (Issue #16)")
        analyze_network()

    # ------------------------------------------------------------------
    # STAGE 5: Composite Risk Index rasters
    # ------------------------------------------------------------------
    if STAGES.index("risk") >= start_idx:
        _header("[5/8] 📊  Composite Risk Index  (Issue #15)")
        build_risk_index()

    # ------------------------------------------------------------------
    # STAGE 6: Citizen DB initialisation + early warning check
    # ------------------------------------------------------------------
    if STAGES.index("citizen_db") >= start_idx:
        _header("[6/8] 📋  Citizen DB + Early Warning  (Issues #17 / #19)")
        init_db()
        alert = get_alert()
        print(f"   ⚡  Current alert: {alert['label']}")
        print(f"       Forecast rainfall: {alert.get('rainfall_mm', 'N/A')} mm/24h")

    # ------------------------------------------------------------------
    # STAGE 7: Citizen fusion
    # ------------------------------------------------------------------
    if STAGES.index("fusion") >= start_idx:
        _header("[7/8] 🔀  Citizen Signal Fusion  (Issue #34)")
        fuse()

    # ------------------------------------------------------------------
    # STAGE 8: Action cards
    # ------------------------------------------------------------------
    if STAGES.index("actions") >= start_idx:
        _header("[8/8] 🃏  Action Card Generator  (Issue #35)")
        write_action_cards()

    # ------------------------------------------------------------------
    _header("🏁 PIPELINE COMPLETE")
    print("\nOutputs are in:", config.DATA_OUT)
    print("Start the API with:")
    print("    cd api && uvicorn main:app --host 0.0.0.0 --port 8000 --reload\n")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ounila risk-engine pipeline (v1)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all steps even if outputs already exist")
    parser.add_argument("--from", dest="from_stage",
                        choices=STAGES, default=None,
                        help="Start from this pipeline stage")
    args = parser.parse_args()
    run(force=args.force, from_stage=args.from_stage)