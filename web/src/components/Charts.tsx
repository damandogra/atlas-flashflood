import { Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Forecast } from "../lib/forecast";
import type { Hydrographs } from "../lib/data";
import { clock } from "../lib/store";

const AX = { fontSize: 11, fill: "var(--muted)" };

export function ForecastChart({ f }: { f: Forecast }) {
  const models = Object.keys(f.deterministic);
  const rows = f.hourly.time.map((t, i) => {
    const r: Record<string, number | string | [number, number]> = { t: new Date(t).toLocaleString(undefined, { weekday: "short", hour: "2-digit" }) };
    r.band = [f.hourly.ens_p10[i], f.hourly.ens_p90[i]];
    r["Ensemble median"] = f.hourly.ens_p50[i];
    for (const m of models) r[m] = f.hourly[m][i] as number;
    return r;
  });
  const colors = ["var(--accent)", "#a78bfa", "#34d399"];
  return (
    <ResponsiveContainer width="100%" height={190}>
      <ComposedChart data={rows} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="t" tick={AX} interval={23} />
        <YAxis tick={AX} unit="" />
        <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", fontSize: 12 }} />
        <Area dataKey="band" name="Ensemble 10–90 %" stroke="none" fill="var(--accent)" fillOpacity={0.15} isAnimationActive={false} />
        {models.map((m, k) => <Line key={m} dataKey={m} stroke={colors[k]} dot={false} strokeWidth={1.6} isAnimationActive={false} />)}
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function HydrographChart({ h, scenario, pointId, t0, time, burst }: { h: Hydrographs; scenario: string; pointId: number; t0: string | null; time: number | null; burst: number }) {
  const s = h.scenarios[scenario];
  if (!s) return null;
  const q = s.q[String(pointId)] ?? [];
  const rows = q.map((v, i) => ({ h: (i * h.dt_min) / 60, q: v, rain: (s.rain_mm[i] ?? 0) * (60 / h.dt_min) }))
    .filter((r) => r.h >= burst - 4 && r.h <= burst + 20);
  return (
    <ResponsiveContainer width="100%" height={170}>
      <ComposedChart data={rows} margin={{ top: 6, right: 4, left: -14, bottom: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="h" type="number" domain={["dataMin", "dataMax"]} tick={AX} tickFormatter={(v) => clock(t0, v, false)} />
        <YAxis yAxisId="q" tick={AX} />
        <YAxis yAxisId="r" orientation="right" reversed tick={AX} width={28} />
        <Tooltip labelFormatter={(v) => clock(t0, Number(v))} formatter={(v: number, n) => [n === "q" ? `${v.toFixed(0)} m³/s` : `${v.toFixed(1)} mm/h`, n === "q" ? "Discharge" : "Rain"]}
          contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", fontSize: 12 }} />
        <Bar yAxisId="r" dataKey="rain" fill="#7dd3fc" opacity={0.6} isAnimationActive={false} />
        <Line yAxisId="q" dataKey="q" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
        {time !== null && <ReferenceLine yAxisId="q" x={time} stroke="var(--fg)" strokeDasharray="3 3" />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
