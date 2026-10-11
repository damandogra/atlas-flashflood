import createClient from "openapi-fetch";
import type { paths, components } from "./types";

// ─── Configuration ───────────────────────────────────────────────────────

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export { API_BASE_URL };

// ─── Enums / Constants ───────────────────────────────────────────────────

export const SCENARIOS = ["T10", "T50", "T100", "T500"] as const;
export type Scenario = (typeof SCENARIOS)[number];

export const EVENT_TYPES = [
  "flooding",
  "road_blocked",
  "structure_damage",
  "evacuation_needed",
  "infrastructure_damage",
  "other",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export const ALERT_LEVELS = ["green", "yellow", "orange", "red"] as const;
export type AlertLevel = (typeof ALERT_LEVELS)[number];

export const ROAD_STATUSES = ["passable", "emergency_only", "impassable"] as const;
export type RoadStatus = (typeof ROAD_STATUSES)[number];

export const RISK_LEVELS = ["low", "moderate", "high", "critical"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export const SEVERITY_LEVELS = [1, 2, 3] as const;
export type Severity = (typeof SEVERITY_LEVELS)[number];

// ─── Response Types (the OpenAPI spec response schemas are mostly
//     `unknown`, so we add concrete types here) ───────────────────────────

/** GeoJSON Position: [lon, lat] */
type Position = [number, number];

/** A building exposed to flooding */
export interface BuildingFeature {
  type: "Feature";
  geometry: { type: "Point" | "Polygon"; coordinates: unknown };
  properties: {
    depth_m: number;
    velocity_ms: number;
    hazard_score: number;
    risk_level: RiskLevel;
    is_critical: boolean;
    /** optional building id or name */
    id?: string | number;
  };
}

/** A road segment with passability info */
export interface RoadFeature {
  type: "Feature";
  geometry: { type: "LineString"; coordinates: Position[] };
  properties: {
    flood_depth_m: number;
    status: RoadStatus;
    color: "green" | "orange" | "red";
    name?: string;
  };
}

/** A single community observation */
export interface CitizenFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: Position };
  properties: {
    id: number;
    event_type: EventType;
    severity: Severity;
    description: string;
    reporter: string;
    created_at: string;
  };
}

/** Composite Risk Index summary */
export interface RiskSummary {
  scenario: Scenario;
  mean: number;
  max: number;
  min: number;
  std: number;
  /** pixel counts per risk level */
  pixel_counts?: Record<RiskLevel, number>;
  /** CRI mean (from the same endpoint, alternative naming) */
  cri_mean?: number;
  hazard_mean?: number;
  exposure_mean?: number;
  vulnerability_mean?: number;
}

/** Alert data from the early warning system */
export interface AlertData {
  level: AlertLevel;
  /** Rainfall forecast in mm */
  rainfall_24h: number;
  timestamp: string;
}

/** Priority Action Card */
export interface ActionCard {
  id: string;
  priority: "CRITICAL" | "HIGH" | "MEDIUM";
  title: string;
  description: string;
  location?: string;
  affected_population?: number;
  action: string;
}

/** GeoJSON FeatureCollection wrapper */
export interface FeatureCollection<T> {
  type: "FeatureCollection";
  features: T[];
}

// ─── Raw client (openapi-fetch) ──────────────────────────────────────────

const client = createClient<paths>({ baseUrl: API_BASE_URL });

// ─── Typed API functions ─────────────────────────────────────────────────

/**
 * List available flood scenarios.
 * Returns the list of return-period scenarios that have been processed.
 */
export async function getScenarios(): Promise<string[]> {
  const { data, error } = await client.GET("/scenarios");
  if (error) throw new ApiError("Failed to fetch scenarios", error);
  return data as unknown as string[];
}

/**
 * Flooded buildings for a given scenario.
 */
export async function getExposure(
  scenario: Scenario,
): Promise<FeatureCollection<BuildingFeature>> {
  const { data, error } = await client.GET("/exposure/{scenario}", {
    params: { path: { scenario } },
  });
  if (error) throw new ApiError(`Failed to fetch exposure for ${scenario}`, error);
  return data as FeatureCollection<BuildingFeature>;
}

/**
 * Road passability for a given scenario.
 */
export async function getRoads(
  scenario: Scenario,
): Promise<FeatureCollection<RoadFeature>> {
  const { data, error } = await client.GET("/roads/{scenario}", {
    params: { path: { scenario } },
  });
  if (error) throw new ApiError(`Failed to fetch roads for ${scenario}`, error);
  return data as FeatureCollection<RoadFeature>;
}

/**
 * Composite Risk Index stats for a scenario.
 * Set `fused: true` to get the citizen-signal-fused version.
 */
export async function getRiskStats(
  scenario: Scenario,
  fused = false,
): Promise<RiskSummary> {
  const { data, error } = await client.GET("/risk/{scenario}", {
    params: { path: { scenario }, query: { fused } },
  });
  if (error) throw new ApiError(`Failed to fetch risk stats for ${scenario}`, error);
  return data as RiskSummary;
}

/**
 * Download CRI raster GeoTIFF. Returns a Blob for display or download.
 * Set `fused: true` to get the citizen-signal-fused version.
 */
export async function downloadRiskTiff(
  scenario: Scenario,
  fused = false,
): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/risk/${scenario}/download${fused ? "?fused=true" : ""}`,
  );
  if (!response.ok) {
    throw new ApiError(`Failed to download CRI GeoTIFF for ${scenario}`, {
      status: response.status,
    });
  }
  return response.blob();
}

/**
 * Current early-warning alert level based on 24h rainfall forecast.
 */
export async function getAlert(): Promise<AlertData> {
  const { data, error } = await client.GET("/alert");
  if (error) throw new ApiError("Failed to fetch alert", error);
  return data as AlertData;
}

/**
 * Community observations as GeoJSON.
 * Optionally filter by `eventType` and minimum `severity`.
 */
export async function getCitizenObservations(
  eventType?: EventType,
  minSeverity?: Severity,
): Promise<FeatureCollection<CitizenFeature>> {
  const { data, error } = await client.GET("/citizen", {
    params: {
      query: {
        event_type: eventType ?? null,
        min_severity: minSeverity,
      },
    },
  });
  if (error) throw new ApiError("Failed to fetch citizen observations", error);
  return data as FeatureCollection<CitizenFeature>;
}

/**
 * Submit a community observation.
 */
export async function submitObservation(
  observation: components["schemas"]["ObservationIn"],
): Promise<CitizenFeature> {
  const { data, error } = await client.POST("/citizen", {
    body: observation,
  });
  if (error) throw new ApiError("Failed to submit observation", error);
  return data as CitizenFeature;
}

/**
 * Ranked planner action cards for a given scenario (default: t100).
 */
export async function getActionCards(
  scenario: Scenario = "T100",
): Promise<ActionCard[]> {
  const { data, error } = await client.GET("/action_cards", {
    params: { query: { scenario } },
  });
  if (error) throw new ApiError("Failed to fetch action cards", error);
  return data as ActionCard[];
}

/**
 * A flow direction arrow (point with bearing).
 */
export interface FlowArrowFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    bearing: number;
    /** optional flow velocity magnitude */
    magnitude?: number;
  };
}

/**
 * Flow direction arrows for a given scenario.
 */
export async function getFlowArrows(
  scenario: Scenario,
): Promise<FeatureCollection<FlowArrowFeature>> {
  const response = await fetch(
    `${API_BASE_URL}/flow/${scenario}`,
  );
  if (!response.ok) {
    throw new ApiError(`Failed to fetch flow arrows for ${scenario}`, {
      status: response.status,
    });
  }
  return response.json();
}

/**
 * Reforestation simulation result from the backend.
 */
export interface ReforestationResult {
  status: string;
  intervention_type: string;
  details: {
    area_hectares: number;
    pixels_affected: number;
    avg_ndvi_before: number;
    avg_ndvi_after: number;
  };
  impact: {
    scenario: string;
    peak_discharge_reduction_pct: number;
    total_water_retained_m3: number;
  };
  message: string;
}

/**
 * Run a reforestation simulation.
 * POST /simulate/reforestation with coordinates and radius.
 */
export async function simulateReforestation(
  lat: number,
  lon: number,
  radius_m: number,
  scenario: Scenario,
): Promise<ReforestationResult> {
  const response = await fetch(
    `${API_BASE_URL}/simulate/reforestation`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon, radius_m, scenario }),
    },
  );
  if (!response.ok) {
    throw new ApiError(
      `Reforestation simulation failed (HTTP ${response.status})`,
      { status: response.status },
    );
  }
  return response.json();
}

// ─── Dynamic Custom Simulation ────────────────────────────────────────────

export interface CustomSimMetrics {
  rainfall_applied: number;
  nbs_applied: boolean;
  area_treated_ha: number;
  peak_discharge_reduction_pct: number;
  calculation_time_sec: number;
}

export interface CustomSimResponse {
  status: string;
  scenario_generated: string;
  metrics: CustomSimMetrics;
  message: string;
}

/**
 * Run a fully dynamic custom simulation.
 * POST /simulate/custom with rainfall, NBS flag, and optional location.
 * Backend runs the hydrological engine in real time (~5-8 seconds).
 */
export async function simulateCustom(
  rainfall_mm: number,
  is_planting: boolean,
  lat?: number | null,
  lon?: number | null,
  radius_m = 500,
): Promise<CustomSimResponse> {
  const response = await fetch(`${API_BASE_URL}/simulate/custom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rainfall_mm, is_planting, lat, lon, radius_m }),
  });
  if (!response.ok) {
    throw new ApiError(
      `Custom simulation failed (HTTP ${response.status})`,
      { status: response.status },
    );
  }
  return response.json();
}

// ─── Error type ──────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly cause: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
