import { useEffect } from "react";
import { useStore, clock, type Mode } from "../lib/store";
import type { Forecast } from "../lib/forecast";
import type { FloodLayer } from "../lib/raster";

const ALERT_TEXT: Record<string, string> = {
  green: "No flood impacts expected",
  yellow: "Watch: minor flooding possible",
  orange: "Warning: damaging floods likely",
  red: "Emergency: severe flooding expected",
};

export function TopBar({ forecast, sourceLabel }: { forecast: Forecast | null; sourceLabel: string }) {
  const { layer, terrain3d, source, set } = useStore();
  const level = source.kind === "forecast" ? forecast?.alert.level : null;
  return (
    <header className="topbar">
      <div className="brand">
        <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden><path d="M16 3c5 7 9 11 9 16a9 9 0 0 1-18 0c0-5 4-9 9-16z" fill="var(--accent)" /></svg>
        <div><b>Atlas</b><small>Ounila flash-flood DSS</small></div>
      </div>
      {level && (
        <div className={`alert-chip ${level}`} title="Impact-based alert from the ECMWF ensemble">
          <span className="pulse" />
          <b>{level.toUpperCase()}</b>
          <span className="hide-sm">{ALERT_TEXT[level]}</span>
        </div>
      )}
      <div className="source-chip" title="What the map is showing">{sourceLabel}</div>
      <div className="spacer" />
      <label className="sel">
        <span className="hide-sm">Layer</span>
        <select value={layer} onChange={(e) => set({ layer: e.target.value as FloodLayer })}>
          <option value="hazard">Hazard to people</option>
          <option value="depth">Water depth</option>
          <option value="velocity">Velocity</option>
          <option value="arrival">Arrival time</option>
        </select>
      </label>
      <button className={`tbtn${terrain3d ? " on" : ""}`} onClick={() => set({ terrain3d: !terrain3d })} title="3D terrain">3D</button>
    </header>
  );
}

const MODES: [Mode, string, string][] = [
  ["situation", "Situation", "M12 3v3m0 12v3M3 12h3m12 0h3M6 6l2 2m8 8 2 2M6 18l2-2m8-8 2-2"],
  ["impact", "Impact", "M3 20h18M5 20V9l7-5 7 5v11M9 20v-6h6v6"],
  ["act", "Act", "M9 11l3 3 8-8M4 12a8 8 0 1 0 16 0"],
  ["plan", "Plan", "M4 19V5m0 14h16M8 15l3-4 3 2 5-6"],
  ["community", "Reports", "M4 5h16v10H8l-4 4z"],
  ["report", "Export", "M12 4v11m0 0-4-4m4 4 4-4M5 20h14"],
  ["method", "Method", "M12 8h.01M11 12h1v5h1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z"],
];

export function Rail() {
  const { mode, panelOpen, set } = useStore();
  return (
    <nav className="rail" aria-label="Workflow">
      {MODES.map(([m, label, d]) => (
        <button key={m} className={mode === m && panelOpen ? "on" : ""} onClick={() => set({ mode: m, panelOpen: mode === m ? !panelOpen : true })}>
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden><path d={d} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

export function Timeline({ firstImpact, burst }: { firstImpact: number | null; burst: number }) {
  const { time, t0, playing, set, scenario } = useStore();
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const cur = useStore.getState().time ?? 6;
      set({ time: cur >= 36 ? 6 : +(cur + 0.5).toFixed(1) });
    }, 450);
    return () => clearInterval(id);
  }, [playing, set]);
  if (!scenario) return null;
  const pct = (h: number) => `${(h / 36) * 100}%`;
  return (
    <div className="timeline">
      <button className="play" onClick={() => set({ playing: !playing, time: time ?? 6 })} aria-label={playing ? "Pause" : "Play"}>
        {playing ? "❚❚" : "▶"}
      </button>
      <div className="track">
        <input type="range" min={0} max={36} step={0.5} value={time ?? 36}
          onChange={(e) => set({ time: +e.target.value, playing: false })} aria-label="Time" />
        <i className="mark burst" style={{ left: pct(burst) }} title="Peak of the rain" />
        {firstImpact !== null && <i className="mark impact" style={{ left: pct(firstImpact) }} title="First modelled impact" />}
      </div>
      <div className="tlabel">
        {time === null ? <b>Maximum extent</b> : <b>{clock(t0, time)}</b>}
        <small>{time === null ? "whole event" : t0 ? `${(time - burst >= 0 ? "+" : "")}${(time - burst).toFixed(1)} h from rain peak` : `${(time - burst).toFixed(1)} h from rain peak`}</small>
      </div>
      <button className={`tbtn${time === null ? " on" : ""}`} onClick={() => set({ time: null, playing: false })}>Max</button>
    </div>
  );
}
