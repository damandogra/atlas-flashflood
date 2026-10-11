import { useCallback, useEffect, useMemo, useState } from "react";
import type { FeatureCollection, LineString, Point } from "geojson";
import { DataContext, loadStatic, useScenario, useStatic, type Static } from "./lib/useData";
import { useStore } from "./lib/store";
import { getForecast, type Forecast } from "./lib/forecast";
import { addReport, listReports, subscribe, type Report } from "./lib/reports";
import MapView from "./components/MapView";
import { Rail, StatusStrip, Timeline, TopBar } from "./components/Layout";
import Situation, { scenarioLabel } from "./components/panels/Situation";
import Impact from "./components/panels/Impact";
import Act from "./components/panels/Act";
import Plan from "./components/panels/Plan";
import Community from "./components/panels/Community";
import Export from "./components/panels/Export";
import Method from "./components/panels/Method";

export default function App() {
  const [data, setData] = useState<Static | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    loadStatic().then(setData).catch((e) => setErr(String(e)));
  }, []);
  if (!data) {
    return (
      <div className="splash">
        <svg viewBox="0 0 32 32" width="40" height="40" aria-hidden><path d="M16 3c5 7 9 11 9 16a9 9 0 0 1-18 0c0-5 4-9 9-16z" fill="var(--accent)" /></svg>
        <p>{err ? `Could not load the data bundle: ${err}` : "Loading the Ounila flood model…"}</p>
      </div>
    );
  }
  return (
    <DataContext.Provider value={data}>
      <Shell />
    </DataContext.Provider>
  );
}

function Shell() {
  const data = useStatic();
  const { mode, scenario, source, panelOpen, set } = useStore();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [route, setRoute] = useState<FeatureCollection<LineString> | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<[number, number] | null>(null);
  const scn = useScenario(scenario);

  useEffect(() => {
    getForecast(data.meta).then((f) => {
      setForecast(f);
      const ref = f.deterministic[f.reference_model];
      if (useStore.getState().source.kind === "forecast") set({ scenario: ref.scenario, t0: ref.library_t0 });
    });
  }, [data, set]);

  const refreshReports = useCallback(() => {
    listReports().then(setReports).catch(() => setReports([]));
  }, []);
  useEffect(() => {
    refreshReports();
    return subscribe(refreshReports);
  }, [refreshReports]);

  const reportFC = useMemo<FeatureCollection<Point>>(() => ({
    type: "FeatureCollection",
    features: reports.map((r) => ({ type: "Feature", properties: { severity: r.severity, kind: r.kind }, geometry: { type: "Point", coordinates: [r.lon, r.lat] } })),
  }), [reports]);

  const flyTo = useCallback((ll: [number, number]) => set({ fly: { ll, n: Date.now() } }), [set]);
  const onPick = picking ? (ll: [number, number]) => { setPicked(ll); setPicking(false); } : undefined;
  const impact = scn?.impact;
  const firstImpact = impact ? Math.min(...Object.values(impact.villages).map((v) => v.first_water_h ?? Infinity)) : Infinity;
  const label = source.kind === "forecast"
    ? `Live forecast · ${scenario ? scenarioLabel(data.meta, scenario) : "no flooding expected"}`
    : source.kind === "replay" ? `Exercise · ${source.title}` : `Design flood · ${scenarioLabel(data.meta, scenario)}`;

  return (
    <div className={`app${panelOpen ? " panel-open" : ""}${picking ? " picking" : ""}`}>
      <TopBar forecast={forecast} sourceLabel={label} />
      <div className="body">
        <Rail />
        <main className="stage">
          <MapView scenario={scn} route={route} reports={reportFC} onPick={onPick} />
          {picking && <div className="pick-hint">Click the map where you observed the situation</div>}
          <StatusStrip impact={impact} />
          <Timeline firstImpact={Number.isFinite(firstImpact) ? firstImpact : null} burst={data.meta.design_burst_h} />
          {scenario && !scn && <div className="loading-chip">Loading flood scenario…</div>}
        </main>
        {panelOpen && (
          <aside className="panel" aria-label={mode}>
            <button className="panel-close" onClick={() => set({ panelOpen: false })} aria-label="Close panel">×</button>
            {mode === "situation" && <Situation forecast={forecast} impact={impact} />}
            {mode === "impact" && <Impact impact={impact} />}
            {mode === "act" && <Act impact={impact} onRoute={setRoute} flyTo={flyTo} />}
            {mode === "plan" && <Plan flyTo={flyTo} />}
            {mode === "community" && <Community reports={reports} picked={picked} onStartPick={() => setPicking(true)}
              onSubmit={async (r) => { await addReport(r); refreshReports(); }} />}
            {mode === "report" && <Export impact={impact} />}
            {mode === "method" && <Method />}
          </aside>
        )}
      </div>
    </div>
  );
}
