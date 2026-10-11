// Live forecast in the browser - same logic as pipeline/forecast/core.py + live.py.
// Falls back to data/forecast/latest.json (written every 6 h by GitHub Actions) if Open-Meteo is unreachable.
import { json, type Meta } from "./data";

export interface Assessment {
  p24_mm: number;
  window_end: string;
  peak_hour: string;
  antecedent_5d_mm: number;
  amc: number;
  p24_equivalent_mm: number;
  scenario: string | null;
  next_scenario: string | null;
  library_t0: string;
}

export interface Forecast {
  issued: string;
  source: string;
  origin: "live" | "server";
  antecedent_5d_mm: number;
  alert: { level: "green" | "yellow" | "orange" | "red"; probabilities: Record<string, number> };
  deterministic: Record<string, Assessment>;
  reference_model: string;
  ensemble_p24_equivalent_mm: number[];
  hourly: { time: string[]; ens_p10: number[]; ens_p50: number[]; ens_p90: number[]; [model: string]: (number | string)[] };
}

const MODELS: Record<string, string> = { ecmwf_ifs025: "ECMWF IFS", gfs_seamless: "NOAA GFS", icon_seamless: "DWD ICON" };
const REFERENCE = "ecmwf_ifs025";

function cnAmc(cn: number, amc: number) {
  if (amc === 1) return (4.2 * cn) / (10 - 0.058 * cn);
  if (amc === 3) return (23 * cn) / (10 + 0.13 * cn);
  return cn;
}

function basinRunoff(meta: Meta, p: number, amc: number) {
  let q = 0, a = 0;
  for (const sb of meta.subbasins) {
    const s = 25400 / cnAmc(sb.cn, amc) - 254;
    q += (p > 0.2 * s ? (p - 0.2 * s) ** 2 / (p + 0.8 * s) : 0) * sb.area_km2;
    a += sb.area_km2;
  }
  return q / a;
}

export function amcClass(meta: Meta, antecedent: number) {
  const [lo, hi] = meta.amc_limits_mm;
  return antecedent < lo ? 1 : antecedent > hi ? 3 : 2;
}

export function equivalentDepth(meta: Meta, p24: number, amc: number) {
  if (amc === 2 || p24 <= 0) return p24;
  const target = basinRunoff(meta, p24, amc);
  if (target <= 0) return 0;
  let lo = 0, hi = 400;
  for (let k = 0; k < 60; k++) {
    const mid = (lo + hi) / 2;
    if (basinRunoff(meta, mid, 2) < target) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

export function matchScenario(meta: Meta, p24eq: number): [string | null, string | null] {
  const lib = meta.library;
  let k = -1;
  for (let i = 0; i < lib.length; i++) if (lib[i].p24_mm <= p24eq) k = i;
  return [k >= 0 ? lib[k].name : null, k + 1 < lib.length ? lib[k + 1].name : null];
}

const rank = (meta: Meta, name: string | null) => (name ? meta.library.findIndex((l) => l.name === name) : -1);

export function assess(meta: Meta, time: string[], hourly: number[], antecedent: number): Assessment {
  let best = -1, end = 0;
  for (let i = 0; i < hourly.length; i++) {
    let s = 0;
    for (let j = Math.max(0, i - 23); j <= i; j++) s += hourly[j];
    if (s > best) { best = s; end = i; }
  }
  let peak = end;
  for (let j = Math.max(0, end - 23); j <= end; j++) if (hourly[j] > hourly[peak]) peak = j;
  const amc = amcClass(meta, antecedent);
  const p24eq = equivalentDepth(meta, best, amc);
  const [scenario, next] = matchScenario(meta, p24eq);
  const t0 = new Date(Date.parse(time[peak]) - meta.design_burst_h * 3600e3).toISOString();
  return {
    p24_mm: +best.toFixed(1), window_end: time[end], peak_hour: time[peak], antecedent_5d_mm: +antecedent.toFixed(1),
    amc, p24_equivalent_mm: +p24eq.toFixed(1), scenario, next_scenario: next, library_t0: t0,
  };
}

export function alertLevel(meta: Meta, det: Assessment, members: Assessment[]) {
  const probabilities: Record<string, number> = {};
  for (const scn of ["P25", "T2", "T5", "T10", "T25", "T50", "T100"]) {
    if (rank(meta, scn) < 0 || !members.length) continue;
    probabilities[scn] = members.filter((m) => rank(meta, m.scenario) >= rank(meta, scn)).length / members.length;
  }
  let level: Forecast["alert"]["level"] = "green";
  for (const lv of ["red", "orange", "yellow"] as const) {
    const r = meta.alert_rules[lv];
    if ((probabilities[r.scenario] ?? 0) >= r.prob || rank(meta, det.scenario) >= rank(meta, r.deterministic)) {
      level = lv;
      break;
    }
  }
  return { level, probabilities };
}

const UTC = (t: string) => (t.endsWith("Z") ? t : `${t}Z`);

export async function liveForecast(meta: Meta): Promise<Forecast> {
  const pts = meta.rain_points;
  const lat = pts.map((p) => p.lat.toFixed(3)).join(","), lon = pts.map((p) => p.lon.toFixed(3)).join(",");
  const q = (o: Record<string, string>) => new URLSearchParams(o).toString();
  const [f, e] = await Promise.all([
    fetch(`https://api.open-meteo.com/v1/forecast?${q({ latitude: lat, longitude: lon, hourly: "rain,showers,snowfall", models: Object.keys(MODELS).join(","), past_days: "5", forecast_days: "7", timezone: "UTC" })}`).then((r) => r.json()),
    fetch(`https://ensemble-api.open-meteo.com/v1/ensemble?${q({ latitude: lat, longitude: lon, hourly: "precipitation,snowfall", models: "ecmwf_ifs025", forecast_days: "7", timezone: "UTC" })}`).then((r) => r.json()),
  ]);
  const fa = Array.isArray(f) ? f : [f], ea = Array.isArray(e) ? e : [e];
  if (!fa[0]?.hourly) throw new Error("Open-Meteo forecast unavailable");
  const cf = meta.correction_factor;
  const time: string[] = fa[0].hourly.time.map(UTC);
  const areal = (rows: number[][]) => time.map((_, i) => rows.reduce((s, r, k) => s + pts[k].w * (r[i] ?? 0), 0));
  const det: Record<string, number[]> = {};
  for (const m of Object.keys(MODELS)) {
    det[m] = areal(fa.map((p) => p.hourly[`rain_${m}`].map((v: number | null, i: number) => (v ?? 0) + (p.hourly[`showers_${m}`][i] ?? 0))));
  }
  const now = Date.now() - (Date.now() % 3600e3);
  const k0 = time.findIndex((t) => Date.parse(t) >= now);
  const antecedent = det[REFERENCE].slice(Math.max(0, k0 - 120), k0).reduce((a, b) => a + b, 0) * cf;
  const futT = time.slice(k0);
  const assessments: Record<string, Assessment> = {};
  const hourly: Forecast["hourly"] = { time: futT, ens_p10: [], ens_p50: [], ens_p90: [] };
  for (const [m, name] of Object.entries(MODELS)) {
    const s = det[m].slice(k0).map((v) => v * cf);
    assessments[name] = assess(meta, futT, s, antecedent);
    hourly[name] = s.map((v) => +v.toFixed(2));
  }
  const et: string[] = ea[0].hourly.time.map(UTC);
  const e0 = et.findIndex((t) => Date.parse(t) >= now);
  const keys = Object.keys(ea[0].hourly).filter((k) => k.startsWith("precipitation"));
  const members = keys.map((k) => {
    const sk = k.replace("precipitation", "snowfall");
    const rows = ea.map((p) => p.hourly[k].map((v: number | null, i: number) => Math.max((v ?? 0) - (p.hourly[sk]?.[i] ?? 0) * 10 / 7, 0)));
    return et.map((_, i) => rows.reduce((s: number, r: number[], j: number) => s + pts[j].w * r[i], 0) * cf).slice(e0);
  });
  const ens = members.map((s) => assess(meta, et.slice(e0), s, antecedent));
  for (let i = 0; i < futT.length; i++) {
    const v = members.map((s) => s[i] ?? 0).sort((a, b) => a - b);
    const pct = (p: number) => +(v[Math.min(v.length - 1, Math.floor(p * v.length))] ?? 0).toFixed(2);
    hourly.ens_p10.push(pct(0.1));
    hourly.ens_p50.push(pct(0.5));
    hourly.ens_p90.push(pct(0.9));
  }
  return {
    issued: new Date(now).toISOString(), source: "Open-Meteo (live, in your browser): ECMWF IFS, NOAA GFS, DWD ICON + ECMWF ENS 51",
    origin: "live", antecedent_5d_mm: +antecedent.toFixed(1), alert: alertLevel(meta, assessments[MODELS[REFERENCE]], ens),
    deterministic: assessments, reference_model: MODELS[REFERENCE],
    ensemble_p24_equivalent_mm: ens.map((a) => a.p24_equivalent_mm).sort((a, b) => a - b), hourly,
  };
}

export async function getForecast(meta: Meta): Promise<Forecast> {
  try {
    return await liveForecast(meta);
  } catch {
    const f = await json<Omit<Forecast, "origin">>("forecast/latest.json");
    return { ...f, origin: "server" };
  }
}
