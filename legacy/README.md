# Legacy hackathon code (v1)

Reference only. Nothing in `pipeline/` or `web/` imports from here.

<img width="834" height="522" alt="Atlas v1 dashboard from the Cassini Hackathon" src="https://github.com/user-attachments/assets/936222e1-dd6c-4680-a00e-98d453e86905" />

*The v1 dashboard as presented at the Cassini Hackathon.*

| Folder | Came from | What it was |
|---|---|---|
| `hydrology_v1/` | branch `data-extraction` (was `Hydrology_Part_A`) | Sentinel Hub NDVI/DEM download, per-pixel SCS-CN, Manning velocity, RUSLE |
| `risk_backend_v1/` | `main` + `api/` from branch `pipeline-backend` (was `Exposure_Person_B`) | OSM/WorldPop exposure, roads, CRI, early warning, citizen DB, action cards, FastAPI |
| `frontend_v1/` | branch `frontend` | Lovable/TanStack-Start + Mapbox dashboard (source only) |

Known issues that v2 fixes:
- Depth was `runoff_mm / 1000` per pixel, with no flow accumulation or routing. As a result the T500 maximum depth was only 0.16 m and no road ever closed.
- The rainfall inputs were inconsistent.
- Action-card coordinates were null.
