import { createContext, useContext, useEffect, useState } from "react";
import {
  json, scenarioImpact, scenarioRasters,
  type BuildingFC, type FacilityFC, type Hydrographs, type Meta, type PlaceFC, type RoadFC, type ScenarioImpact,
  type ScenarioRasters, type ShelterFC,
} from "./data";
import type { FeatureCollection } from "geojson";
import { RoadGraph } from "./routing";

export interface Static {
  meta: Meta;
  buildings: BuildingFC;
  roads: RoadFC;
  villages: PlaceFC;
  facilities: FacilityFC;
  shelters: ShelterFC;
  catchment: FeatureCollection;
  subbasins: FeatureCollection;
  streams: FeatureCollection;
  controlPoints: FeatureCollection;
  hydrographs: Hydrographs;
  graph: RoadGraph;
}

export const DataContext = createContext<Static | null>(null);
export const useStatic = () => useContext(DataContext)!;

export async function loadStatic(): Promise<Static> {
  const [meta, buildings, roads, villages, facilities, shelters, catchment, subbasins, streams, controlPoints, hydrographs] =
    await Promise.all([
      json<Meta>("meta.json"),
      json<BuildingFC>("geo/buildings.geojson"),
      json<RoadFC>("geo/roads.geojson"),
      json<PlaceFC>("geo/villages.geojson"),
      json<FacilityFC>("geo/facilities.geojson"),
      json<ShelterFC>("geo/shelters.geojson"),
      json<FeatureCollection>("geo/catchment.geojson"),
      json<FeatureCollection>("geo/subbasins.geojson"),
      json<FeatureCollection>("geo/streams.geojson"),
      json<FeatureCollection>("geo/control_points.geojson"),
      json<Hydrographs>("hydrographs.json"),
    ]);
  return {
    meta, buildings, roads, villages, facilities, shelters, catchment, subbasins, streams, controlPoints, hydrographs,
    graph: new RoadGraph(roads),
  };
}

/** Impact arrays + rasters of the scenario on screen (null while loading or when none is selected). */
export function useScenario(name: string | null) {
  const [state, setState] = useState<{ name: string; impact: ScenarioImpact; rasters: ScenarioRasters } | null>(null);
  useEffect(() => {
    let live = true;
    if (!name) {
      setState(null);
      return;
    }
    Promise.all([scenarioImpact(name), scenarioRasters(name)]).then(([impact, rasters]) => {
      if (live) setState({ name, impact, rasters });
    });
    return () => {
      live = false;
    };
  }, [name]);
  return state && state.name === name ? state : null;
}
