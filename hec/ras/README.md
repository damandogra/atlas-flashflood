# HEC-RAS 2D cross-check: Tamdaght → Aït Ben Haddou

This test checks the Atlas 2D solver (`pipeline/hydraulics/lisflood2d.py`, local-inertia, LISFLOOD-FP formulation) against **HEC-RAS 2D** on the same terrain, roughness and boundary conditions.

**The reach:**
- It runs from the junction of the western Ounila and the eastern Marghène at **Tamdaght**, down past the **Aït Ben Haddou ksar** (a UNESCO World Heritage site), to 2 km below it.
- The flood is the T100 design flood (central rainfall).

**Software:** HEC-RAS 6.6, free from the US Army Corps of Engineers, Hydrologic Engineering Center. Expect about 1–1.5 hours.

## Package (`Ounila_reach/`)

| File | Use in HEC-RAS |
|---|---|
| `terrain_utm29n.tif` | RAS Mapper → New Terrain. Projection: **WGS 84 / UTM zone 29N (EPSG:32629)** |
| `landcover_classes.tif` + `landcover_manning.csv` | RAS Mapper → Map Layers → Land Cover. Set the Manning's n per class from the CSV (class 200 = channel, n = 0.045) |
| `perimeter.shp` | Geometry → 2D Flow Area → import the perimeter. Cell size **30 m** (to match the Atlas grid) |
| `bc_inflow_Tazlaft.shp`, `bc_inflow_Taifest.shp` | Two upstream BC lines → **Flow Hydrograph**, from the matching `.csv` (15-minute steps, 0–48 h) |
| `bc_outflow.shp` | Downstream BC line → **Normal Depth**, friction slope given in `expected_summary.json` |
| `expected_hmax_m.tif`, `expected_summary.json` | The Atlas solver's answer for exactly this set-up |

## Steps

1. **Project and terrain.**
   - New project, then set the projection (EPSG:32629).
   - Create the terrain from `terrain_utm29n.tif`. The channels are already breached through the DSM's false dams, so use it as-is.
2. **Land cover.** Create the land cover layer from `landcover_classes.tif` and enter the n values from the CSV.
3. **Geometry.**
   - 2D Flow Area from `perimeter.shp`, 30 × 30 m cells.
   - Associate the terrain and land cover with the geometry.
   - Draw the three BC lines over the imported shapefiles, or import them.
4. **Unsteady flow.**
   - Paste each inflow hydrograph into its BC line.
   - Set the downstream line to Normal Depth with the slope from `expected_summary.json`.
5. **Plan.**
   - Simulation window 01JAN2000 0000 to 02JAN2000 1200 (36 h). Computation interval 2–5 s, or adaptive with Courant ≤ 1.
   - Equation set: **Diffusion Wave** first, then **Shallow Water (SWE-ELM)** as a second run.
   - Mapping output: 15 minutes.
6. **Export.** Run the plan, then in RAS Mapper export **Depth (Max)** as GeoTIFF to `Ounila_reach/ras_hmax_m.tif`.
   - I'll then compute the agreement against `expected_hmax_m.tif`:
     - F-score for the flooded extent (> 0.1 m);
     - depth RMSE and bias over cells both models wet;
     - peak outflow difference.
   - **Targets:** F ≥ 0.7 and |peak outflow difference| ≤ 10%.

## What to expect

- **Local-inertia vs SWE.** The Atlas solver neglects advection and limits the Froude number to 1 in steep reaches. Expect it to give slightly higher depths and lower velocities than full SWE in the steepest gorge sections.
- **Meshes.** HEC-RAS uses sub-grid terrain inside each 30 m cell (hydraulic property tables), the Atlas solver uses one elevation per cell. HEC-RAS conveys more water in narrow channels, so expect its depths to be lower there.
