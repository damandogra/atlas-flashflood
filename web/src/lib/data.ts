// Static data bundle (built by `python -m pipeline.export.web`) and its types.
import type { FeatureCollection, Point, Polygon, LineString } from "geojson";

export const DATA = `${import.meta.env.BASE_URL}data/`;

export interface LibraryEntry {
  name: string;
  p24_mm: number;
  return_period: string;
  buildings_affected: number;
  people_affected: number;
  road_km_closed: number;
  fords_closed: number;
  villages_isolated: string[];
}

export interface Meta {
  title: string;
  library: LibraryEntry[];
  raster: {
    corners_lonlat: [number, number][];
    width: number;
    height: number;
  };
  design_burst_h: number;
  alert_rules: Record<string, { scenario: string; prob: number; deterministic: string }>;
  correction_factor: number;
  catchment_km2: number;
  population: number;
  subbasins: { id: number; name: string; area_km2: number; cn: number }[];
  rain_points: { lon: number; lat: number; w: number }[];
  amc_limits_mm: [number, number];
  validation: {
    water_balance: {
      observed_storm_runoff_mm_yr: [number, number];
      levels: Record<string, { storm_runoff_mm_yr: number; factor: number }>;
    };
    outlet_k: Record<string, number>;
  };
}

export interface VillageImpact {
  buildings: number;
  buildings_affected: number;
  by_hazard: { low: number; moderate: number; significant: number; extreme: number };
  structural_damage_likely: number;
  collapse_possible: number;
  people_affected: number;
  facilities_affected: Record<string, number>;
  first_water_h: number | null;
  isolation: { from_h: number; to_h: number; hours: number } | null;
}

export interface Action {
  id: string;
  title: string;
  owner: string;
  priority: "CRITICAL" | "HIGH" | "MEDIUM";
  deadline_h: number;
  where: string;
  lonlat: [number, number] | null;
  reason: string;
  count: number | null;
}

export interface ScenarioImpact {
  name: string;
  p24_mm: number;
  buildings: { depth: number[]; hr_class: number[]; arrival_h: number[]; structural: number[] };
  segments: {
    depth: number[];
    dv: number[];
    status: number[];
    car_from: number[];
    car_to: number[];
    closed_from: number[];
    closed_to: number[];
  };
  villages: Record<string, VillageImpact>;
  actions: Action[];
  summary: {
    buildings_affected: number;
    people_affected: number;
    by_hazard: Record<string, number>;
    collapse_possible: number;
    road_km_closed: number;
    road_km_cars_unsafe: number;
    fords_closed: number;
    facilities_affected: Record<string, number>;
    villages_isolated: string[];
  };
  hydraulics: { peak_outflow_m3s: number; flooded_km2_gt_0_1m?: number; max_depth_m: number; [k: string]: unknown };
}

export interface Hydrographs {
  dt_min: number;
  points: { id: number; name: string; kind: string; drainage_km2: number }[];
  scenarios: Record<string, { rain_mm: number[]; q: Record<string, number[]> }>;
}

export type BuildingFC = FeatureCollection<Polygon, { village: string; type: string; pop: number; facility_name: string }>;
export type RoadFC = FeatureCollection<
  LineString,
  { highway: string; ref: string | null; label: string; mode: string; ford: boolean; bridge: boolean; length_m: number }
>;
export type PlaceFC = FeatureCollection<Point, { name: string; name_local: string; place: string }>;
export type FacilityFC = FeatureCollection<Point, { kind: string; name: string }>;
export type ShelterFC = FeatureCollection<Point, { kind: string; name: string | null; village: string; source: string }>;

const cache = new Map<string, Promise<unknown>>();

export function json<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(DATA + path).then((r) => {
        if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
        return r.json();
      }),
    );
  }
  return cache.get(path) as Promise<T>;
}

/** Decode a data PNG into raw pixel values (no colour management: the PNGs carry no profile). */
export function png(path: string): Promise<ImageData> {
  if (!cache.has(path)) {
    cache.set(
      path,
      new Promise<ImageData>((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          const c = document.createElement("canvas");
          c.width = img.width;
          c.height = img.height;
          const ctx = c.getContext("2d", { willReadFrequently: true })!;
          ctx.drawImage(img, 0, 0);
          resolve(ctx.getImageData(0, 0, img.width, img.height));
        };
        img.onerror = () => reject(new Error(`${path}: image failed to load`));
        img.src = DATA + path;
      }),
    );
  }
  return cache.get(path) as Promise<ImageData>;
}

export interface ScenarioRasters {
  flood: ImageData; // R depth*40, G velocity*40, B first water >0.1 m (h*5)
  time: ImageData; // R first water >0.3 m (h*5), G duration >0.3 m (h*5), B max d(v+0.5)*40
}

export async function scenarioRasters(name: string): Promise<ScenarioRasters> {
  const [flood, time] = await Promise.all([png(`scenarios/${name}/flood.png`), png(`scenarios/${name}/time.png`)]);
  return { flood, time };
}

export const scenarioImpact = (name: string) => json<ScenarioImpact>(`scenarios/${name}/impact.json`);
