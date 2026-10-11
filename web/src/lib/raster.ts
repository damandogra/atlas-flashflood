// Flood raster: geolocation, point queries and colouring for the map.
import type { ScenarioRasters } from "./data";

export type FloodLayer = "depth" | "hazard" | "velocity" | "arrival";

/** Affine frame of the raster from its top-left, top-right and bottom-left corners (lon/lat). */
export function frame(corners: [number, number][], width: number, height: number) {
  const [tl, tr, , bl] = corners;
  const ax = tr[0] - tl[0], ay = tr[1] - tl[1];
  const bx = bl[0] - tl[0], by = bl[1] - tl[1];
  const det = ax * by - ay * bx;
  return (lon: number, lat: number): [number, number] | null => {
    const dx = lon - tl[0], dy = lat - tl[1];
    const u = (dx * by - dy * bx) / det;
    const v = (ax * dy - ay * dx) / det;
    if (u < 0 || u >= 1 || v < 0 || v >= 1) return null;
    return [Math.floor(u * width), Math.floor(v * height)];
  };
}

export interface CellValues {
  depth: number;
  velocity: number;
  firstWater: number | null; // h from storm start, water > 0.1 m
  firstWater03: number | null;
  duration03: number;
  hazard: number; // DEFRA HR for people in the open
}

/** DEFRA FD2320 hazard rating with the pasture/arable debris factor (people outside buildings). */
export function hazardRating(depth: number, hv: number) {
  const df = depth > 0.75 ? 0.5 : 0;
  return depth >= 0.1 ? hv + df : 0;
}

export function hazardClass(hr: number) {
  if (hr <= 0) return 0;
  if (hr < 0.75) return 1;
  if (hr < 1.25) return 2;
  if (hr < 2) return 3;
  return 4;
}

export function query(r: ScenarioRasters, col: number, row: number): CellValues {
  const i = (row * r.flood.width + col) * 4;
  const f = r.flood.data, t = r.time.data;
  const depth = f[i] / 40;
  const hv = t[i + 2] / 40;
  return {
    depth,
    velocity: f[i + 1] / 40,
    firstWater: f[i + 2] ? f[i + 2] / 5 : null,
    firstWater03: t[i] ? t[i] / 5 : null,
    duration03: t[i + 1] / 5,
    hazard: hazardRating(depth, hv),
  };
}

/** Is a cell wet at time t (h from storm start)? Flooded from first water until the >0.3 m period ends
 *  (or one hour after first water for shallow cells), plus one hour of recession. */
export function wetAt(first01: number, first03: number, dur03: number, t: number) {
  if (!first01 || t < first01) return false;
  const end = first03 ? first03 + dur03 : first01 + 1;
  return t <= end + 1;
}

const DEPTH_RAMP: [number, [number, number, number]][] = [
  [0.1, [198, 225, 255]],
  [0.5, [107, 174, 214]],
  [1.0, [49, 130, 189]],
  [2.0, [8, 81, 156]],
  [4.0, [8, 48, 107]],
];
export const HAZARD_COLORS: [number, number, number][] = [
  [0, 0, 0],
  [246, 213, 92], // low
  [244, 145, 54], // moderate
  [214, 40, 40], // significant
  [110, 25, 105], // extreme
];
export const HAZARD_NAMES = ["dry", "Low", "Moderate", "Significant", "Extreme"];

function ramp(stops: [number, [number, number, number]][], v: number): [number, number, number] {
  if (v <= stops[0][0]) return stops[0][1];
  for (let k = 1; k < stops.length; k++) {
    if (v <= stops[k][0]) {
      const [a, ca] = stops[k - 1], [b, cb] = stops[k];
      const w = (v - a) / (b - a);
      return [0, 1, 2].map((j) => Math.round(ca[j] + w * (cb[j] - ca[j]))) as [number, number, number];
    }
  }
  return stops[stops.length - 1][1];
}

const VEL_RAMP: [number, [number, number, number]][] = [
  [0.25, [255, 237, 160]], [1, [254, 178, 76]], [2, [240, 59, 32]], [4, [128, 0, 38]],
];
const ARR_RAMP: [number, [number, number, number]][] = [
  [-1, [180, 4, 38]], [1, [244, 109, 67]], [3, [254, 224, 144]], [6, [171, 217, 233]], [10, [69, 117, 180]],
];

/** Paint the raster for a layer at time t (null = maximum envelope) into an RGBA buffer. */
export function paint(r: ScenarioRasters, layer: FloodLayer, t: number | null, burstH: number, out: Uint8ClampedArray) {
  const f = r.flood.data, tm = r.time.data;
  for (let i = 0; i < f.length; i += 4) {
    const depth = f[i];
    if (depth < 4 || (t !== null && !wetAt(f[i + 2] / 5, tm[i] / 5, tm[i + 1] / 5, t))) {
      out[i + 3] = 0;
      continue;
    }
    let c: [number, number, number];
    if (layer === "depth") c = ramp(DEPTH_RAMP, depth / 40);
    else if (layer === "velocity") c = ramp(VEL_RAMP, f[i + 1] / 40);
    else if (layer === "hazard") c = HAZARD_COLORS[hazardClass(hazardRating(depth / 40, tm[i + 2] / 40))];
    else c = ramp(ARR_RAMP, f[i + 2] / 5 - burstH);
    out[i] = c[0];
    out[i + 1] = c[1];
    out[i + 2] = c[2];
    out[i + 3] = 215;
  }
}

export const LEGENDS: Record<FloodLayer, { title: string; items: [string, string][] }> = {
  depth: {
    title: "Water depth",
    items: DEPTH_RAMP.map(([v, c], k) => [`rgb(${c})`, k === DEPTH_RAMP.length - 1 ? `> ${v} m` : `${v} m`]),
  },
  velocity: { title: "Water speed", items: VEL_RAMP.map(([v, c]) => [`rgb(${c})`, `${v} m/s`]) },
  hazard: {
    title: "Danger to people in the water",
    items: [
      [`rgb(${HAZARD_COLORS[1]})`, "Low — caution"],
      [`rgb(${HAZARD_COLORS[2]})`, "Moderate — dangerous for children"],
      [`rgb(${HAZARD_COLORS[3]})`, "Significant — dangerous for most"],
      [`rgb(${HAZARD_COLORS[4]})`, "Extreme — dangerous for all"],
    ],
  },
  arrival: {
    title: "When water arrives (after the rain peak)",
    items: ARR_RAMP.map(([v, c]) => [`rgb(${c})`, v < 0 ? "before" : `+${v} h`]),
  },
};
