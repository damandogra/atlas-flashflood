import { useEffect, useState } from "react";
import { json } from "../../lib/data";

interface Totals { outlet_peak_m3s?: number; buildings_affected: number; people_affected: number; collapse_possible: number }
interface Measure extends Totals { description: string; peak_reduction_pct: number; avoided: Omit<Totals, "outlet_peak_m3s"> }
interface Link { segment: number; village_hours_charged: number; ford: boolean; highway: string; label: string; max_depth_m: number; lonlat: [number, number] }
interface Mitigation {
  headwater_area_km2: number;
  measures: Record<string, {
    baseline: Totals;
    restoration: Measure;
    check_dams: Measure;
    crossings: { description: string; baseline_village_hours: number; with_works_village_hours: number; baseline_isolated: string[]; reconnected: string[]; ranked_links: Link[]; flood_proofed: number[] };
  }>;
}

export default function Plan({ flyTo }: { flyTo: (ll: [number, number]) => void }) {
  const [m, setM] = useState<Mitigation | null>(null);
  const [scn, setScn] = useState("T10");
  const [cost, setCost] = useState({ restoration: "", check_dams: "", crossings: "" });
  useEffect(() => { json<Mitigation>("mitigation.json").then(setM); }, []);
  if (!m) return <div className="panel-body"><p className="muted">Loading…</p></div>;
  const r = m.measures[scn];
  const per = (c: string, n: number) => (c && n > 0 ? `${(Number(c) / n).toLocaleString(undefined, { maximumFractionDigits: 0 })} per unit avoided` : "");
  const top = r.crossings.ranked_links.slice(0, 10);

  return (
    <div className="panel-body">
      <h3>Mitigation planning</h3>
      <p className="muted small">Each measure is run through the models (hydrology → 2D library → impacts), not estimated with rules of thumb. No costs are assumed: enter local unit costs to compare cost-effectiveness.</p>
      <div className="tabs">
        {Object.keys(m.measures).map((k) => <button key={k} className={scn === k ? "on" : ""} onClick={() => setScn(k)}>{k === "T10" ? "10-year flood" : "100-year flood"}</button>)}
      </div>
      <p>Without measures: outlet peak <b>{r.baseline.outlet_peak_m3s} m³/s</b>, {Math.round(r.baseline.buildings_affected)} buildings and ~{Math.round(r.baseline.people_affected)} residents affected, {r.crossings.baseline_isolated.length} villages cut off ({r.crossings.baseline_village_hours} village-hours).</p>

      <section className="card">
        <b>1 · Flood-proof the critical road links</b>
        <p className="small">{r.crossings.description}. Villages lose access through several flooded sections at once, so links are ranked by the isolation hours on each village's normal route to the RN9.</p>
        <p className="big">{r.crossings.baseline_village_hours} → <b>{r.crossings.with_works_village_hours}</b> village-hours cut off · {r.crossings.reconnected.length} of {r.crossings.baseline_isolated.length} villages keep access</p>
        {r.crossings.reconnected.length > 0 && <p className="small">Reconnected: {r.crossings.reconnected.join(", ")}</p>}
        <ol className="links">{top.map((l) => (
          <li key={l.segment} onClick={() => flyTo(l.lonlat)}>{l.label}{l.ford ? " (ford)" : ""} — {l.village_hours_charged} village-hours, {l.max_depth_m} m of water</li>))}</ol>
        <label className="cost">Cost of the works <input inputMode="decimal" value={cost.crossings} onChange={(e) => setCost({ ...cost, crossings: e.target.value })} placeholder="MAD" /></label>
        <small>{per(cost.crossings, r.crossings.baseline_village_hours - r.crossings.with_works_village_hours).replace("unit", "village-hour")}</small>
      </section>

      <section className="card">
        <b>2 · Rangeland restoration / reforestation of the headwaters</b>
        <p className="small">{r.restoration.description} — lower Curve Number from better cover.</p>
        <p className="big">Peak −{r.restoration.peak_reduction_pct}% · {Math.round(r.restoration.avoided.buildings_affected)} fewer buildings, ~{Math.round(r.restoration.avoided.people_affected)} fewer residents affected</p>
        <label className="cost">Cost <input inputMode="decimal" value={cost.restoration} onChange={(e) => setCost({ ...cost, restoration: e.target.value })} placeholder="MAD" /></label>
        <small>{per(cost.restoration, r.restoration.avoided.buildings_affected).replace("unit", "building")}</small>
      </section>

      <section className="card">
        <b>3 · Check-dam series in the headwaters</b>
        <p className="small">{r.check_dams.description}.</p>
        <p className="big">Peak {r.check_dams.peak_reduction_pct > 0 ? "−" : ""}{Math.abs(r.check_dams.peak_reduction_pct)}% — negligible for floods of this size</p>
        <p className="small">Their storage is small next to a flood volume of millions of m³: they are worth building against erosion and sediment, not to lower flood peaks.</p>
      </section>
    </div>
  );
}
