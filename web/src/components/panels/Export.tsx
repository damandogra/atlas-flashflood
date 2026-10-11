import { useState } from "react";
import { useStatic } from "../../lib/useData";
import { useStore, clock } from "../../lib/store";
import { DATA, type ScenarioImpact } from "../../lib/data";
import { KeyFigures, scenarioLabel } from "./Situation";

export default function Export({ impact }: { impact: ScenarioImpact | undefined }) {
  const data = useStatic();
  const { scenario, t0, source } = useStore();
  const [snap, setSnap] = useState<string | null>(null);
  const print = () => {
    const c = document.querySelector("canvas.maplibregl-canvas") as HTMLCanvasElement | null;
    try { setSnap(c ? c.toDataURL("image/jpeg", 0.85) : null); } catch { setSnap(null); }
    setTimeout(() => window.print(), 150);
  };
  const files: [string, string][] = [
    ["Scenario impacts (JSON)", scenario ? `scenarios/${scenario}/impact.json` : ""],
    ["Buildings (GeoJSON)", "geo/buildings.geojson"],
    ["Roads and fords (GeoJSON)", "geo/roads.geojson"],
    ["Catchment and sub-basins (GeoJSON)", "geo/subbasins.geojson"],
    ["Shelters (GeoJSON)", "geo/shelters.geojson"],
    ["Hydrographs at control points (JSON)", "hydrographs.json"],
    ["Mitigation results (JSON)", "mitigation.json"],
    ["Latest forecast (JSON)", "forecast/latest.json"],
  ];
  return (
    <div className="panel-body">
      <h3>Situation report</h3>
      <p className="muted small">Prints the map as it is on screen with the key figures, the most urgent actions and the affected villages. Use "Save as PDF" in the print dialog.</p>
      <button className="primary" disabled={!scenario} onClick={print}>Print / save PDF</button>
      <div className="print-only print-report">
        <h1>Atlas · Ounila valley flood situation report</h1>
        <p>{source.kind === "forecast" ? "Live forecast" : source.kind === "replay" ? `Exercise: ${source.title}` : "Design scenario"} · {scenarioLabel(data.meta, scenario)} · printed {new Date().toLocaleString()}</p>
        {snap && <img className="snap" src={snap} alt="Map at the time of printing" />}
        <KeyFigures imp={impact} />
        <h2>Most urgent actions</h2>
        <table className="mini"><thead><tr><th>Deadline</th><th>Priority</th><th>Action</th><th>Where</th><th>Owner</th></tr></thead>
          <tbody>{(impact?.actions ?? []).filter((a) => a.priority === "CRITICAL").slice(0, 25).map((a, i) => (
            <tr key={i}><td>{clock(t0, a.deadline_h)}</td><td>{a.priority}</td><td>{a.title}</td><td>{a.where}</td><td>{a.owner}</td></tr>))}</tbody></table>
        <h2>Villages</h2>
        <table className="mini"><thead><tr><th>Village</th><th>Buildings</th><th>Residents</th><th>First water</th><th>Cut off</th></tr></thead>
          <tbody>{Object.entries(impact?.villages ?? {}).filter(([, v]) => v.buildings_affected || v.isolation).map(([n, v]) => (
            <tr key={n}><td>{n}</td><td>{v.buildings_affected}</td><td>{Math.round(v.people_affected)}</td>
              <td>{v.first_water_h !== null ? clock(t0, v.first_water_h) : "—"}</td><td>{v.isolation ? `${clock(t0, v.isolation.from_h)} (${v.isolation.hours} h)` : "—"}</td></tr>))}</tbody></table>
        <p className="small">Model results for planning support — not a certified operational warning. Sources and methods: see the Method page.</p>
      </div>
      <h4>Data downloads</h4>
      <ul className="dl">{files.filter(([, f]) => f).map(([l, f]) => <li key={f}><a href={DATA + f} download>{l}</a></li>)}</ul>
    </div>
  );
}
