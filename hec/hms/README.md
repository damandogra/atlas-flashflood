# HEC-HMS cross-check

This folder contains the Ounila basin model as an **HEC-HMS 4.x project**. Running it in real HEC-HMS checks the Python engine (`pipeline/hydrology/hms.py`) independently.

The goal is the same answer from both. The target is peak flows within ±10% at every junction.

**Software:** HEC-HMS 4.12, free from the US Army Corps of Engineers, Hydrologic Engineering Center (search for "HEC-HMS download"). Expect about 30–45 minutes.

## What's in `Ounila/`

| File | Content |
|---|---|
| `Ounila.hms` | The project file. Open this |
| `Ounila.basin` | 21 sub-basins, 21 junctions, 20 reaches and one sink |
| `Ounila.gage` | Two precipitation gages (T10 and T100 central). They start empty; step 2 fills them |
| `T10_central.met`, `T100_central.met` | Specified-hyetograph meteorologic models |
| `Ounila.control` | 48 h run at a 5-minute step (01 Jan 2000 00:00 to 03 Jan 2000 00:00) |
| `parameters_subbasins.csv`, `parameters_reaches.csv` | Every parameter, for manual entry if a file won't load |
| `hyetograph_T*_central.csv` | 15-minute incremental rain, in mm |
| `expected_results.csv` | The Python engine's peak, time to peak and volume at every junction |

## Steps

1. **Open the project.** In HEC-HMS: File → Open → `Ounila/Ounila.hms`.
   - If the basin fails to load (keywords vary slightly between HMS versions), create the basin model by hand from the two parameter CSVs:
     - Loss method: SCS Curve Number. Leave initial abstraction blank so it defaults to 0.2·S.
     - Transform: Clark Unit Hydrograph.
     - Routing: Muskingum-Cunge, rectangular channel, automatic DX/DT.
     - Baseflow: none.
2. **Fill each gage.** Open Time-Series Data → Precipitation Gages → `T100_central`, then the Table tab. Paste the `incremental_mm` column of `hyetograph_T100_central.csv`.
   - That's 192 rows at 15-minute steps, starting 01Jan2000 00:15.
   - Repeat for `T10_central`.
3. **Create the runs.** Compute → Create Compute → Simulation Run:
   - basin `Ounila`, meteorology `T100_central`, control `Design_48h`.
   - Repeat for T10.
4. **Compute** both runs.
5. **Export results.** Results → Global Summary Table, then export it to `Ounila/hms_results_T100.csv` (and `..._T10.csv`).
   - Tell me when the files are there. I'll compute the differences against `expected_results.csv` and report them in `docs/hydrology.md`.

## Known differences to expect

These are small, and they're the ones that are worth knowing about:

- **Muskingum-Cunge.** HEC-HMS chooses its own Δx and Δt. The Python engine uses sub-reaches at Courant number ≈ 1 at the inflow peak. Expect a few percent of difference in routed peaks.
- **Clark time step.** Both use the HEC-HMS synthetic time-area curve. HMS integrates the time-area curve slightly differently at the first and last steps.
- **Rain input.** The rain is the *outlet-storm* hyetograph: one storm sized to the 731 km² catchment, applied to every sub-basin. So compare against the `outlet_storm` results, which is what `expected_results.csv` contains.
