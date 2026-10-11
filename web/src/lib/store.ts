import { create } from "zustand";
import type { FloodLayer } from "./raster";

export type Mode = "situation" | "impact" | "act" | "plan" | "community" | "report" | "method";
export type Source =
  | { kind: "forecast" }
  | { kind: "replay"; id: string; title: string }
  | { kind: "scenario" };

interface State {
  mode: Mode;
  source: Source;
  scenario: string | null; // library scenario shown on the map
  t0: string | null; // UTC time of library t = 0 (forecast / replay), null = design scenario
  time: number | null; // hours from library t0; null = maximum envelope
  playing: boolean;
  layer: FloodLayer;
  terrain3d: boolean;
  selectedVillage: string | null;
  panelOpen: boolean;
  fly: { ll: [number, number]; n: number } | null;
  set: (p: Partial<Omit<State, "set">>) => void;
}

export const useStore = create<State>((set) => ({
  mode: "situation",
  source: { kind: "forecast" },
  scenario: null,
  t0: null,
  time: null,
  playing: false,
  layer: "hazard",
  terrain3d: false,
  selectedVillage: null,
  panelOpen: true,
  fly: null,
  set: (p) => set(p),
}));

/** Clock label for a library time (hours from t0). */
export function clock(t0: string | null, h: number, withDay = true) {
  if (!t0) return `+${h.toFixed(1)} h`;
  const d = new Date(Date.parse(t0) + h * 3600e3);
  return d.toLocaleString(undefined, {
    weekday: withDay ? "short" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    day: withDay ? "numeric" : undefined,
    month: withDay ? "short" : undefined,
  });
}
