import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Building,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  CloudRain,
  Crosshair,
  Download,
  Droplets,
  History,
  Hospital,
  Info,
  Loader2,
  Mountain,
  Play,
  Plus,
  Route,
  Shield,
  ShieldAlert,
  Sparkles,
  TreePine,
  TriangleAlert,
  Waves,
  Wrench,
} from "lucide-react";
import { ToggleSwitch } from "./ToggleSwitch";
import { useLayerState } from "./useLayerState";
import {
  getRiskStats,
  getActionCards,
  downloadRiskTiff,
  simulateCustom,
  type ActionCard,
  type Scenario,
  type CustomSimResponse,
} from "@/api/client";

type Tab = "historical" | "simulator";

export function LeftSidebar() {
  const [tab, setTab] = useState<Tab>("historical");
  const [rainfall, setRainfall] = useState(85);
  const [running, setRunning] = useState(false);
  const [customSimResult, setCustomSimResult] = useState<CustomSimResponse | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const { forestZone, activeScenario, setActiveScenario } = useLayerState();

  const handleRun = async () => {
    setRunning(true);
    setCustomSimResult(null);
    setSimError(null);

    try {
      const isPlanting = forestZone !== null;
      const result = await simulateCustom(
        rainfall,
        isPlanting,
        forestZone?.lat ?? null,
        forestZone?.lon ?? null,
        500,
      );
      setCustomSimResult(result);
      setActiveScenario("CUSTOM_" + Date.now());
    } catch (err) {
      setSimError(
        err instanceof Error ? err.message : "Simulation failed",
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <aside className="pointer-events-auto absolute left-4 top-24 bottom-4 z-20 hidden w-[350px] max-w-[calc(100vw-2rem)] lg:block">
      <div className="glass-panel-strong flex h-full flex-col overflow-hidden rounded-2xl">
        {/* Tab nav */}
        <div className="grid grid-cols-2 gap-1 border-b border-glass-border bg-background/30 p-1.5">
          <TabButton
            active={tab === "historical"}
            onClick={() => setTab("historical")}
            icon={<History className="h-3.5 w-3.5" />}
            label="Historical Risk"
          />
          <TabButton
            active={tab === "simulator"}
            onClick={() => setTab("simulator")}
            icon={<Sparkles className="h-3.5 w-3.5" />}
            label="What-If Simulator"
          />
        </div>

        {/* Content */}
        <div className="scrollbar-thin flex-1 overflow-y-auto p-5">
          {tab === "historical" ? <HistoricalTab /> : (
            <SimulatorTab
              rainfall={rainfall}
              setRainfall={setRainfall}
              running={running}
              onRun={handleRun}
              simError={simError}
              customSimResult={customSimResult}
            />
          )}
        </div>

        {/* Footer status */}
        <div className="border-t border-glass-border bg-background/30 px-4 py-2.5">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Activity className="h-3 w-3 text-primary" />
              Model · v1.0.0
            </span>
            <span>DEM 30m · CHIRPS</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all ${
        active
          ? "bg-primary/15 text-primary ring-1 ring-primary/40"
          : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
      }`}
    >
      {icon}
      <span className="truncate">{label}</span>
    </button>
  );
}

function HistoricalTab() {
  return (
    <div className="space-y-5">
      <div>
        <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-primary">
          <span className="h-px w-4 bg-primary/60" />
          Baseline
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          View vulnerabilities based on the{" "}
          <span className="text-foreground">10-year historical maximum</span> rainfall.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Peak Rainfall" value="23.7" unit="mm" />
        <Stat label="Risk Zones" value="27" unit="sites" />
      </div>

      {/* Data layers */}
      <div>
        <div className="mb-2.5 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground">
            Data Layers
          </h3>
          <button className="text-[11px] text-muted-foreground hover:text-primary">
            Reset
          </button>
        </div>
        <LayerToggles />
      </div>

      {/* Legend hint */}
      <div className="rounded-xl border border-glass-border bg-background/40 p-3">
        <div className="flex items-start gap-2.5">
          <Droplets className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Hover terrain to inspect runoff coefficient, slope, and soil class for
            any 30m cell.
          </p>
        </div>
      </div>
    </div>
  );
}

function LayerToggles() {
  const { flood, erosion, choke, toggle } = useLayerState();
  return (
    <div className="space-y-2">
      <ToggleSwitch
        label="Show Flood Runoff"
        description="HEC-HMS hydrological model"
        colorDot="oklch(0.75 0.18 220)"
        checked={flood}
        onChange={() => toggle("flood")}
      />
      <ToggleSwitch
        label="Show Erosion Susceptibility"
        description="RUSLE soil-loss equation"
        colorDot="oklch(0.72 0.20 50)"
        checked={erosion}
        onChange={() => toggle("erosion")}
      />
      <ToggleSwitch
        label="Show Choke Points"
        description="No data layer available"
        colorDot="oklch(0.65 0.24 25)"
        checked={choke}
        onChange={() => toggle("choke")}
        disabled
      />
    </div>
  );
}


function SimulatorTab({
  rainfall,
  setRainfall,
  running,
  onRun,
  simError,
  customSimResult,
}: {
  rainfall: number;
  setRainfall: (n: number) => void;
  running: boolean;
  onRun: () => void;
  simError: string | null;
  customSimResult: CustomSimResponse | null;
}) {
  const intensity =
    rainfall < 60 ? "Low" : rainfall < 130 ? "Moderate" : rainfall < 200 ? "High" : "Extreme";

  const {
    availableScenarios,
    activeScenario,
    scenariosLoading,
    setActiveScenario,
    fused,
    setFused,
    dashboardBuildings,
    dashboardRoads,
    isPlantingMode,
    setIsPlantingMode,
    forestZone,
    setForestZone,
    setRiskCriMean,
  } = useLayerState();

  // ── Risk stats ──────────────────────────────────────────────────────────
  const [riskStats, setRiskStats] = useState<{
    mean: number;
    max: number;
    min: number;
  } | null>(null);
  const [riskStatsLoading, setRiskStatsLoading] = useState(true);
  const [riskStatsError, setRiskStatsError] = useState<string | null>(null);

  useEffect(() => {
    if (scenariosLoading) return;
    let cancelled = false;

    setRiskStatsLoading(true);
    setRiskStatsError(null);

    getRiskStats(activeScenario as Scenario, fused)
      .then((stats) => {
        if (cancelled) return;
        const cri = stats.cri_mean ?? stats.mean;
        setRiskCriMean(cri ?? null);
        setRiskStats({ mean: stats.mean, max: stats.max, min: stats.min });
        setRiskStatsLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setRiskStatsError(e.message);
        setRiskStatsLoading(false);
      });

    return () => { cancelled = true; };
  }, [activeScenario, scenariosLoading, fused]);

  // ── Action cards ────────────────────────────────────────────────────────
  const [actionCards, setActionCards] = useState<ActionCard[]>([]);
  const [cardsLoading, setCardsLoading] = useState(true);
  const [cardsError, setCardsError] = useState<string | null>(null);

  useEffect(() => {
    if (scenariosLoading) return;
    let cancelled = false;

    setCardsLoading(true);
    setCardsError(null);

    getActionCards(activeScenario as Scenario)
      .then((cards) => {
        if (cancelled) return;
        setActionCards(Array.isArray(cards) ? cards : []);
        setCardsLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setCardsError(e.message);
        setCardsLoading(false);
      });

    return () => { cancelled = true; };
  }, [activeScenario, scenariosLoading]);

  return (
    <div className="space-y-5">
      <div>
        <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-primary">
          <span className="h-px w-4 bg-primary/60" />
          Sandbox
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Simulate extreme weather events and plan{" "}
          <span className="text-foreground">nature-based interventions</span>.
        </p>
      </div>

      {/* Scenario selector */}
      <div className="rounded-xl border border-glass-border bg-background/40 p-4">
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          <History className="h-3.5 w-3.5" />
          Return Period Scenario
        </div>
        {scenariosLoading ? (
          <div className="flex items-center gap-2 py-2">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span className="text-xs text-muted-foreground">Loading scenarios…</span>
          </div>
        ) : (
          <div className="relative">
            <select
              value={activeScenario}
              onChange={(e) => setActiveScenario(e.target.value)}
              className="w-full appearance-none rounded-lg border border-glass-border bg-secondary/60 px-3 py-2.5 pr-8 text-sm font-medium text-foreground outline-none transition-all focus:border-primary/60 focus:ring-1 focus:ring-primary/30"
            >
              {availableScenarios.map((s) => (
                <option key={s} value={s} className="bg-background text-foreground">
                  {s}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          </div>
        )}
        {!scenariosLoading && (
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            {activeScenario} —{" "}
            {activeScenario === "T10"
              ? "10-year return period"
              : activeScenario === "T50"
                ? "50-year return period"
                : activeScenario === "T100"
                  ? "100-year return period"
                  : "500-year return period"}
          </p>
        )}
      </div>

      {/* ── Risk Analytics Dashboard ───────────────────────────────────── */}
      <div className="rounded-xl border border-glass-border bg-background/40 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
            <Activity className="h-3.5 w-3.5" />
            Risk Analytics
          </div>
          <label className="flex cursor-pointer items-center gap-1.5">
            <span className="text-[10px] text-muted-foreground select-none">
              Citizen Intel
            </span>
            <input
              type="checkbox"
              checked={fused}
              onChange={(e) => setFused(e.target.checked)}
              className="sr-only"
            />
            <span
              className={`relative inline-block h-4 w-7 rounded-full transition-colors ${
                fused ? "bg-primary" : "bg-secondary"
              }`}
            >
              <span
                className={`absolute left-0.5 top-0.5 h-3 w-3 rounded-full bg-white transition-transform ${
                  fused ? "translate-x-3" : "translate-x-0"
                }`}
              />
            </span>
          </label>
        </div>

        {riskStatsLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
          </div>
        ) : riskStatsError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[10px] text-destructive">
            {riskStatsError}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            <DashboardStat
              label="CRI"
              value={riskStats?.mean != null ? riskStats.mean.toFixed(2) : "—"}
              description="Composite Risk Index"
              fused={fused}
            />
            <DashboardStat
              label="Buildings"
              value={String(dashboardBuildings.total || "—")}
              description={`${dashboardBuildings.critical} critical`}
              fused={fused}
            />
            <DashboardStat
              label="Roads"
              value={
                dashboardRoads.total > 0
                  ? `${Math.round((dashboardRoads.blocked / dashboardRoads.total) * 100)}%`
                  : "—"
              }
              description={`${dashboardRoads.blocked} of ${dashboardRoads.total} blocked`}
              fused={fused}
            />
          </div>
        )}
      </div>

      {/* Rainfall slider */}
      <div className="rounded-xl border border-glass-border bg-background/40 p-4">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
              <CloudRain className="h-3.5 w-3.5" />
              Simulated Rainfall
            </div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-3xl font-bold tracking-tight text-primary text-glow tabular-nums">
                {rainfall}
              </span>
              <span className="text-xs text-muted-foreground">mm / 24h</span>
            </div>
          </div>
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
              intensity === "Extreme"
                ? "border-destructive/40 bg-destructive/15 text-destructive"
                : intensity === "High"
                  ? "border-warning/40 bg-warning/15 text-warning"
                  : "border-primary/40 bg-primary/15 text-primary"
            }`}
          >
            {intensity}
          </span>
        </div>

        <input
          type="range"
          min={0}
          max={250}
          value={rainfall}
          onChange={(e) => setRainfall(Number(e.target.value))}
          disabled={running}
          className="terrain-slider w-full"
          style={{
            background: `linear-gradient(to right, oklch(0.78 0.16 210) 0%, oklch(0.78 0.16 210) ${(rainfall / 250) * 100}%, oklch(0.28 0.04 250) ${(rainfall / 250) * 100}%, oklch(0.28 0.04 250) 100%)`,
          }}
        />
        <div className="mt-1.5 flex justify-between text-[10px] text-muted-foreground">
          <span>0</span>
          <span>125</span>
          <span>250mm</span>
        </div>
      </div>

      {/* Run button */}
      <button
        onClick={onRun}
        disabled={running}
        className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-primary to-primary-glow px-4 py-3 text-sm font-semibold text-primary-foreground shadow-[0_8px_24px_-8px_oklch(0.78_0.16_210/0.6)] transition-all hover:shadow-[0_12px_30px_-8px_oklch(0.78_0.16_210/0.8)] disabled:cursor-not-allowed disabled:opacity-80"
      >
        {running ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Calculating physics…
          </>
        ) : (
          <>
            <Play className="h-4 w-4 fill-current" />
            Run Simulation
          </>
        )}
        <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
      </button>

      {/* ── Custom Simulation Result ──────────────────────────────────── */}
      {customSimResult && (
        <div className="space-y-3 rounded-xl border border-success/30 bg-success/10 p-4">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            <p className="text-[11px] leading-relaxed text-success/90">
              {customSimResult.message}
            </p>
          </div>
          <div className="text-center text-[9px] text-muted-foreground">
            Scenario: {customSimResult.scenario_generated} · {customSimResult.metrics.calculation_time_sec.toFixed(1)}s compute
          </div>

          <div className="grid grid-cols-2 gap-2">
            <ResultMetric
              label="Rainfall Applied"
              value={`${customSimResult.metrics.rainfall_applied} mm`}
              icon={<CloudRain className="h-3.5 w-3.5" />}
            />
            <ResultMetric
              label="Peak Discharge"
              value={`-${customSimResult.metrics.peak_discharge_reduction_pct}%`}
              icon={<Droplets className="h-3.5 w-3.5" />}
            />
            {customSimResult.metrics.nbs_applied && (
              <>
                <ResultMetric
                  label="Area Treated"
                  value={`${customSimResult.metrics.area_treated_ha} ha`}
                  icon={<TreePine className="h-3.5 w-3.5" />}
                />
                <ResultMetric
                  label="Calc. Time"
                  value={`${customSimResult.metrics.calculation_time_sec.toFixed(1)}s`}
                  icon={<Activity className="h-3.5 w-3.5" />}
                />
              </>
            )}
            {!customSimResult.metrics.nbs_applied && (
              <div className="col-span-2 rounded-lg border border-success/20 bg-success/5 px-2.5 py-2 text-center text-[10px] text-muted-foreground">
                No NBS intervention — baseline risk assessment only
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Simulation Error ──────────────────────────────────────────── */}
      {simError && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <p className="text-[11px] leading-relaxed text-destructive/90">
              {simError}
            </p>
          </div>
        </div>
      )}

      {/* ── Action Planner ─────────────────────────────────────────────── */}
      <div>
        <div className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-foreground">
          <ClipboardList className="h-3.5 w-3.5 text-primary" />
          Action Planner
        </div>

        {cardsLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="animate-pulse rounded-xl border border-glass-border bg-secondary/20 p-3"
              >
                <div className="mb-2 h-3 w-16 rounded-full bg-secondary/60" />
                <div className="mb-1.5 h-4 w-3/4 rounded bg-secondary/60" />
                <div className="h-3 w-full rounded bg-secondary/40" />
              </div>
            ))}
          </div>
        ) : cardsError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[10px] text-destructive">
            {cardsError}
          </div>
        ) : !Array.isArray(actionCards) || actionCards.length === 0 ? (
          <div className="rounded-xl border border-glass-border bg-background/40 px-3 py-4 text-center text-[11px] text-muted-foreground">
            {activeScenario.startsWith("CUSTOM")
              ? "No action cards generated for dynamic scenarios. Switch to a base return-period to view planning actions."
              : "No action cards generated for this scenario."}
          </div>
        ) : (
          <div className="space-y-2">
            {actionCards.map((card) => (
              <ActionCardItem key={card.id} card={card} />
            ))}
          </div>
        )}
      </div>

      {/* ── Interventions ──────────────────────────────────────────────── */}
      <div>
        <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-foreground">
          Interventions
        </h3>

        {/* Planting mode hint */}
        {isPlantingMode && (
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2.5">
            <Crosshair className="h-3.5 w-3.5 shrink-0 text-primary animate-pulse" />
            <span className="text-[11px] font-medium text-primary flex-1">
              Click on the map to select a reforestation area
            </span>
            <button
              onClick={() => setIsPlantingMode(false)}
              className="flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
              aria-label="Cancel planting"
            >
              <span className="text-xs">×</span>
            </button>
          </div>
        )}

        {/* Forest zone indicator */}
        {forestZone && !isPlantingMode && (
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2">
            <TreePine className="h-3.5 w-3.5 shrink-0 text-success" />
            <span className="text-[11px] text-success flex-1">
              Reforestation zone selected ({forestZone.lat.toFixed(4)}, {forestZone.lon.toFixed(4)})
            </span>
            <button
              onClick={() => setForestZone(null)}
              className="flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
              aria-label="Remove forest zone"
            >
              <span className="text-xs">×</span>
            </button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <InterventionChip
            icon={<TreePine className="h-3.5 w-3.5" />}
            label="Plant Forest"
            onClick={() => setIsPlantingMode(true)}
          />
          <InterventionChip
            icon={<Mountain className="h-3.5 w-3.5" />}
            label="Check-dam"
            disabled
            tooltip="Coming in v2.0"
          />
          <InterventionChip
            icon={<Waves className="h-3.5 w-3.5" />}
            label="Terracing"
            disabled
            tooltip="Coming in v2.0"
          />
          <InterventionChip
            icon={<Droplets className="h-3.5 w-3.5" />}
            label="Wetland"
            disabled
            tooltip="Coming in v2.0"
          />
        </div>
      </div>

      {/* ── GIS Export ─────────────────────────────────────────────────── */}
      <ExportButton scenario={activeScenario as Scenario} fused={fused} />
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────────────────

function DashboardStat({
  label,
  value,
  description,
  fused,
}: {
  label: string;
  value: string;
  description: string;
  fused: boolean;
}) {
  return (
    <div className="rounded-lg border border-glass-border bg-background/40 px-2 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-bold tabular-nums ${
        fused ? "text-primary text-glow" : "text-foreground"
      }`}>
        {value}
      </div>
      <div className="truncate text-[9px] text-muted-foreground">{description}</div>
    </div>
  );
}

function ActionCardItem({ card }: { card: ActionCard }) {
  const priorityConfig = {
    CRITICAL: {
      bg: "border-red-500/40 bg-red-950/40",
      badge: "bg-red-600 text-white",
      icon: <ShieldAlert className="h-3.5 w-3.5" />,
    },
    HIGH: {
      bg: "border-orange-500/30 bg-orange-950/30",
      badge: "bg-orange-600 text-white",
      icon: <TriangleAlert className="h-3.5 w-3.5" />,
    },
    MEDIUM: {
      bg: "border-primary/30 bg-primary/5",
      badge: "bg-primary/20 text-primary",
      icon: <Shield className="h-3.5 w-3.5" />,
    },
  };

  const cfg = priorityConfig[card.priority] ?? priorityConfig.MEDIUM;
  const ActionIcon = guessActionIcon(card.title + " " + card.action);

  return (
    <div className={`rounded-xl border ${cfg.bg} p-3 transition-all hover:brightness-110`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span
          className={`flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cfg.badge}`}
        >
          {cfg.icon}
          {card.priority}
        </span>
        {card.affected_population !== undefined && card.affected_population > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <Building className="h-3 w-3" />
            {card.affected_population}
          </span>
        )}
      </div>

      <h4 className="text-xs font-semibold text-foreground">{card.title}</h4>

      {card.description && (
        <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-muted-foreground">
          {card.description}
        </p>
      )}

      <div className="mt-2 flex items-center gap-2">
        <span className="flex items-center gap-1 text-[10px] font-medium text-primary">
          <Route className="h-3 w-3" />
          {card.action}
        </span>
        {card.location && (
          <span className="text-[10px] text-muted-foreground">· {card.location}</span>
        )}
      </div>
    </div>
  );
}

function ExportButton({ scenario, fused }: { scenario: Scenario; fused: boolean }) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);

    try {
      const blob = await downloadRiskTiff(scenario, fused);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${scenario}_cri${fused ? "_fused" : ""}.tif`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="rounded-xl border border-glass-border bg-background/40 p-3">
      <button
        onClick={handleExport}
        disabled={exporting}
        className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-lg border border-primary/40 bg-primary/5 px-3 py-2.5 text-xs font-medium text-primary transition-all hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-60"
        title="Export high-resolution physical simulation data for QGIS/ArcGIS desktop analysis."
      >
        {exporting ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Exporting GeoTIFF…
          </>
        ) : (
          <>
            <Download className="h-3.5 w-3.5" />
            Export Raw GeoTIFF (GIS Compatible)
          </>
        )}
      </button>
      <p className="mt-1.5 text-[9px] text-muted-foreground text-center">
        High-resolution simulation data for QGIS / ArcGIS.
      </p>
      {exportError && (
        <div className="mt-1.5 rounded border border-destructive/30 bg-destructive/10 px-2 py-1 text-[10px] text-destructive">
          {exportError}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-xl border border-glass-border bg-background/40 px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span className="text-lg font-semibold text-foreground tabular-nums">{value}</span>
        <span className="text-[10px] text-muted-foreground">{unit}</span>
      </div>
    </div>
  );
}

function InterventionChip({
  icon,
  label,
  disabled,
  tooltip,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
  tooltip?: string;
  onClick?: () => void;
}) {
  const Comp = disabled ? "div" : "button";
  return (
    <Comp
      {...(!disabled && onClick ? { onClick } : {})}
      title={tooltip}
      className={`flex items-center gap-1.5 rounded-lg border bg-secondary/40 px-2.5 py-2 text-[11px] font-medium transition-all ${
        disabled
          ? "cursor-not-allowed border-glass-border text-muted-foreground/50 opacity-50"
          : "cursor-pointer border-glass-border text-foreground hover:border-primary/40 hover:bg-secondary/70 hover:text-primary"
      }`}
    >
      <span className={disabled ? "text-muted-foreground/50" : "text-primary"}>{icon}</span>
      <span className="truncate">{label}</span>
    </Comp>
  );
}

/** Guess a lucide icon from action text keywords */
function guessActionIcon(text: string): React.ReactNode {
  const t = text.toLowerCase();
  if (t.includes("hospital") || t.includes("medical") || t.includes("health")) return <Hospital className="h-3 w-3" />;
  if (t.includes("evacuation") || t.includes("evacuate") || t.includes("shelter")) return <Shield className="h-3 w-3" />;
  if (t.includes("bridge") || t.includes("road") || t.includes("infrastructure")) return <Wrench className="h-3 w-3" />;
  if (t.includes("flood") || t.includes("water") || t.includes("drain")) return <Waves className="h-3 w-3" />;
  if (t.includes("warning") || t.includes("alert")) return <AlertTriangle className="h-3 w-3" />;
  if (t.includes("forest") || t.includes("tree") || t.includes("reforest")) return <TreePine className="h-3 w-3" />;
  return <Shield className="h-3 w-3" />;
}

/** Metric card for reforestation simulation result */
function ResultMetric({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-success/30 bg-success/5 px-2.5 py-2">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-0.5 text-sm font-bold tabular-nums text-success">
        {value}
      </div>
    </div>
  );
}
