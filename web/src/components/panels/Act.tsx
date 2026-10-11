import { useEffect, useMemo, useState } from "react";
import type { FeatureCollection, LineString } from "geojson";
import { useStatic } from "../../lib/useData";
import { useStore, clock } from "../../lib/store";
import type { Action, ScenarioImpact } from "../../lib/data";
import { unsafeAt } from "../../lib/routing";

const PRIO = { CRITICAL: "crit", HIGH: "high", MEDIUM: "med" } as const;

function storageKey(src: string, scn: string) {
  return `atlas-done:${src}:${scn}`;
}

export default function Act({ impact, onRoute, flyTo }: {
  impact: ScenarioImpact | undefined;
  onRoute: (fc: FeatureCollection<LineString> | null) => void;
  flyTo: (ll: [number, number]) => void;
}) {
  const data = useStatic();
  const { scenario, t0, time, source, selectedVillage, set } = useStore();
  const src = source.kind === "replay" ? `replay-${source.id}` : source.kind;
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [prio, setPrio] = useState<"ALL" | Action["priority"]>("ALL");
  const [routeInfo, setRouteInfo] = useState<string | null>(null);

  useEffect(() => {
    if (!scenario) return;
    try { setDone(JSON.parse(localStorage.getItem(storageKey(src, scenario)) ?? "{}")); } catch { setDone({}); }
  }, [src, scenario]);
  const toggle = (k: string) => {
    const next = { ...done, [k]: !done[k] };
    setDone(next);
    try { localStorage.setItem(storageKey(src, scenario!), JSON.stringify(next)); } catch { /* per-viewer convenience only */ }
  };

  const actions = useMemo(() => (impact?.actions ?? []).filter((a) => prio === "ALL" || a.priority === prio), [impact, prio]);
  useEffect(() => () => onRoute(null), [onRoute]);
  if (!scenario || !impact) return <div className="panel-body"><p className="muted">Choose a forecast, past event or design flood in Situation.</p></div>;

  const routeFrom = (village: string) => {
    const vf = data.villages.features.find((f) => f.properties.name === village);
    if (!vf) return;
    const [lon, lat] = vf.geometry.coordinates;
    const from = data.graph.nearest(lon, lat);
    const targets = new Set(data.shelters.features.map((s) => data.graph.nearest(s.geometry.coordinates[0], s.geometry.coordinates[1])!).filter(Boolean));
    const v = impact.villages[village];
    const tq = time ?? (v?.first_water_h ?? null);
    const r = from ? data.graph.route(from, targets, (seg) => unsafeAt(impact, seg, tq)) : null;
    if (!r) {
      onRoute(null);
      setRouteInfo(`No safe route from ${village} to a dry shelter at ${tq === null ? "peak" : clock(t0, tq)} — shelter in place on high ground.`);
      return;
    }
    const fc: FeatureCollection<LineString> = { type: "FeatureCollection", features: r.segments.map((i) => data.roads.features[i]) as FeatureCollection<LineString>["features"] };
    onRoute(fc);
    const shelter = data.shelters.features.find((s) => data.graph.nearest(s.geometry.coordinates[0], s.geometry.coordinates[1]) === r.target);
    setRouteInfo(`${village} → ${shelter?.properties.name || shelter?.properties.kind} (${shelter?.properties.village}): ${(r.length_m / 1000).toFixed(1)} km, ~${Math.round(r.length_m / 1000 / 4 * 60)} min on foot, avoiding roads unsafe at ${tq === null ? "the peak" : clock(t0, tq)}.`);
  };

  const owners = [...new Set(actions.map((a) => a.owner.split(/[+/]/)[0].trim()))];
  const csv = () => {
    const rows = [["deadline", "priority", "owner", "action", "where", "reason", "lon", "lat"],
      ...actions.map((a) => [clock(t0, a.deadline_h), a.priority, a.owner, a.title, a.where, a.reason, a.lonlat?.[0] ?? "", a.lonlat?.[1] ?? ""])];
    const blob = new Blob([rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `atlas-actions-${scenario}.csv`;
    a.click();
  };

  return (
    <div className="panel-body">
      <h3>Early-action plan</h3>
      <p className="muted small">Generated from the playbook (pipeline/impact/playbook.yaml) for this flood. Deadlines are {t0 ? "clock times for this forecast/event" : "hours from the start of the design storm"}.</p>
      <div className="row">
        <select value={prio} onChange={(e) => setPrio(e.target.value as typeof prio)}>
          <option value="ALL">All priorities</option><option value="CRITICAL">Critical</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option>
        </select>
        <button className="tbtn" onClick={csv}>Download CSV</button>
      </div>
      <section className="card">
        <b>Evacuation route</b>
        <div className="row">
          <select value={selectedVillage ?? ""} onChange={(e) => set({ selectedVillage: e.target.value || null })}>
            <option value="">Choose a village…</option>
            {Object.entries(impact.villages).filter(([, v]) => v.buildings_affected > 0).map(([n]) => <option key={n} value={n}>{n}</option>)}
          </select>
          <button className="tbtn" disabled={!selectedVillage} onClick={() => selectedVillage && routeFrom(selectedVillage)}>Route to shelter</button>
        </div>
        {routeInfo && <p className="small">{routeInfo}</p>}
      </section>
      <p className="small muted">{actions.length} actions · owners: {owners.join(", ")}</p>
      <ul className="actions">
        {actions.map((a, i) => {
          const k = `${a.id}|${a.where}|${i}`;
          const overdue = time !== null && time > a.deadline_h && !done[k];
          return (
            <li key={k} className={`${done[k] ? "done" : ""} ${overdue ? "overdue" : ""}`}>
              <input type="checkbox" checked={!!done[k]} onChange={() => toggle(k)} aria-label="Done" />
              <div onClick={() => a.lonlat && flyTo(a.lonlat)}>
                <div className="a-h"><span className={`prio ${PRIO[a.priority]}`}>{a.priority}</span><b>{clock(t0, a.deadline_h, !!t0)}</b><span className="where">{a.where}</span></div>
                <p>{a.title}</p>
                <small>{a.owner} · {a.reason}</small>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
