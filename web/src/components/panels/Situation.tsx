import { useEffect, useState } from "react";
import { useStatic } from "../../lib/useData";
import { useStore, clock } from "../../lib/store";
import { json, type ScenarioImpact } from "../../lib/data";
import type { Forecast, Assessment } from "../../lib/forecast";
import { ForecastChart, HydrographChart } from "../Charts";

interface ReplayItem { id: string; title: string; date: string; p24_mm: number; p24_equivalent_mm: number; scenario: string | null; imerg_24h_mm: number | null }
interface ReplayEvent { id: string; title: string; source: string; assessment: Assessment; hourly: { time: string[]; era5: number[]; imerg_raw: number[] | null } }

const AMC = ["", "dry", "normal", "wet"];

export function scenarioLabel(meta: ReturnType<typeof useStatic>["meta"], name: string | null) {
  if (!name) return "below the flooding threshold";
  const e = meta.library.find((l) => l.name === name);
  return e ? `${e.return_period} flood (${e.p24_mm} mm / 24 h)` : name;
}

export function KeyFigures({ imp }: { imp: ScenarioImpact | undefined }) {
  const { t0 } = useStore();
  if (!imp) return <p className="muted">No flood scenario on the map.</p>;
  const s = imp.summary;
  const first = Math.min(...Object.values(imp.villages).map((v) => v.first_water_h ?? Infinity));
  const tiles: [string, string, string?][] = [
    [`${Math.round(s.people_affected)}`, "residents in flooded buildings"],
    [`${s.buildings_affected}`, "buildings reached by water", `${s.by_hazard.extreme} extreme · ${s.by_hazard.significant} significant`],
    [`${s.villages_isolated.length}`, "villages cut off by road"],
    [`${s.road_km_closed}`, "km of road closed", `${s.fords_closed} fords impassable`],
    [`${s.collapse_possible}`, "houses at risk of collapse"],
    [Number.isFinite(first) ? clock(t0, first, !!t0) : "—", "first water at a village"],
  ];
  return (
    <div className="tiles">
      {tiles.map(([v, l, sub]) => (
        <div className="tile" key={l}><b>{v}</b><span>{l}</span>{sub && <small>{sub}</small>}</div>
      ))}
    </div>
  );
}

export default function Situation({ forecast, impact }: { forecast: Forecast | null; impact: ScenarioImpact | undefined }) {
  const data = useStatic();
  const meta = data.meta;
  const { source, scenario, t0, time, set } = useStore();
  const [tab, setTab] = useState<"forecast" | "replay" | "design">(source.kind === "replay" ? "replay" : source.kind === "scenario" ? "design" : "forecast");
  const [replays, setReplays] = useState<ReplayItem[]>([]);
  const [event, setEvent] = useState<ReplayEvent | null>(null);
  useEffect(() => { json<ReplayItem[]>("replay/index.json").then(setReplays); }, []);

  const ref = forecast?.deterministic[forecast.reference_model];
  const showForecast = () => {
    if (!ref) return;
    set({ source: { kind: "forecast" }, scenario: ref.scenario, t0: ref.library_t0, time: null });
  };
  const openReplay = async (it: ReplayItem) => {
    const ev = await json<ReplayEvent>(`replay/${it.id}.json`);
    setEvent(ev);
    set({ source: { kind: "replay", id: it.id, title: it.title }, scenario: ev.assessment.scenario, t0: ev.assessment.library_t0, time: null });
  };
  const outlet = data.hydrographs.points.find((p) => p.kind === "outlet")!;

  return (
    <div className="panel-body">
      <div className="tabs">
        <button className={tab === "forecast" ? "on" : ""} onClick={() => { setTab("forecast"); showForecast(); }}>Live forecast</button>
        <button className={tab === "replay" ? "on" : ""} onClick={() => setTab("replay")}>Past events</button>
        <button className={tab === "design" ? "on" : ""} onClick={() => setTab("design")}>Design floods</button>
      </div>

      {tab === "forecast" && (forecast && ref ? (
        <section>
          <div className={`alert-card ${forecast.alert.level}`}>
            <b>{forecast.alert.level.toUpperCase()}</b>
            <p>Wettest 24 h in the next 7 days: <b>{ref.p24_mm} mm</b> ({forecast.reference_model}), ending {clock(null, 0) && new Date(ref.window_end).toLocaleString(undefined, { weekday: "short", hour: "2-digit", day: "numeric", month: "short" })}.
              Soils are <b>{AMC[ref.amc]}</b> ({ref.antecedent_5d_mm} mm in the last 5 days), so this behaves like <b>{ref.p24_equivalent_mm} mm</b>: {scenarioLabel(meta, ref.scenario)}.</p>
            <small>Issued {new Date(forecast.issued).toLocaleString()} · {forecast.origin === "live" ? "computed live in your browser" : "server copy (live source unavailable)"}</small>
          </div>
          <h4>Chance of reaching each flood level (ECMWF ensemble, 51 members)</h4>
          <div className="probs">
            {Object.entries(forecast.alert.probabilities).map(([k, p]) => (
              <div key={k} className="prob"><span>{meta.library.find((l) => l.name === k)?.return_period.replace("below 2-year", "minor") ?? k}</span>
                <div className="bar"><i style={{ width: `${p * 100}%` }} /></div><b>{Math.round(p * 100)}%</b></div>
            ))}
          </div>
          <h4>Catchment rain forecast (mm/h, liquid, areal, bias-corrected)</h4>
          <ForecastChart f={forecast} />
          <table className="mini">
            <thead><tr><th>Model</th><th>Max 24 h</th><th>Flood equivalent</th></tr></thead>
            <tbody>{Object.entries(forecast.deterministic).map(([m, a]) => (
              <tr key={m}><td>{m}</td><td>{a.p24_mm} mm</td><td>{a.scenario ?? "none"}</td></tr>))}</tbody>
          </table>
          {!ref.scenario && <p className="muted">No flooding is forecast. To explore impacts, open a past event or a design flood.</p>}
        </section>
      ) : <p className="muted">Loading forecast…</p>)}

      {tab === "replay" && (
        <section>
          <p className="muted">The largest storms over the catchment since 1950 (ERA5-Land, bias-corrected), run through the same forecast logic — use them to exercise the plan.</p>
          <ul className="list">
            {replays.map((it) => (
              <li key={it.id} className={source.kind === "replay" && source.id === it.id ? "on" : ""} onClick={() => openReplay(it)}>
                <b>{it.title}</b>
                <span>{it.p24_mm} mm in 24 h → {it.p24_equivalent_mm} mm equivalent · {scenarioLabel(meta, it.scenario)}</span>
                {it.imerg_24h_mm !== null && <small>Satellite (IMERG, uncorrected): {it.imerg_24h_mm} mm</small>}
              </li>
            ))}
          </ul>
          {event && <p className="muted">{event.source}. Antecedent rain {event.assessment.antecedent_5d_mm} mm (soil {AMC[event.assessment.amc]}).</p>}
        </section>
      )}

      {tab === "design" && (
        <section>
          <p className="muted">Pre-computed floods for design storms (central rainfall). Choose one to see who is affected and when.</p>
          <table className="mini clickable">
            <thead><tr><th>Flood</th><th>Rain 24 h</th><th>People</th><th>Cut off</th></tr></thead>
            <tbody>{meta.library.map((l) => (
              <tr key={l.name} className={scenario === l.name && source.kind === "scenario" ? "on" : ""}
                onClick={() => set({ source: { kind: "scenario" }, scenario: l.name, t0: null, time: null })}>
                <td>{l.return_period}</td><td>{l.p24_mm} mm</td><td>{Math.round(l.people_affected)}</td><td>{l.villages_isolated.length}</td>
              </tr>))}</tbody>
          </table>
        </section>
      )}

      {scenario && (
        <section>
          <h3>{scenarioLabel(meta, scenario)}</h3>
          <KeyFigures imp={impact} />
          <h4>Flow at Aït Ben Haddou (outlet)</h4>
          <HydrographChart h={data.hydrographs} scenario={scenario} pointId={outlet.id} t0={t0} time={time} burst={meta.design_burst_h} />
        </section>
      )}
    </div>
  );
}
