import { useStatic } from "../../lib/useData";

const FIG = `${import.meta.env.BASE_URL}figures/`;

export default function Method() {
  const { meta } = useStatic();
  const wb = meta.validation.water_balance;
  return (
    <div className="panel-body prose">
      <h3>How Atlas works</h3>
      <ol>
        <li><b>Terrain & catchment</b> — Copernicus GLO-30 DEM; the Ounila above Aït Ben Haddou (730.9 km², matching the DRPE Agouillal gauge's 740 km²) split into 21 sub-basins at villages and confluences.</li>
        <li><b>Rainfall</b> — 76 years of ERA5-Land hourly (liquid only) for magnitudes, GPM IMERG half-hourly for the storm shape, the Ouarzazate gauge for bias. Central correction ×{meta.correction_factor}.</li>
        <li><b>Hydrology</b> — HEC-HMS methods (SCS Curve Number, Clark unit hydrograph, Muskingum-Cunge) per sub-basin.</li>
        <li><b>Hydraulics</b> — 2D local-inertia flood model (LISFLOOD-FP formulation) on a 30 m grid of the valley floors, run for 13 storms from 20 to 160 mm in 24 h.</li>
        <li><b>Impacts</b> — 16,600 building footprints (Google Open Buildings), OSM roads, fords and facilities, population from GHS-POP/WorldPop; DEFRA hazard classes, ARR 2019 vehicle limits, road-network isolation every 30 min.</li>
        <li><b>Forecast</b> — Open-Meteo (ECMWF IFS, GFS, ICON, ECMWF ensemble) → bias-corrected catchment rain → soil-moisture-equivalent depth → matching flood from the library → impact-based alert.</li>
      </ol>
      <h4>Checked against observations</h4>
      <ul>
        <li>Water balance at the Agouillal gauge: observed storm runoff {wb.observed_storm_runoff_mm_yr[0]}–{wb.observed_storm_runoff_mm_yr[1]} mm/yr, model {wb.levels.central.storm_runoff_mm_yr} mm/yr.</li>
        <li>Flood peaks consistent with gauged High Atlas floods (Ourika, Rheraya): Francou-Rodier K = {meta.validation.outlet_k["10"]} for the 10-year and {meta.validation.outlet_k["100"]} for the 100-year flood.</li>
        <li>2D solver verified against the analytical normal depth (±5 %) with exact mass balance; HEC-HMS / HEC-RAS cross-check packages are in the repository.</li>
      </ul>
      <figure><img src={`${FIG}phase1_idf.png`} alt="Rainfall depth-duration-frequency curves and storm shape" /><figcaption>Design rainfall: magnitude from ERA5-Land, storm shape from IMERG.</figcaption></figure>
      <figure><img src={`${FIG}phase2_regional_check.png`} alt="Design flood peaks against regional flood envelopes" /><figcaption>Design peaks against Francou-Rodier envelopes and the gauged Ourika floods.</figcaption></figure>
      <h4>Limitations</h4>
      <ul>
        <li>30 m terrain smooths narrow gorges; channels were breached through radar-DSM artefacts.</li>
        <li>No flood-peak record is public for this river: peaks are bounded by regional evidence and the outlet water balance, not calibrated event by event.</li>
        <li>ERA5 and IMERG disagree on some storms; forecasts inherit NWP errors in convective rain.</li>
        <li>Residents per building are estimates; tourists and pupils are not counted as residents.</li>
        <li>A planning and training tool — not a certified operational warning service.</li>
      </ul>
      <h4>Data & credits</h4>
      <p className="small">Copernicus DEM GLO-30 · ESA WorldCover 2021 · OpenLandMap soil texture · ERA5-Land (ECMWF/Copernicus) · GPM IMERG V07 (NASA) · GHCN-Daily (NOAA) · Google Open Buildings via VIDA · OpenStreetMap contributors (ODbL) · GHS-POP (JRC) · WorldPop · Open-Meteo · Esri World Imagery · AWS Terrain Tiles. Hydrological references: Saidi et al. (2006, 2010), Agoussine et al. (2004). Built at the Cassini Hackathon, extended as Atlas v2.</p>
    </div>
  );
}
