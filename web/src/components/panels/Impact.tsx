import { useMemo } from "react";
import { useStatic } from "../../lib/useData";
import { useStore, clock } from "../../lib/store";
import type { ScenarioImpact } from "../../lib/data";
import { HAZARD_COLORS } from "../../lib/raster";
import { HydrographChart } from "../Charts";
import { KeyFigures, scenarioLabel } from "./Situation";

const hc = (k: number) => `rgb(${HAZARD_COLORS[k].join(",")})`;

export default function Impact({ impact }: { impact: ScenarioImpact | undefined }) {
  const data = useStatic();
  const { scenario, t0, time, selectedVillage, set } = useStore();
  const rows = useMemo(() => {
    if (!impact) return [];
    return Object.entries(impact.villages)
      .filter(([, v]) => v.buildings_affected > 0 || v.isolation)
      .sort(([, a], [, b]) => (b.by_hazard.extreme + b.by_hazard.significant) - (a.by_hazard.extreme + a.by_hazard.significant)
        || b.people_affected - a.people_affected || (b.isolation?.hours ?? 0) - (a.isolation?.hours ?? 0));
  }, [impact]);
  if (!scenario || !impact) return <div className="panel-body"><p className="muted">Choose a forecast, past event or design flood in Situation.</p></div>;
  const v = selectedVillage ? impact.villages[selectedVillage] : null;
  const cp = selectedVillage ? data.hydrographs.points.find((p) => selectedVillage.startsWith(p.name) || p.name.startsWith(selectedVillage)) : undefined;

  return (
    <div className="panel-body">
      <h3>{scenarioLabel(data.meta, scenario)}</h3>
      <KeyFigures imp={impact} />
      {v && selectedVillage && (
        <section className="card">
          <div className="card-h"><b>{selectedVillage}</b><button className="x" onClick={() => set({ selectedVillage: null })} aria-label="Close">×</button></div>
          <p>{v.buildings_affected} of {v.buildings} buildings reached by water · ~{Math.round(v.people_affected)} residents</p>
          <div className="haz">{(["extreme", "significant", "moderate", "low"] as const).map((k, i) => (
            <span key={k}><i style={{ background: hc(4 - i) }} />{v.by_hazard[k]} {k}</span>))}</div>
          {v.first_water_h !== null && <p>First water: <b>{clock(t0, v.first_water_h)}</b></p>}
          {v.isolation ? <p className="warn">Cut off by road {clock(t0, v.isolation.from_h)} → {clock(t0, v.isolation.to_h)} ({v.isolation.hours} h)</p> : <p>Road access to the RN9 stays open.</p>}
          {v.collapse_possible > 0 && <p className="warn">{v.collapse_possible} earthen houses at risk of collapse</p>}
          {Object.entries(v.facilities_affected).filter(([, n]) => n).map(([k, n]) => <p key={k}>{n} {k} building{n > 1 ? "s" : ""} affected</p>)}
          {cp && <><h4>Flow at {cp.name} ({cp.drainage_km2} km²)</h4>
            <HydrographChart h={data.hydrographs} scenario={scenario} pointId={cp.id} t0={t0} time={time} burst={data.meta.design_burst_h} /></>}
        </section>
      )}
      <h4>Villages affected ({rows.length})</h4>
      <table className="mini clickable">
        <thead><tr><th>Village</th><th>Hazard</th><th>People</th><th>Water</th><th>Cut off</th></tr></thead>
        <tbody>{rows.map(([name, r]) => (
          <tr key={name} className={selectedVillage === name ? "on" : ""} onClick={() => set({ selectedVillage: name })}>
            <td>{name === "(isolated buildings)" ? "Outlying buildings" : name}</td>
            <td><span className="hbar">{([4, 3, 2, 1] as const).map((k) => {
              const n = r.by_hazard[(["", "low", "moderate", "significant", "extreme"] as const)[k] as "low"];
              return n ? <i key={k} style={{ background: hc(k), flexGrow: n }} title={`${n}`} /> : null;
            })}</span>{r.buildings_affected}</td>
            <td>{Math.round(r.people_affected)}</td>
            <td>{r.first_water_h !== null ? clock(t0, r.first_water_h, false) : "—"}</td>
            <td>{r.isolation ? `${r.isolation.hours} h` : "—"}</td>
          </tr>))}</tbody>
      </table>
      <p className="muted small">Residents are estimates: catchment population (GHS-POP / WorldPop 2020, ≈15,600) spread over building footprints. Hazard classes follow DEFRA FD2320; road safety follows Australian Rainfall & Runoff (2019) vehicle limits.</p>
    </div>
  );
}
