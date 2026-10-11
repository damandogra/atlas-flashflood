import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import {
  getScenarios,
  SCENARIOS,
  type CitizenFeature,
} from "@/api/client";

export type LayerKey = "flood" | "erosion" | "choke";

interface LayerState {
  flood: boolean;
  erosion: boolean;
  choke: boolean;
  toggle: (key: LayerKey) => void;

  // Scenario selection
  availableScenarios: string[];
  activeScenario: string;
  scenariosLoading: boolean;
  setActiveScenario: (s: string) => void;

  // Citizen observations (shared between RightPanel & TerrainMap)
  observations: CitizenFeature[];
  setObservations: (obs: CitizenFeature[]) => void;

  // Report submission workflow
  selectionMode: boolean;
  setSelectionMode: (v: boolean) => void;
  pendingLocation: { lat: number; lon: number } | null;
  setPendingLocation: (v: { lat: number; lon: number } | null) => void;

  // Cross-component highlight (map click → card highlight)
  highlightedId: number | null;
  setHighlightedId: (id: number | null) => void;

  // Risk analytics
  fused: boolean;
  setFused: (v: boolean) => void;
  dashboardBuildings: { total: number; critical: number; byRisk: Record<string, number> };
  setDashboardBuildings: (v: { total: number; critical: number; byRisk: Record<string, number> }) => void;
  dashboardRoads: { total: number; blocked: number };
  setDashboardRoads: (v: { total: number; blocked: number }) => void;
  riskCriMean: number | null;
  setRiskCriMean: (v: number | null) => void;

  // NBS interventions
  isPlantingMode: boolean;
  setIsPlantingMode: (v: boolean) => void;
  forestZone: { lat: number; lon: number } | null;
  setForestZone: (v: { lat: number; lon: number } | null) => void;
}

const Ctx = createContext<LayerState | null>(null);

export function LayerStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState({ flood: true, erosion: true, choke: false });
  const toggle = (key: LayerKey) =>
    setState((s) => ({ ...s, [key]: !s[key] }));

  // ── Scenario state ──────────────────────────────────────────────────────
  const [availableScenarios, setAvailableScenarios] = useState<string[]>([...SCENARIOS]);
  const [activeScenario, setActiveScenario] = useState<string>(SCENARIOS[0]);
  const [scenariosLoading, setScenariosLoading] = useState(true);

  // ── Citizen observations ─────────────────────────────────────────────────
  const [observations, setObservations] = useState<CitizenFeature[]>([]);
  const [selectionMode, setSelectionMode] = useState(false);
  const [pendingLocation, setPendingLocation] = useState<{ lat: number; lon: number } | null>(null);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);

  // ── Risk analytics ───────────────────────────────────────────────────────
  const [fused, setFused] = useState(false);
  const [dashboardBuildings, setDashboardBuildings] = useState({
    total: 0,
    critical: 0,
    byRisk: {} as Record<string, number>,
  });
  const [dashboardRoads, setDashboardRoads] = useState({ total: 0, blocked: 0 });
  const [riskCriMean, setRiskCriMean] = useState<number | null>(null);

  // ── NBS interventions ─────────────────────────────────────────────────────
  const [isPlantingMode, setIsPlantingMode] = useState(false);
  const [forestZone, setForestZone] = useState<{ lat: number; lon: number } | null>(null);

  useEffect(() => {
    getScenarios()
      .then((scenarios) => {
        if (scenarios.length > 0) {
          setAvailableScenarios(scenarios);
          if (!scenarios.includes(activeScenario)) {
            setActiveScenario(scenarios[0]);
          }
        }
      })
      .catch(() => {
        // API unavailable — keep the static SCENARIOS fallback
      })
      .finally(() => setScenariosLoading(false));
  }, []);

  return (
    <Ctx.Provider
      value={{
        ...state,
        toggle,
        availableScenarios,
        activeScenario,
        scenariosLoading,
        setActiveScenario,
        observations,
        setObservations,
        selectionMode,
        setSelectionMode,
        pendingLocation,
        setPendingLocation,
        highlightedId,
        setHighlightedId,
        fused,
        setFused,
        dashboardBuildings,
        setDashboardBuildings,
        dashboardRoads,
        setDashboardRoads,
        riskCriMean,
        setRiskCriMean,
        isPlantingMode,
        setIsPlantingMode,
        forestZone,
        setForestZone,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useLayerState() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLayerState must be used inside LayerStateProvider");
  return v;
}
