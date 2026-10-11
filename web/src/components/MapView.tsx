import { useEffect, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type ImageSource, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Feature, FeatureCollection, LineString, Point } from "geojson";
import { useStatic } from "../lib/useData";
import { useStore, clock } from "../lib/store";
import { frame, paint, query, LEGENDS, HAZARD_COLORS, HAZARD_NAMES, type CellValues } from "../lib/raster";
import type { ScenarioImpact, ScenarioRasters } from "../lib/data";

interface Props {
  scenario: { impact: ScenarioImpact; rasters: ScenarioRasters } | null;
  route: FeatureCollection<LineString> | null;
  reports: FeatureCollection<Point>;
  onPick?: (lonlat: [number, number]) => void;
}

const HC = (k: number) => `rgb(${HAZARD_COLORS[k].join(",")})`;

const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 18,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    },
    dem: {
      type: "raster-dem",
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      encoding: "terrarium",
      tileSize: 256,
      maxzoom: 14,
      attribution: "Terrain: AWS Terrain Tiles (Mapzen); flood model: Atlas (Copernicus DEM, ERA5, IMERG)",
    },
  },
  layers: [
    { id: "imagery", type: "raster", source: "imagery", paint: { "raster-saturation": -0.35, "raster-brightness-max": 0.85 } },
    { id: "hillshade", type: "hillshade", source: "dem", paint: { "hillshade-exaggeration": 0.35, "hillshade-shadow-color": "#1b2430" } },
  ],
};

export default function MapView({ scenario, route, reports, onPick }: Props) {
  const data = useStatic();
  const { layer, time, t0, terrain3d, selectedVillage, fly, set } = useStore();
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [ready, setReady] = useState(false);
  const [probe, setProbe] = useState<{ lngLat: [number, number]; v: CellValues | null; text: string[] } | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const locate = frame(data.meta.raster.corners_lonlat, data.meta.raster.width, data.meta.raster.height);

  // --- map + static layers -------------------------------------------------------------------
  useEffect(() => {
    const m = new maplibregl.Map({
      container: box.current!, style: STYLE, center: [-7.15, 31.2], zoom: 10.3, maxPitch: 75,
      attributionControl: { compact: true }, canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    m.on("load", () => {
      const r = data.meta.raster;
      const c = document.createElement("canvas");
      c.width = r.width;
      c.height = r.height;
      canvas.current = c;
      m.addSource("catchment", { type: "geojson", data: data.catchment });
      m.addLayer({ id: "catchment-line", type: "line", source: "catchment", paint: { "line-color": "#f5f7fa", "line-width": 1.6, "line-dasharray": [3, 2], "line-opacity": 0.8 } });
      m.addSource("subbasins", { type: "geojson", data: data.subbasins });
      m.addLayer({ id: "subbasin-line", type: "line", source: "subbasins", paint: { "line-color": "#c9d4e2", "line-width": 0.6, "line-opacity": 0.45 } });
      m.addSource("streams", { type: "geojson", data: data.streams });
      m.addLayer({ id: "streams", type: "line", source: "streams", paint: { "line-color": "#8ecae6", "line-width": ["interpolate", ["linear"], ["get", "drainage_km2"], 1, 0.4, 100, 1.4, 700, 2.4], "line-opacity": 0.55 } });
      m.addSource("flood", { type: "image", url: c.toDataURL(), coordinates: r.corners_lonlat as [[number, number], [number, number], [number, number], [number, number]] });
      m.addLayer({ id: "flood", type: "raster", source: "flood", paint: { "raster-resampling": "nearest", "raster-opacity": 0.85, "raster-fade-duration": 0 } });
      m.addSource("roads", { type: "geojson", data: data.roads });
      m.addLayer({
        id: "roads", type: "line", source: "roads", layout: { "line-cap": "round" },
        paint: { "line-color": "#e8edf3", "line-opacity": 0.85, "line-width": ["match", ["get", "highway"], ["primary", "trunk"], 3, ["secondary", "tertiary"], 2.2, ["path", "footway", "steps"], 0.8, 1.3] },
      });
      const centroids: FeatureCollection<Point> = {
        type: "FeatureCollection",
        features: data.buildings.features.map((f, i) => {
          const ring = f.geometry.coordinates[0];
          const x = ring.reduce((s, p) => s + p[0], 0) / ring.length, y = ring.reduce((s, p) => s + p[1], 0) / ring.length;
          return { type: "Feature", id: i, properties: { ...f.properties }, geometry: { type: "Point", coordinates: [x, y] } };
        }),
      };
      m.addSource("buildings", { type: "geojson", data: data.buildings });
      m.addSource("building-pts", { type: "geojson", data: centroids });
      m.addLayer({ id: "buildings", type: "fill", source: "buildings", minzoom: 13.5, paint: { "fill-color": "#9aa3ad", "fill-outline-color": "#1b2430", "fill-opacity": 0.9 } });
      m.addLayer({ id: "building-pts", type: "circle", source: "building-pts", maxzoom: 13.5, paint: { "circle-radius": 2.2, "circle-color": "#9aa3ad", "circle-stroke-width": 0 } });
      m.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "route-casing", type: "line", source: "route", paint: { "line-color": "#0b1220", "line-width": 7 } });
      m.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": "#22c55e", "line-width": 4, "line-dasharray": [1.5, 1] } });
      m.addSource("reports", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "reports", type: "circle", source: "reports", paint: { "circle-radius": 7, "circle-color": ["match", ["get", "severity"], 3, "#d62828", 2, "#f49136", "#f6d55c"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      m.fitBounds([-7.40, 31.03, -6.97, 31.38], { padding: { top: 70, bottom: 120, left: 80, right: 420 }, duration: 0 });
      setReady(true);
    });
    m.on("click", (e) => {
      const ll: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (pickRef.current) {
        pickRef.current(ll);
        return;
      }
      setProbe({ lngLat: ll, v: null, text: [] });
    });
    return () => m.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- villages, shelters as HTML markers (no glyph server needed) ---------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    markers.current.forEach((k) => k.remove());
    markers.current = [];
    const vimp = scenario?.impact.villages ?? {};
    for (const f of data.villages.features) {
      const v = vimp[f.properties.name];
      if (!v && f.properties.place === "hamlet") continue;
      const el = document.createElement("button");
      const iso = !!v?.isolation && (time === null || (time >= v.isolation.from_h && time < v.isolation.to_h));
      const hit = !!v && v.buildings_affected > 0 && (time === null || (v.first_water_h !== null && time >= v.first_water_h));
      el.className = `vmark${hit ? " hit" : ""}${iso ? " iso" : ""}${selectedVillage === f.properties.name ? " sel" : ""}`;
      el.title = f.properties.name_local || f.properties.name;
      el.innerHTML = `<span class="dot"></span><span class="lbl">${f.properties.name}</span>`;
      el.onclick = (ev) => {
        ev.stopPropagation();
        set({ selectedVillage: f.properties.name });
      };
      markers.current.push(new maplibregl.Marker({ element: el, anchor: "left" }).setLngLat(f.geometry.coordinates as [number, number]).addTo(m));
    }
    for (const f of data.shelters.features) {
      const el = document.createElement("div");
      el.className = "smark";
      el.title = `Shelter: ${f.properties.name || f.properties.kind} (${f.properties.village})`;
      el.textContent = "⛺";
      markers.current.push(new maplibregl.Marker({ element: el }).setLngLat(f.geometry.coordinates as [number, number]).addTo(m));
    }
  }, [ready, scenario, time, selectedVillage, data, set]);

  // --- flood raster for scenario / layer / time ----------------------------------------------
  useEffect(() => {
    const m = map.current, c = canvas.current;
    if (!m || !ready || !c) return;
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(c.width, c.height);
    if (scenario) paint(scenario.rasters, layer, time, data.meta.design_burst_h, img.data);
    ctx.putImageData(img, 0, 0);
    (m.getSource("flood") as ImageSource).updateImage({ url: c.toDataURL(), coordinates: data.meta.raster.corners_lonlat as [[number, number], [number, number], [number, number], [number, number]] });
  }, [ready, scenario, layer, time, data]);

  // --- buildings and roads coloured by scenario + time ------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const T = time ?? 1e6;
    const b = scenario?.impact.buildings;
    const withState = (fc: typeof data.buildings | FeatureCollection<Point>) => ({
      ...fc,
      features: fc.features.map((f, i) => ({ ...f, properties: { ...f.properties, hr: b ? b.hr_class[i] : 0, arr: b ? b.arrival_h[i] : -1, str: b ? b.structural[i] : 0 } })),
    });
    (m.getSource("buildings") as GeoJSONSource).setData(withState(data.buildings) as FeatureCollection);
    const pts = (m.getSource("building-pts") as GeoJSONSource);
    pts.getData().then((d) => pts.setData(withState(d as FeatureCollection<Point>) as FeatureCollection));
    const color: maplibregl.ExpressionSpecification = ["case", ["all", [">", ["get", "hr"], 0], ["<=", ["get", "arr"], T]],
      ["match", ["get", "hr"], 1, HC(1), 2, HC(2), 3, HC(3), HC(4)], "#9aa3ad"];
    m.setPaintProperty("buildings", "fill-color", color);
    m.setPaintProperty("building-pts", "circle-color", color);
    m.setPaintProperty("building-pts", "circle-radius", ["case", [">", ["get", "hr"], 0], 3.4, 1.8]);
    const s = scenario?.impact.segments;
    (m.getSource("roads") as GeoJSONSource).setData({
      ...data.roads,
      features: data.roads.features.map((f, i) => ({
        ...f,
        properties: { ...f.properties, st: s ? s.status[i] : 0, cf: s ? s.car_from[i] : -1, ct: s ? s.car_to[i] : -1, xf: s ? s.closed_from[i] : -1, xt: s ? s.closed_to[i] : -1 },
      })),
    } as FeatureCollection);
    const roadColor: maplibregl.ExpressionSpecification = time === null
      ? ["match", ["get", "st"], 2, "#ff3b30", 1, "#ff9f0a", "#e8edf3"]
      : ["case", ["all", [">=", ["get", "xf"], 0], [">=", T, ["get", "xf"]], ["<", T, ["get", "xt"]]], "#ff3b30",
        ["all", [">=", ["get", "cf"], 0], [">=", T, ["get", "cf"]], ["<", T, ["get", "ct"]]], "#ff9f0a", "#e8edf3"];
    m.setPaintProperty("roads", "line-color", roadColor);
  }, [ready, scenario, time, data]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("route") as GeoJSONSource).setData(route ?? { type: "FeatureCollection", features: [] });
    (m.getSource("reports") as GeoJSONSource).setData(reports);
  }, [ready, route, reports]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    if (terrain3d) {
      m.setTerrain({ source: "dem", exaggeration: 1.4 });
      m.easeTo({ pitch: 60, duration: 800 });
    } else {
      m.setTerrain(null);
      m.easeTo({ pitch: 0, duration: 600 });
    }
  }, [ready, terrain3d]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !selectedVillage) return;
    const f = data.villages.features.find((v) => v.properties.name === selectedVillage);
    if (f) m.flyTo({ center: f.geometry.coordinates as [number, number], zoom: Math.max(m.getZoom(), 14), duration: 900 });
  }, [ready, selectedVillage, data]);

  useEffect(() => {
    if (map.current && ready && fly) map.current.flyTo({ center: fly.ll, zoom: Math.max(map.current.getZoom(), 14.5), duration: 900 });
  }, [ready, fly]);

  // --- probe (click to inspect) ----------------------------------------------------------------
  useEffect(() => {
    if (!probe || !scenario) return;
    const px = locate(probe.lngLat[0], probe.lngLat[1]);
    const v = px ? query(scenario.rasters, px[0], px[1]) : null;
    const text: string[] = [];
    const m = map.current!;
    const pt = m.project(probe.lngLat);
    const feats = m.queryRenderedFeatures([[pt.x - 4, pt.y - 4], [pt.x + 4, pt.y + 4]], { layers: ["buildings", "building-pts", "roads"] });
    const bf = feats.find((f) => f.layer.id !== "roads");
    if (bf) {
      const p = bf.properties as Record<string, number | string>;
      text.push(`${p.type === "residential" ? "House" : String(p.type)}${p.facility_name ? ` · ${p.facility_name}` : ""} — ${p.village}`);
      if (Number(p.hr) > 0) text.push(`Hazard: ${HAZARD_NAMES[Number(p.hr)]}${Number(p.str) === 2 ? " · collapse possible" : Number(p.str) === 1 ? " · damage likely" : ""} · water from ${clock(t0, Number(p.arr))}`);
      if (Number(p.pop) > 0) text.push(`~${Number(p.pop).toFixed(1)} residents (estimate)`);
    }
    const rf = feats.find((f) => f.layer.id === "roads");
    if (rf) {
      const p = rf.properties as Record<string, number | string>;
      const st = Number(p.st);
      text.push(`${p.label}${p.ford === "true" || p.ford === true as unknown ? " · ford" : ""}: ${st === 2 ? `closed (4WD unsafe) ${clock(t0, Number(p.xf), false)}–${clock(t0, Number(p.xt), false)}` : st === 1 ? `cars unsafe ${clock(t0, Number(p.cf), false)}–${clock(t0, Number(p.ct), false)}` : "open"}`);
    }
    setProbe((o) => (o ? { ...o, v, text } : o));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probe?.lngLat[0], probe?.lngLat[1], scenario]);

  const legend = LEGENDS[layer];
  return (
    <div className="map-wrap">
      <div ref={box} className="map" />
      {probe && (
        <div className="probe">
          <button className="x" onClick={() => setProbe(null)} aria-label="Close">×</button>
          {!scenario && <p>Choose a scenario to inspect flood values.</p>}
          {probe.v && probe.v.depth > 0 ? (
            <dl>
              <dt>Max depth</dt><dd>{probe.v.depth.toFixed(2)} m</dd>
              <dt>Max velocity</dt><dd>{probe.v.velocity.toFixed(1)} m/s</dd>
              <dt>Hazard</dt><dd>{["—", "Low", "Moderate", "Significant", "Extreme"][Math.min(4, probe.v.hazard <= 0 ? 0 : probe.v.hazard < 0.75 ? 1 : probe.v.hazard < 1.25 ? 2 : probe.v.hazard < 2 ? 3 : 4)]} (HR {probe.v.hazard.toFixed(2)})</dd>
              <dt>Water arrives</dt><dd>{probe.v.firstWater ? clock(t0, probe.v.firstWater) : "—"}</dd>
              <dt>Over 0.3 m for</dt><dd>{probe.v.duration03.toFixed(1)} h</dd>
            </dl>
          ) : scenario ? <p>No modelled flooding here in this scenario.</p> : null}
          {probe.text.map((t) => <p key={t} className="feat">{t}</p>)}
        </div>
      )}
      <div className="legend">
        <strong>{legend.title}</strong>
        {legend.items.map(([c, l]) => <span key={l}><i style={{ background: c }} />{l}</span>)}
        <strong>Roads</strong>
        <span><i style={{ background: "#ff3b30" }} />closed (4WD unsafe)</span>
        <span><i style={{ background: "#ff9f0a" }} />cars unsafe</span>
      </div>
    </div>
  );
}

export type { Feature };
