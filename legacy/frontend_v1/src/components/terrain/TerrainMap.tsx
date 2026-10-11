import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { Map, Source, Layer, Popup, type MapRef } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";
import { useLayerState } from "./useLayerState";
import {
  getRoads,
  getExposure,
  getFlowArrows,
  type Scenario,
  type RoadFeature,
  type BuildingFeature,
  type FlowArrowFeature,
  type CitizenFeature,
  type EventType,
  type Severity,
} from "@/api/client";
import type mapboxgl from "mapbox-gl";
import { Loader2, AlertCircle, Waves, Ban, Building, AlertTriangle, Wrench, CircleHelp, ShieldCheck, TriangleAlert } from "lucide-react";

// ─── Token ───────────────────────────────────────────────────────────────

const MAPBOX_ACCESS_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN as string;
if (!MAPBOX_ACCESS_TOKEN || MAPBOX_ACCESS_TOKEN === "pk.your_mapbox_token_here") {
  throw new Error(
    "Missing Mapbox token: set VITE_MAPBOX_TOKEN in .env (see .env.example). " +
    "Get a free token at https://account.mapbox.com/access-tokens/"
  );
}

// ─── Constants ───────────────────────────────────────────────────────────

const MIN_LON = -7.188835;
const MIN_LAT = 31.268093;
const MAX_LON = -6.969452;
const MAX_LAT = 31.378074;

const RISK_BBOX: [[number, number], [number, number], [number, number], [number, number]] = [
  [MIN_LON, MAX_LAT],
  [MAX_LON, MAX_LAT],
  [MAX_LON, MIN_LAT],
  [MIN_LON, MIN_LAT],
];

/** Building fill-extrusion colors — pink/purple/yellow palette */
const BUILDING_RISK_EXPRESSION = [
  "match",
  ["get", "risk_level"],
  "critical",
  "#a855f7",
  "high",
  "#ec4899",
  "moderate",
  "#eab308",
  "low",
  "#d8b4fe",
  "#6b7280",
] as unknown as Exclude<mapboxgl.DataDrivenPropertyValueSpecification<string>, string>;

/** Building circle colors — matches the extrusion but more saturated for visibility */
const BUILDING_CIRCLE_COLOR_EXPRESSION = [
  "match",
  ["get", "risk_level"],
  "critical",
  "#c084fc",
  "high",
  "#f472b6",
  "moderate",
  "#facc15",
  "low",
  "#e9d5ff",
  "#6b7280",
] as unknown as Exclude<mapboxgl.DataDrivenPropertyValueSpecification<string>, string>;

/** Critical infrastructure: hot pink for high/critical risk, bright purple for low/moderate */
const CRITICAL_BUILDING_COLOR_EXPRESSION = [
  "match",
  ["get", "risk_level"],
  "critical",
  "#ff1493",
  "high",
  "#ff1493",
  "#c084fc",
] as unknown as Exclude<mapboxgl.DataDrivenPropertyValueSpecification<string>, string>;

/** Road color driven by the GeoJSON `color` property */
const ROAD_COLOR_EXPRESSION = [
  "match",
  ["get", "color"],
  "red",
  "#ef4444",
  "orange",
  "#fb923c",
  "green",
  "#4ade80",
  "#6b7280",
] as unknown as Exclude<mapboxgl.DataDrivenPropertyValueSpecification<string>, string>;

/** Citizen severity → circle color */
const CITIZEN_SEVERITY_EXPRESSION = [
  "match",
  ["get", "severity"],
  1,
  "#fbbf24",
  2,
  "#fb923c",
  3,
  "#ef4444",
  "#6b7280",
] as unknown as Exclude<mapboxgl.DataDrivenPropertyValueSpecification<string>, string>;

/** Citizen severity → circle radius */
const CITIZEN_RADIUS_EXPRESSION = [
  "match",
  ["get", "severity"],
  1,
  5,
  2,
  7,
  3,
  9,
  5,
] as unknown as Exclude<mapboxgl.DataDrivenPropertyValueSpecification<number>, number>;

// ─── Event type → lucide icon name (for popup) ─────────────────────────────

const EVENT_TYPE_ICONS: Record<string, React.ReactNode> = {
  flooding: <Waves className="h-3.5 w-3.5" />,
  road_blocked: <Ban className="h-3.5 w-3.5" />,
  structure_damage: <Building className="h-3.5 w-3.5" />,
  evacuation_needed: <AlertTriangle className="h-3.5 w-3.5" />,
  infrastructure_damage: <Wrench className="h-3.5 w-3.5" />,
  other: <CircleHelp className="h-3.5 w-3.5" />,
};

const EVENT_LABELS: Record<string, string> = {
  flooding: "Flooding",
  road_blocked: "Road Blocked",
  structure_damage: "Structure Damage",
  evacuation_needed: "Evacuation Needed",
  infrastructure_damage: "Infrastructure Damage",
  other: "Other",
};

const SEVERITY_LABELS: Record<number, string> = {
  1: "Minor",
  2: "Moderate",
  3: "Severe",
};

// ─── Component ───────────────────────────────────────────────────────────

export function TerrainMap({
  onCoordsChange,
}: {
  onCoordsChange?: (lat: number, lng: number) => void;
}) {
  const {
    flood,
    erosion,
    choke,
    activeScenario,
    fused,
    scenariosLoading,
    observations,
    selectionMode,
    setSelectionMode,
    pendingLocation,
    setPendingLocation,
    setHighlightedId,
    setDashboardBuildings,
    setDashboardRoads,
    isPlantingMode,
    setIsPlantingMode,
    forestZone,
    setForestZone,
  } = useLayerState();
  const [mounted, setMounted] = useState(false);
  const mapRef = useRef<MapRef>(null);

  // ── GeoJSON data state ──────────────────────────────────────────────────
  const [roadsData, setRoadsData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [buildingsData, setBuildingsData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [flowArrowsData, setFlowArrowsData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [loadingScenario, setLoadingScenario] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  // ── Popup state ─────────────────────────────────────────────────────────
  interface PopupInfo {
    coordinates: [number, number];
    type: "road" | "building" | "citizen";
    properties: Record<string, unknown>;
  }
  const [popup, setPopup] = useState<PopupInfo | null>(null);

  // ── Cursor state (hover cursor change) ──────────────────────────────────
  const [mapCursor, setMapCursor] = useState<string>("");

  // ── Selected building (click-based persistent popup) ─────────────────────
  const [selectedBuilding, setSelectedBuilding] = useState<{
    coordinates: [number, number];
    properties: Record<string, unknown>;
  } | null>(null);

  // ── Build citizen GeoJSON from context observations ──────────────────────
  const citizenGeoJson = useMemo((): GeoJSON.FeatureCollection | null => {
    if (observations.length === 0) return null;
    return {
      type: "FeatureCollection",
      features: observations as unknown as GeoJSON.Feature[],
    };
  }, [observations]);

  // ── Client-side mount guard ─────────────────────────────────────────────
  useEffect(() => setMounted(true), []);

  // ── Fetch roads + exposure when scenario changes ─────────────────────────
  useEffect(() => {
    if (!mounted) return;
    if (scenariosLoading) return;

    let cancelled = false;
    setLoadingScenario(true);
    setScenarioError(null);
    setPopup(null); // dismiss popup on scenario switch

    Promise.all([
      getRoads(activeScenario as Scenario).catch((e: Error) => {
        console.warn(`Failed to fetch roads for ${activeScenario}:`, e.message);
        return null;
      }),
      getExposure(activeScenario as Scenario).catch((e: Error) => {
        console.warn(`Failed to fetch exposure for ${activeScenario}:`, e.message);
        return null;
      }),
      getFlowArrows(activeScenario as Scenario).catch((e: Error) => {
        console.warn(`Failed to fetch flow arrows for ${activeScenario}:`, e.message);
        return null;
      }),
    ])
      .then(([roads, buildings, flowArrows]) => {
        if (cancelled) return;
        setRoadsData(roads as GeoJSON.FeatureCollection | null);
        setBuildingsData(buildings as GeoJSON.FeatureCollection | null);
        setFlowArrowsData(flowArrows as GeoJSON.FeatureCollection | null);

        // Compute dashboard metrics
        const b = buildings as GeoJSON.FeatureCollection | null;
        const r = roads as GeoJSON.FeatureCollection | null;
        if (b?.features) {
          const byRisk: Record<string, number> = {};
          let critical = 0;
          for (const f of b.features) {
            const props = f.properties as Record<string, unknown> | null;
            const level = (props?.risk_level as string) ?? "unknown";
            byRisk[level] = (byRisk[level] ?? 0) + 1;
            if (props?.is_critical) critical++;
          }
          setDashboardBuildings({ total: b.features.length, critical, byRisk });
        }
        if (r?.features) {
          let blocked = 0;
          for (const f of r.features) {
            const props = f.properties as Record<string, unknown> | null;
            if (props?.status === "impassable") blocked++;
          }
          setDashboardRoads({ total: r.features.length, blocked });
        }

        if (!roads && !buildings) {
          setScenarioError("Could not load flood data for this scenario");
        }
        setLoadingScenario(false);
      })
      .catch(() => {
        if (!cancelled) {
          setScenarioError("Failed to load flood data");
          setLoadingScenario(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeScenario, mounted, scenariosLoading]);

  // ── Popup handlers ──────────────────────────────────────────────────────

  const handleMouseEnter = useCallback(
    (e: mapboxgl.MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const layerId = feature.layer?.id ?? "";

      // Set pointer cursor on building layers
      if (layerId.startsWith("buildings")) {
        setMapCursor("pointer");
        return; // Buildings use click-based popup, not hover
      }

      const isRoad = layerId.startsWith("road");
      const isCitizen = layerId.startsWith("citizen");
      if (isRoad || isCitizen) {
        setMapCursor("pointer");
        setPopup({
          coordinates: [e.lngLat.lng, e.lngLat.lat],
          type: isCitizen ? "citizen" : "road",
          properties: feature.properties as Record<string, unknown>,
        });
      }
    },
    []
  );

  const handleMouseLeave = useCallback(() => {
    setPopup(null);
    setMapCursor("");
  }, []);

  // ── Map click handler: selection mode + citizen highlight ────────────────

  const handleMapClick = useCallback(
    (e: mapboxgl.MapMouseEvent) => {
      if (selectionMode) {
        setPendingLocation({ lat: e.lngLat.lat, lon: e.lngLat.lng });
        setSelectionMode(false);
        return;
      }

      // Planting mode — capture location for reforestation zone
      if (isPlantingMode) {
        setForestZone({ lat: e.lngLat.lat, lon: e.lngLat.lng });
        setIsPlantingMode(false);
        setSelectedBuilding(null);
        setPopup(null);
        return;
      }

      // Check citizen features first (rendered on top of buildings)
      if (citizenGeoJson) {
        const features = e.target.queryRenderedFeatures(e.point, {
          layers: ["citizen-circle-layer", "citizen-glow-layer"],
        });
        if (features.length > 0) {
          const id = features[0].properties?.id as number | undefined;
          if (id !== undefined) {
            setHighlightedId(id);
            setPopup({
              coordinates: [e.lngLat.lng, e.lngLat.lat],
              type: "citizen",
              properties: features[0].properties as Record<string, unknown>,
            });
            setSelectedBuilding(null);
          }
          return;
        }
      }

      // Check if a building feature was clicked
      const buildingFeatures = e.target.queryRenderedFeatures(e.point, {
        layers: ["buildings-extrusion-layer", "buildings-critical-layer", "buildings-circle-layer"],
      });
      if (buildingFeatures.length > 0) {
        setSelectedBuilding({
          coordinates: [e.lngLat.lng, e.lngLat.lat],
          properties: buildingFeatures[0].properties as Record<string, unknown>,
        });
        setPopup(null);
        return;
      }

      // Clicked on empty space — dismiss building popup
      setSelectedBuilding(null);
      setPopup(null);
    },
    [selectionMode, isPlantingMode, citizenGeoJson, setPendingLocation, setSelectionMode, setHighlightedId, setForestZone, setIsPlantingMode]
  );

  // ── Loading overlay (only when data is empty AND loading) ───────────────
  const showLoadingLayer = loadingScenario && !roadsData && !buildingsData;

  // ── Render ──────────────────────────────────────────────────────────────

  if (!mounted) {
    return <div className="absolute inset-0 bg-background" aria-hidden />;
  }

  return (
    <div
      id="mapbox-container"
      className="absolute inset-0"
      aria-label="3D terrain map of Atlas Mountains Basin"
    >
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_ACCESS_TOKEN}
        mapStyle="mapbox://styles/mapbox/satellite-v9"
        initialViewState={{
          longitude: -7.15,
          latitude: 31.3,
          zoom: 11,
          pitch: 65,
          bearing: 20,
        }}
        terrain={{ source: "mapbox-dem", exaggeration: 1.5 }}
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
        interactiveLayerIds={[
          "roads-line-layer",
          "buildings-extrusion-layer",
          "buildings-critical-layer",
          "buildings-circle-layer",
          "citizen-circle-layer",
          "citizen-glow-layer",
        ]}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onMouseMove={(e) => onCoordsChange?.(e.lngLat.lat, e.lngLat.lng)}
        onClick={handleMapClick}
        cursor={selectionMode || isPlantingMode ? "crosshair" : mapCursor}
      >
        {/* ⛰ 3D terrain DEM */}
        <Source
          id="mapbox-dem"
          type="raster-dem"
          url="mapbox://mapbox.mapbox-terrain-dem-v1"
          tileSize={512}
          maxzoom={14}
        />

        {/* ── Roads ──────────────────────────────────────────────────── */}
        {roadsData && roadsData.features.length > 0 && (
          <Source id="roads-source" type="geojson" data={roadsData}>
            {/* Glow beneath (wider, blurred) */}
            <Layer
              id="roads-glow-layer"
              type="line"
              source="roads-source"
              paint={{
                "line-color": ROAD_COLOR_EXPRESSION,
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10,
                  4,
                  14,
                  10,
                ],
                "line-blur": 6,
                "line-opacity": 0.35,
              }}
              layout={{ visibility: "visible" }}
            />
            {/* Main road line */}
            <Layer
              id="roads-line-layer"
              type="line"
              source="roads-source"
              paint={{
                "line-color": ROAD_COLOR_EXPRESSION,
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10,
                  2,
                  14,
                  6,
                ],
                "line-opacity": 0.85,
              }}
            />
          </Source>
        )}

        {/* ── Buildings (3D fill-extrusion) ──────────────────────────── */}
        {flood && buildingsData && buildingsData.features.length > 0 && (
          <Source id="buildings-source" type="geojson" data={buildingsData}>
            <Layer
              id="buildings-extrusion-layer"
              type="fill-extrusion"
              source="buildings-source"
              // filter={["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false]}
              paint={{
                "fill-extrusion-color": BUILDING_RISK_EXPRESSION,
                "fill-extrusion-height": [
                  "max",
                  ["coalesce", ["*", ["get", "depth_m"], 3], 0],
                  5,
                ],
                "fill-extrusion-elevation-reference": "terrain",
                "fill-extrusion-opacity": 0.7,
              } as any}
            />

            {/* Critical infrastructure highlight (risk-driven neon colors) */}
            <Layer
              id="buildings-critical-layer"
              type="fill-extrusion"
              source="buildings-source"
              filter={["==", ["get", "is_critical"], true]}
              paint={{
                "fill-extrusion-color": CRITICAL_BUILDING_COLOR_EXPRESSION,
                "fill-extrusion-height": [
                  "max",
                  ["coalesce", ["*", ["get", "depth_m"], 3], 0],
                  5,
                ],
                "fill-extrusion-opacity": 0.9,
                "fill-extrusion-opacity-transition": {
                  duration: 600,
                  delay: 0,
                },
                "fill-extrusion-elevation-reference": "terrain",
              } as any}
            />

            {/* Building circle markers — visible at any zoom/pitch */}
            <Layer
              id="buildings-circle-layer"
              type="circle"
              source="buildings-source"
              paint={{
                "circle-color": BUILDING_CIRCLE_COLOR_EXPRESSION,
                "circle-radius": 8,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
                "circle-opacity": 0.9,
              }}
            />
          </Source>
        )}

        {/* ── Flow Direction Arrows ───────────────────────────────────── */}
        {flood && flowArrowsData && flowArrowsData.features.length > 0 && (
          <Source id="flow-arrows" type="geojson" data={flowArrowsData}>
            <Layer
              id="flow-direction-layer"
              type="symbol"
              source="flow-arrows"
              layout={{
                visibility: "visible", // Forzamos a que se vea siempre
                "text-field": "➤",     // Usamos un carácter de flecha en vez de imagen
                "text-rotate": ["get", "bearing"],
                "text-allow-overlap": true,
                "text-size": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10, 12, // Más pequeñas de lejos
                  14, 28  // Más grandes de cerca
                ],
                "text-rotation-alignment": "map",
                "text-pitch-alignment": "map", // Hace que la flecha se tumbe en 3D
              }}
              paint={{
                "text-color": "#22d3ee",       // Cyan brillante
                "text-halo-color": "#000000",  // Borde negro para que resalte
                "text-halo-width": 1.5,
                "text-opacity": 0.9,
              }}
            />
          </Source>
        )}

        {/* ── Flood-runoff overlay ─────────────────────────────────────── */}
        {/*<Source
          id="flood-risk-img"
          type="image"
          url="/static/risk_layer.png"
          coordinates={RISK_BBOX}
        >
          
          <Layer
            id="flood-risk-layer"
            type="raster"
            paint={{
              "raster-opacity": flood ? 0.6 : 0,
              "raster-opacity-transition": { duration: 500 },
            }}
          />
        </Source>
        */}

        {/* ── Erosion susceptibility overlay ───────────────────────────── */}
        <Source
          id="erosion-risk-img"
          type="image"
          url="/static/erosion_rusle.png"
          coordinates={RISK_BBOX}
        >
          <Layer
            id="erosion-risk-layer"
            type="raster"
            paint={{
              "raster-opacity": erosion ? 0.6 : 0,
              "raster-opacity-transition": { duration: 500 },
            }}
          />
        </Source>

        {/* ── Citizen Observations ────────────────────────────────────── */}
        {fused && citizenGeoJson && (
          <Source id="citizen-source" type="geojson" data={citizenGeoJson}>
            {/* Glow ring for severity 3 (severe) */}
            <Layer
              id="citizen-glow-layer"
              type="circle"
              source="citizen-source"
              filter={["==", ["get", "severity"], 3]}
              paint={{
                "circle-color": CITIZEN_SEVERITY_EXPRESSION,
                "circle-radius": 16,
                "circle-opacity": 0.2,
                "circle-blur": 2,
              }}
            />
            {/* Main circle */}
            <Layer
              id="citizen-circle-layer"
              type="circle"
              source="citizen-source"
              paint={{
                "circle-color": CITIZEN_SEVERITY_EXPRESSION,
                "circle-radius": CITIZEN_RADIUS_EXPRESSION,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1.5,
                "circle-opacity": 0.85,
              }}
            />
          </Source>
        )}

        {/* ── Reforestation Zone (Plant Forest) ───────────────────────── */}
        {forestZone && (
          <Source
            id="forest-source"
            type="geojson"
            data={{
              type: "FeatureCollection",
              features: [
                {
                  type: "Feature",
                  geometry: {
                    type: "Point",
                    coordinates: [forestZone.lon, forestZone.lat],
                  },
                  properties: {},
                },
              ],
            }}
          >
            <Layer
              id="forest-glow-layer"
              type="circle"
              source="forest-source"
              paint={{
                "circle-color": "#22c55e",
                "circle-radius": 40,
                "circle-opacity": 0.15,
                "circle-blur": 3,
              }}
            />
            <Layer
              id="forest-circle-layer"
              type="circle"
              source="forest-source"
              paint={{
                "circle-color": "#22c55e",
                "circle-radius": 14,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2.5,
                "circle-opacity": 0.7,
              }}
            />
            <Layer
              id="forest-pulse-layer"
              type="circle"
              source="forest-source"
              paint={{
                "circle-color": "#22c55e",
                "circle-radius": 20,
                "circle-opacity": 0.25,
                "circle-blur": 2,
              }}
            />
          </Source>
        )}

        {/* ── Glassmorphic Popup (hover: roads & citizens) ────────────── */}
        {popup && (
          <Popup
            longitude={popup.coordinates[0]}
            latitude={popup.coordinates[1]}
            closeButton={false}
            closeOnClick={false}
            onClose={() => setPopup(null)}
            style={{ zIndex: 999 }}
          >
            <div
              className="rounded-xl border border-white/20 px-3 py-2 text-xs leading-relaxed shadow-xl"
              style={{
                background: "oklch(0.15 0.03 250 / 0.92)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                minWidth: 180,
              }}
            >
              {popup.type === "road" ? (
                <RoadPopupContent properties={popup.properties} />
              ) : (
                <CitizenPopupContent properties={popup.properties} />
              )}
            </div>
          </Popup>
        )}

        {/* ── Selected Building Popup (click-based, persistent) ─────────── */}
        {selectedBuilding && (
          <Popup
            longitude={selectedBuilding.coordinates[0]}
            latitude={selectedBuilding.coordinates[1]}
            closeButton={true}
            closeOnClick={false}
            onClose={() => setSelectedBuilding(null)}
            style={{ zIndex: 1000 }}
          >
            <div
              className="rounded-xl border border-white/20 p-3 text-xs leading-relaxed shadow-xl"
              style={{
                background: "oklch(0.15 0.03 250 / 0.92)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                minWidth: 220,
              }}
            >
              <BuildingPopupContent properties={selectedBuilding.properties} />
            </div>
          </Popup>
        )}
      </Map>

      {/* ── Loading spinner ──────────────────────────────────────────── */}
      {showLoadingLayer && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <div className="flex items-center gap-2.5 rounded-xl border border-glass-border bg-background/70 px-4 py-3 backdrop-blur-md">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span className="text-xs font-medium text-muted-foreground">
              Loading {activeScenario} flood data…
            </span>
          </div>
        </div>
      )}

      {/* ── Error toast ─────────────────────────────────────────────── */}
      {scenarioError && !loadingScenario && (
        <div className="pointer-events-none absolute bottom-6 left-1/2 z-10 -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/15 px-4 py-2.5 text-xs font-medium text-destructive backdrop-blur-md">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            {scenarioError}
          </div>
        </div>
      )}

      {/* Vignette overlay */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 45%, oklch(0.10 0.03 250 / 0.65) 100%)",
        }}
      />
    </div>
  );
}

// ─── Popup Content Components ─────────────────────────────────────────────

function RoadPopupContent({ properties }: { properties: Record<string, unknown> }) {
  const status = (properties.status as string) ?? "unknown";
  const depth = properties.flood_depth_m as number | undefined;
  const velocity = properties.velocity_ms as number | undefined;
  const name = properties.name as string | undefined;

  return (
    <div className="space-y-1.5">
      {name && (
        <p className="text-[11px] font-semibold text-primary">{name}</p>
      )}
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${status === "passable"
              ? "bg-green-400"
              : status === "emergency_only"
                ? "bg-orange-400"
                : "bg-red-400"
            }`}
        />
        <span className="font-medium capitalize text-foreground">
          {status.replace("_", " ")}
        </span>
      </div>
      {depth !== undefined && (
        <p className="text-muted-foreground">
          Flood Depth: <span className="font-semibold tabular-nums text-foreground">{depth.toFixed(2)} m</span>
        </p>
      )}
      {velocity !== undefined && (
        <p className="text-muted-foreground">
          Velocity: <span className="font-semibold tabular-nums text-foreground">{velocity.toFixed(1)} m/s</span>
        </p>
      )}
    </div>
  );
}

function BuildingPopupContent({ properties }: { properties: Record<string, unknown> }) {
  const depth = properties.depth_m as number | undefined;
  const velocity = properties.velocity_ms as number | undefined;
  const hazardScore = properties.hazard_score as number | undefined;
  const riskLevel = (properties.risk_level as string) ?? "unknown";
  const isCritical = properties.is_critical as boolean | undefined;
  const buildingId = properties.id as string | number | undefined;

  const isFlooded = depth != null && depth > 0;

  const riskColor: Record<string, string> = {
    critical: "text-purple-400",
    high: "text-red-400",
    moderate: "text-orange-400",
    low: "text-green-400",
  };

  const riskBadgeBg: Record<string, string> = {
    critical: "bg-purple-500/20 border-purple-500/40",
    high: "bg-red-500/20 border-red-500/40",
    moderate: "bg-orange-500/20 border-orange-500/40",
    low: "bg-green-500/20 border-green-500/40",
  };

  const buildingLabel = isCritical ? "Critical Asset" : buildingId ? `Building #${buildingId}` : "Building";

  return (
    <div className="space-y-2">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {isFlooded ? (
            <TriangleAlert className="h-4 w-4 text-red-400" />
          ) : (
            <ShieldCheck className="h-4 w-4 text-green-400" />
          )}
          <span className="text-[11px] font-semibold text-foreground">
            {buildingLabel}
          </span>
        </div>
        {isCritical && (
          <span className="rounded border border-white/40 bg-white/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest text-white">
            Critical
          </span>
        )}
      </div>

      {/* ── Flood Status ─────────────────────────────────────────────── */}
      <div className={`flex items-center gap-1.5 rounded-md border px-2 py-1 ${isFlooded
          ? "border-red-500/30 bg-red-500/10"
          : "border-green-500/30 bg-green-500/10"
        }`}>
        <span className={`text-[10px] font-bold uppercase tracking-wider ${isFlooded ? "text-red-400" : "text-green-400"
          }`}>
          {isFlooded ? "FLOODED" : "SAFE"}
        </span>
        {depth !== undefined && (
          <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">
            {depth.toFixed(2)}m depth
          </span>
        )}
      </div>

      {/* ── Metrics ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        {velocity !== undefined && (
          <div>
            <span className="text-[10px] text-muted-foreground">Velocity</span>
            <p className="font-semibold tabular-nums text-foreground">
              {velocity.toFixed(1)} m/s
            </p>
          </div>
        )}
        {hazardScore !== undefined && (
          <div>
            <span className="text-[10px] text-muted-foreground">Hazard Score</span>
            <p className="font-semibold tabular-nums text-foreground">
              {hazardScore.toFixed(2)}
            </p>
          </div>
        )}
      </div>

      {/* ── Risk Level Badge ──────────────────────────────────────────── */}
      <div className={`rounded-md border px-2 py-1 ${riskBadgeBg[riskLevel] ?? "bg-secondary/30 border-white/10"}`}>
        <span className={`text-[10px] font-bold uppercase tracking-wider ${riskColor[riskLevel] ?? "text-muted-foreground"}`}>
          {riskLevel} Risk
        </span>
      </div>
    </div>
  );
}

function CitizenPopupContent({ properties }: { properties: Record<string, unknown> }) {
  const eventType = (properties.event_type as string) ?? "other";
  const severity = (properties.severity as number) ?? 1;
  const description = (properties.description as string) ?? "";
  const reporter = (properties.reporter as string) ?? "Anonymous";
  const createdAt = properties.created_at as string | undefined;

  const severityColors: Record<number, string> = {
    1: "text-warning",
    2: "text-orange-400",
    3: "text-destructive",
  };

  const severityDots: Record<number, string> = {
    1: "bg-warning",
    2: "bg-orange-500",
    3: "bg-destructive",
  };

  return (
    <div className="space-y-1.5" style={{ minWidth: 200 }}>
      <div className="flex items-center gap-1.5">
        <span className="text-primary">{EVENT_TYPE_ICONS[eventType] ?? null}</span>
        <span className="text-[11px] font-semibold text-foreground">
          {EVENT_LABELS[eventType] ?? eventType}
        </span>
        <span className={`ml-auto text-[10px] font-bold uppercase tracking-wider ${severityColors[severity] ?? "text-muted-foreground"}`}>
          {SEVERITY_LABELS[severity] ?? severity}
        </span>
      </div>

      <div className="flex items-center gap-1">
        {[1, 2, 3].map((s) => (
          <span
            key={s}
            className={`inline-block h-1.5 w-1.5 rounded-full ${s <= severity ? severityDots[s] : "bg-secondary/60"
              }`}
          />
        ))}
      </div>

      {description && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}

      <div className="flex items-center justify-between pt-0.5">
        <span className="text-[10px] font-medium text-foreground/70">{reporter}</span>
        {createdAt && (
          <span className="text-[10px] text-muted-foreground">
            {(() => {
              const diff = Date.now() - new Date(createdAt).getTime();
              const mins = Math.floor(diff / 60000);
              if (mins < 1) return "Just now";
              if (mins < 60) return `${mins}m ago`;
              const hrs = Math.floor(mins / 60);
              return `${hrs}h ago`;
            })()}
          </span>
        )}
      </div>
    </div>
  );
}
