import { Layers, TriangleAlert } from "lucide-react";
import { useLayerState } from "./useLayerState";

export function MapLegend({
  coordinates,
}: {
  coordinates?: { lat: number; lng: number } | null;
}) {
  const { riskCriMean, activeScenario, erosion, fused } = useLayerState();

  const coordDisplay = coordinates
    ? `${coordinates.lat.toFixed(4)}° N · ${coordinates.lng.toFixed(4)}° W`
    : "31.0594° N · 7.9404° W";

  const isCustom = activeScenario.startsWith("CUSTOM");

  // CRI indicator position (0-1 range → percentage)
  const criPct =
    riskCriMean != null && !isCustom
      ? Math.min(100, Math.max(0, riskCriMean * 100))
      : null;

  return (
    <div className="pointer-events-auto absolute bottom-4 right-4 z-20">
      <div className="glass-panel rounded-xl px-4 py-3 w-64">
        {/* ── Erosion Risk Legend (only when erosion toggle on) ───────── */}
        {erosion && (
          <>
            <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              <Layers className="h-3 w-3 text-primary" />
              Erosion Risk (RUSLE)
            </div>
            <div
              className="h-2.5 w-full rounded-full ring-1 ring-glass-border"
              style={{
                background:
                  "linear-gradient(to right, rgba(255,255,0,0.3), #FFA500, #8B0000)",
              }}
            />
            <div className="mb-2 mt-1.5 flex justify-between text-[10px] text-muted-foreground">
              <span>Low</span>
              <span>Severe</span>
            </div>
          </>
        )}

        {/* ── Composite Risk Level Bar ────────────────────────────────── */}
        <div className="mb-1.5 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            <Layers className="h-3 w-3 text-primary" />
            Risk Level
          </div>
          <span className="text-[10px] text-muted-foreground">
            {fused ? "Fused" : "Composite"}
          </span>
        </div>

        {isCustom ? (
          <div className="flex items-center gap-1.5 rounded-md border border-warning/30 bg-warning/10 px-2 py-1.5 text-[10px] text-warning">
            <TriangleAlert className="h-3 w-3 shrink-0" />
            N/A for dynamic scenario
          </div>
        ) : (
          <>
            <div className="relative h-2.5 w-full rounded-full ring-1 ring-glass-border">
              <div
                className="h-full w-full rounded-full"
                style={{ background: "var(--gradient-risk)" }}
              />
              {criPct !== null && (
                <div
                  className="absolute -top-1 transition-all duration-500"
                  style={{ left: `${criPct}%`, transform: "translateX(-50%)" }}
                >
                  {/* indicator triangle */}
                  <div className="w-0 h-0 border-l-[6px] border-r-[6px] border-t-[7px] border-l-transparent border-r-transparent border-t-white drop-shadow-lg" />
                </div>
              )}
            </div>

            <div className="mt-1.5 flex justify-between text-[10px] text-muted-foreground">
              <span>Low</span>
              <span>Moderate</span>
              <span>High</span>
              <span className="text-destructive">Critical</span>
            </div>

            {criPct !== null && (
              <div
                className={`mt-1.5 text-center text-[11px] font-semibold tabular-nums ${
                  fused ? "text-primary text-glow" : "text-foreground/80"
                }`}
              >
                CRI {riskCriMean!.toFixed(3)}
              </div>
            )}
          </>
        )}
      </div>

      {/* Compass / scale */}
      <div className="glass-panel mt-2 flex items-center justify-between rounded-xl px-4 py-2 text-[10px] text-muted-foreground">
        <span className="font-mono tabular-nums">{coordDisplay}</span>
        <span className="font-mono">2 km</span>
      </div>
    </div>
  );
}
