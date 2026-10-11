// Status of roads, villages and buildings at a time t (hours from library t0; null = whole event).
import type { RoadFC, ScenarioImpact, VillageImpact } from "./data";

export type RoadState = 0 | 1 | 2; // open, unsafe for cars, closed even for 4x4

export function roadState(imp: ScenarioImpact, i: number, t: number | null): RoadState {
  const s = imp.segments;
  if (t === null) return s.status[i] as RoadState;
  if (s.closed_from[i] >= 0 && t >= s.closed_from[i] && t < s.closed_to[i]) return 2;
  if (s.car_from[i] >= 0 && t >= s.car_from[i] && t < s.car_to[i]) return 1;
  return 0;
}

export function villageState(v: VillageImpact | undefined, t: number | null) {
  if (!v) return { flooded: false, cut: false };
  const flooded = v.buildings_affected > 0 && (t === null || (v.first_water_h !== null && t >= v.first_water_h));
  const cut = !!v.isolation && (t === null || (t >= v.isolation.from_h && t < v.isolation.to_h));
  return { flooded, cut };
}

export function snapshot(imp: ScenarioImpact, roads: RoadFC, t: number | null) {
  let fordsClosed = 0, roadKmClosed = 0, roadKmUnsafe = 0;
  roads.features.forEach((f, i) => {
    const st = roadState(imp, i, t);
    if (st === 2) {
      roadKmClosed += f.properties.length_m / 1000;
      if (f.properties.ford) fordsClosed++;
    } else if (st === 1) roadKmUnsafe += f.properties.length_m / 1000;
  });
  let flooded = 0, cut = 0;
  for (const v of Object.values(imp.villages)) {
    const s = villageState(v, t);
    if (s.flooded) flooded++;
    if (s.cut) cut++;
  }
  const b = imp.buildings;
  let buildings = 0;
  for (let i = 0; i < b.hr_class.length; i++) if (b.hr_class[i] > 0 && (t === null || (b.arrival_h[i] >= 0 && b.arrival_h[i] <= t))) buildings++;
  return { flooded, cut, fordsClosed, roadKmClosed, roadKmUnsafe, buildings };
}

export const ROAD_TEXT = ["Open", "Unsafe for cars", "Closed — too deep or fast even for a 4×4"];
