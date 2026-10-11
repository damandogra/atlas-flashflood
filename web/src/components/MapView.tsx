import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type ExpressionSpecification, type GeoJSONSource, type ImageSource, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection, LineString, Point } from "geojson";
import { useStatic } from "../lib/useData";
import { useStore, clock } from "../lib/store";
import { frame, paint, query, LEGENDS, HAZARD_COLORS, HAZARD_NAMES, type CellValues } from "../lib/raster";
import { villageState, ROAD_TEXT } from "../lib/status";
import type { ScenarioImpact, ScenarioRasters } from "../lib/data";

interface Props {
  scenario: { impact: ScenarioImpact; rasters: ScenarioRasters } | null;
  route: FeatureCollection<LineString> | null;
  reports: FeatureCollection<Point>;
  onPick?: (lonlat: [number, number]) => void;
}

const HC = (k: number) => `rgb(${HAZARD_COLORS[k].join(",")})`;
const RED = "#ff3b30", ORANGE = "#ff9500", GREEN = "#34c759";
type Corners = [[number, number], [number, number], [number, number], [number, number]];

const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256, maxzoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    },
    dem: {
      type: "raster-dem", tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      encoding: "terrarium", tileSize: 256, maxzoom: 14,
      attribution: "Terrain: AWS Terrain Tiles (Mapzen); flood model: Atlas (Copernicus DEM, ERA5, IMERG)",
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#efe9df" } },
    { id: "imagery", type: "raster", source: "imagery", paint: { "raster-saturation": -0.55, "raster-brightness-max": 0.62, "raster-contrast": 0.05 } },
    { id: "hillshade", type: "hillshade", source: "dem", paint: { "hillshade-exaggeration": 0.3, "hillshade-shadow-color": "#1b2430", "hillshade-highlight-color": "#ffffff" } },
  ],
};

/** Width that grows with zoom: [width at z9, width at z15]. The zoom interpolation must be the
 *  outermost expression, so data-driven widths go *inside* each stop (zwBy). */
const zw = (a: number, b: number): ExpressionSpecification => ["interpolate", ["exponential", 1.6], ["zoom"], 9, a, 15, b];
const zwBy = (a: ExpressionSpecification, b: ExpressionSpecification): ExpressionSpecification =>
  ["interpolate", ["exponential", 1.6], ["zoom"], 9, a, 15, b];
const NONE: ExpressionSpecification = ["==", ["get", "st"], -99];

/** Road/ford state expressions for time T (null = whole event). */
function stateExpr(T: number | null) {
  if (T === null) return { closed: ["==", ["get", "st"], 2] as ExpressionSpecification, unsafe: ["==", ["get", "st"], 1] as ExpressionSpecification };
  const within = (a: string, b: string): ExpressionSpecification => ["all", [">=", ["get", a], 0], [">=", T, ["get", a]], ["<", T, ["get", b]]];
  return { closed: within("xf", "xt"), unsafe: within("cf", "ct") };
}

const ROAD_KIND: Record<string, string> = {
  primary: "Main road", trunk: "Main road", secondary: "Regional road", tertiary: "Provincial road",
  unclassified: "Local road", residential: "Village street", service: "Service road", track: "Dirt track",
  path: "Footpath", footway: "Footpath", steps: "Steps", living_street: "Village street",
};
const roadName = (label: string, highway: string) => (label === `${highway} road` ? ROAD_KIND[highway] ?? "Road" : label);

function diamond(color: string) {
  const s = 28, c = document.createElement("canvas");
  c.width = c.height = s;
  const g = c.getContext("2d")!;
  g.translate(s / 2, s / 2);
  g.rotate(Math.PI / 4);
  g.fillStyle = color;
  g.strokeStyle = "#0b1220";
  g.lineWidth = 3;
  g.fillRect(-8, -8, 16, 16);
  g.strokeRect(-8, -8, 16, 16);
  return g.getImageData(0, 0, s, s);
}

export default function MapView({ scenario, route, reports, onPick }: Props) {
  const data = useStatic();
  const { layer, time, t0, terrain3d, basemap, selectedVillage, fly, set } = useStore();
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [ready, setReady] = useState(false);
  const [legendOpen, setLegendOpen] = useState(true);
  const [probe, setProbe] = useState<{ lngLat: [number, number]; v: CellValues | null; text: string[] } | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const scnRef = useRef(scenario);
  scnRef.current = scenario;
  const tRef = useRef({ time, t0 });
  tRef.current = { time, t0 };
  const locate = frame(data.meta.raster.corners_lonlat, data.meta.raster.width, data.meta.raster.height);

  const population = useMemo(() => {
    const p: Record<string, number> = {};
    for (const f of data.buildings.features) p[f.properties.village] = (p[f.properties.village] ?? 0) + f.properties.pop;
    return p;
  }, [data]);

  const fordPoints = useMemo<FeatureCollection<Point>>(() => ({
    type: "FeatureCollection",
    features: data.roads.features.flatMap((f, i) => {
      if (!f.properties.ford) return [];
      const c = f.geometry.coordinates;
      const mid = c[Math.floor(c.length / 2)];
      return [{ type: "Feature" as const, id: i, properties: { seg: i, label: f.properties.label, highway: f.properties.highway }, geometry: { type: "Point" as const, coordinates: mid } }];
    }),
  }), [data]);

  // --- map + layers ------------------------------------------------------------------------------
  useEffect(() => {
    const m = new maplibregl.Map({
      container: box.current!, style: STYLE, center: [-7.15, 31.2], zoom: 10.3, maxPitch: 75,
      attributionControl: { compact: true }, canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    map.current = m;
    if (import.meta.env.DEV) (window as unknown as { __atlasMap: MLMap }).__atlasMap = m;
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    m.on("load", () => {
      const r = data.meta.raster;
      const c = document.createElement("canvas");
      c.width = r.width;
      c.height = r.height;
      canvas.current = c;
      for (const [name, col] of [["ford-red", RED], ["ford-orange", ORANGE], ["ford-green", GREEN]] as const) m.addImage(name, diamond(col));

      m.addSource("catchment", { type: "geojson", data: data.catchment });
      m.addLayer({ id: "catchment-casing", type: "line", source: "catchment", paint: { "line-color": "#0b1220", "line-width": zw(4, 7), "line-opacity": 0.5 } });
      m.addLayer({ id: "catchment-line", type: "line", source: "catchment", paint: { "line-color": "#ffd166", "line-width": zw(2, 3.5), "line-dasharray": [3, 1.5] } });
      m.addSource("subbasins", { type: "geojson", data: data.subbasins });
      m.addLayer({ id: "subbasin-line", type: "line", source: "subbasins", paint: { "line-color": "#ffffff", "line-width": zw(0.6, 1.2), "line-opacity": 0.3 } });
      m.addSource("streams", { type: "geojson", data: data.streams });
      m.addLayer({
        id: "streams", type: "line", source: "streams", layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#4cc9f0", "line-opacity": 0.9,
          "line-width": ["interpolate", ["linear"], ["zoom"],
            9, ["interpolate", ["linear"], ["get", "drainage_km2"], 1, 0.6, 50, 1.6, 700, 3.5],
            15, ["interpolate", ["linear"], ["get", "drainage_km2"], 1, 1.5, 50, 4, 700, 10]],
        },
      });
      m.addSource("flood", { type: "image", url: c.toDataURL(), coordinates: r.corners_lonlat as Corners });
      m.addLayer({ id: "flood", type: "raster", source: "flood", paint: { "raster-resampling": "linear", "raster-opacity": 0.82, "raster-fade-duration": 0 } });

      m.addSource("roads", { type: "geojson", data: data.roads });
      m.addLayer({
        id: "roads-base", type: "line", source: "roads", layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#e5e9ef", "line-opacity": 0.6,
          "line-width": zwBy(
            ["match", ["get", "highway"], ["primary", "trunk"], 2.2, ["secondary", "tertiary"], 1.6, ["path", "footway", "steps"], 0.5, 0.9],
            ["match", ["get", "highway"], ["primary", "trunk"], 7, ["secondary", "tertiary"], 5, ["path", "footway", "steps"], 1.6, 3]),
        },
      });
      m.addLayer({ id: "roads-alert-casing", type: "line", source: "roads", filter: NONE, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#0b1220", "line-width": zw(5, 13) } });
      m.addLayer({ id: "roads-alert", type: "line", source: "roads", filter: NONE, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": RED, "line-width": zw(3, 9) } });

      m.addSource("buildings", { type: "geojson", data: data.buildings });
      const centroids: FeatureCollection<Point> = {
        type: "FeatureCollection",
        features: data.buildings.features.map((f, i) => {
          const ring = f.geometry.coordinates[0];
          const x = ring.reduce((s, p) => s + p[0], 0) / ring.length, y = ring.reduce((s, p) => s + p[1], 0) / ring.length;
          return { type: "Feature", id: i, properties: { ...f.properties }, geometry: { type: "Point", coordinates: [x, y] } };
        }),
      };
      m.addSource("building-pts", { type: "geojson", data: centroids });
      m.addLayer({ id: "buildings", type: "fill", source: "buildings", minzoom: 14, paint: { "fill-color": "#9aa3ad", "fill-opacity": 0.85 } });
      m.addLayer({ id: "buildings-outline", type: "line", source: "buildings", minzoom: 14, paint: { "line-color": "#0b1220", "line-width": 1.2 } });
      m.addLayer({ id: "building-pts", type: "circle", source: "building-pts", maxzoom: 14, paint: { "circle-radius": 2, "circle-color": "#9aa3ad" } });

      m.addSource("fords", { type: "geojson", data: fordPoints });
      m.addLayer({ id: "fords", type: "symbol", source: "fords", minzoom: 10.3, layout: { "icon-image": "ford-green", "icon-size": zw(0.55, 1.1), "icon-allow-overlap": true } });

      m.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "route-casing", type: "line", source: "route", paint: { "line-color": "#0b1220", "line-width": zw(7, 12) } });
      m.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": GREEN, "line-width": zw(4, 7), "line-dasharray": [1.5, 1] } });
      m.addSource("reports", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "reports", type: "circle", source: "reports", paint: { "circle-radius": zw(6, 10), "circle-color": ["match", ["get", "severity"], 3, RED, 2, ORANGE, "#ffd60a"], "circle-stroke-color": "#fff", "circle-stroke-width": 2.5 } });
      m.fitBounds([-7.40, 31.03, -6.97, 31.38], { padding: { top: 70, bottom: 150, left: 80, right: 420 }, duration: 0 });
      setReady(true);
    });

    // hover tooltips
    const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "tip", offset: 12 });
    const hoverLayers = ["fords", "roads-alert", "building-pts", "buildings"];
    m.on("mousemove", (e) => {
      if (!m.getLayer("fords")) return;
      const f = m.queryRenderedFeatures(e.point, { layers: hoverLayers })[0];
      if (!f) { tip.remove(); m.getCanvas().style.cursor = ""; return; }
      m.getCanvas().style.cursor = "pointer";
      const p = f.properties as Record<string, number | string>;
      const { time: T, t0: T0 } = tRef.current;
      let html = "";
      if (f.layer.id === "fords" || f.layer.id === "roads-alert") {
        const st = Number(p.xf) >= 0 && (T === null ? Number(p.st) === 2 : T >= Number(p.xf) && T < Number(p.xt)) ? 2
          : Number(p.cf) >= 0 && (T === null ? Number(p.st) >= 1 : T >= Number(p.cf) && T < Number(p.ct)) ? 1 : 0;
        const [a, b] = st === 2 ? [Number(p.xf), Number(p.xt)] : st === 1 ? [Number(p.cf), Number(p.ct)] : [0, 0];
        const win = st ? `From ${clock(T0, a)}, for ${(b - a).toFixed(1)} h` : "";
        const road = roadName(String(p.label), String(p.highway));
        html = `<b>${f.layer.id === "fords" ? "Ford · " : ""}${road}</b><span class="s${st}">${ROAD_TEXT[st]}</span>${win ? `<small>${win}</small>` : ""}`;
      } else {
        const hr = Number(p.hr);
        if (!hr) { tip.remove(); m.getCanvas().style.cursor = ""; return; }
        html = `<b>${p.type === "residential" ? "House" : p.type}${p.facility_name ? ` · ${p.facility_name}` : ""}</b><span class="h${hr}">${HAZARD_NAMES[hr]} danger</span><small>${p.village} · water from ${clock(T0, Number(p.arr), false)}</small>`;
      }
      tip.setLngLat(e.lngLat).setHTML(html).addTo(m);
    });
    m.getCanvas().addEventListener("mouseleave", () => tip.remove());

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

  // --- basemap ------------------------------------------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const sat = basemap === "satellite";
    m.setLayoutProperty("imagery", "visibility", sat ? "visible" : "none");
    m.setPaintProperty("hillshade", "hillshade-exaggeration", sat ? 0.3 : 0.6);
    m.setPaintProperty("hillshade", "hillshade-shadow-color", sat ? "#1b2430" : "#8a7a66");
    m.setPaintProperty("roads-base", "line-color", sat ? "#e5e9ef" : "#5b6472");
    m.setPaintProperty("roads-base", "line-opacity", sat ? 0.6 : 0.75);
    m.setPaintProperty("streams", "line-color", sat ? "#4cc9f0" : "#1d7fc4");
    m.setPaintProperty("subbasin-line", "line-color", sat ? "#ffffff" : "#6b5f50");
    m.setPaintProperty("catchment-line", "line-color", sat ? "#ffd166" : "#b5651d");
  }, [ready, basemap]);

  // --- villages as labelled status badges (HTML: no glyph server needed) ------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    markers.current.forEach((k) => k.remove());
    markers.current = [];
    const vimp = scenario?.impact.villages ?? {};
    for (const f of data.villages.features) {
      const name = f.properties.name;
      const v = vimp[name];
      if (!v && f.properties.place === "hamlet") continue;
      const { flooded, cut } = villageState(v, time);
      const pop = population[name] ?? 0;
      const el = document.createElement("button");
      el.className = `vmark ${pop > 600 ? "big" : pop > 150 ? "mid" : "small"}${flooded ? " hit" : ""}${cut ? " iso" : ""}${!flooded && !cut && scenario ? " safe" : ""}${selectedVillage === name ? " sel" : ""}`;
      const count = flooded && v ? `<span class="cnt">${v.buildings_affected} bldg</span>` : "";
      const cutTag = cut ? `<span class="cut">cut off</span>` : "";
      el.innerHTML = `<span class="dot"></span><span class="lbl">${name}</span>${count}${cutTag}`;
      el.title = `${f.properties.name_local || name}${pop ? ` · ~${Math.round(pop)} residents` : ""}`;
      el.onclick = (ev) => {
        ev.stopPropagation();
        set({ selectedVillage: name, mode: "impact", panelOpen: true });
      };
      markers.current.push(new maplibregl.Marker({ element: el, anchor: "left", offset: [-7, 0] }).setLngLat(f.geometry.coordinates as [number, number]).addTo(m));
    }
    for (const f of data.shelters.features) {
      const el = document.createElement("div");
      el.className = "smark";
      el.title = `Shelter: ${f.properties.name || f.properties.kind} (${f.properties.village}) — stays dry in the largest flood`;
      el.textContent = "⛺";
      markers.current.push(new maplibregl.Marker({ element: el }).setLngLat(f.geometry.coordinates as [number, number]).addTo(m));
    }
  }, [ready, scenario, time, selectedVillage, data, set, population]);

  // --- flood raster for scenario / layer / time ---------------------------------------------------
  useEffect(() => {
    const m = map.current, c = canvas.current;
    if (!m || !ready || !c) return;
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(c.width, c.height);
    if (scenario) paint(scenario.rasters, layer, time, data.meta.design_burst_h, img.data);
    ctx.putImageData(img, 0, 0);
    (m.getSource("flood") as ImageSource).updateImage({ url: c.toDataURL(), coordinates: data.meta.raster.corners_lonlat as Corners });
  }, [ready, scenario, layer, time, data]);

  // --- data-driven state: buildings, roads, fords ---------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const b = scenario?.impact.buildings;
    const withState = <T extends FeatureCollection>(fc: T) => ({
      ...fc,
      features: fc.features.map((f, i) => ({ ...f, properties: { ...f.properties, hr: b ? b.hr_class[i] : 0, arr: b ? b.arrival_h[i] : -1, str: b ? b.structural[i] : 0 } })),
    });
    (m.getSource("buildings") as GeoJSONSource).setData(withState(data.buildings) as FeatureCollection);
    const pts = m.getSource("building-pts") as GeoJSONSource;
    pts.getData().then((d) => pts.setData(withState(d as FeatureCollection) as FeatureCollection));
    const s = scenario?.impact.segments;
    const roadProps = (i: number) => ({ st: s ? s.status[i] : 0, cf: s ? s.car_from[i] : -1, ct: s ? s.car_to[i] : -1, xf: s ? s.closed_from[i] : -1, xt: s ? s.closed_to[i] : -1 });
    (m.getSource("roads") as GeoJSONSource).setData({ ...data.roads, features: data.roads.features.map((f, i) => ({ ...f, properties: { ...f.properties, ...roadProps(i) } })) } as FeatureCollection);
    (m.getSource("fords") as GeoJSONSource).setData({ ...fordPoints, features: fordPoints.features.map((f) => ({ ...f, properties: { ...f.properties, ...roadProps(f.properties!.seg) } })) } as FeatureCollection);
  }, [ready, scenario, data, fordPoints]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const T = time ?? 1e6;
    const hit: ExpressionSpecification = ["all", [">", ["get", "hr"], 0], ["<=", ["get", "arr"], T]];
    const color: ExpressionSpecification = ["case", hit, ["match", ["get", "hr"], 1, HC(1), 2, HC(2), 3, HC(3), HC(4)], "#9aa3ad"];
    m.setPaintProperty("buildings", "fill-color", color);
    m.setPaintProperty("buildings-outline", "line-opacity", ["case", hit, 1, 0.25]);
    m.setPaintProperty("building-pts", "circle-color", color);
    m.setPaintProperty("building-pts", "circle-radius", zwBy(["case", hit, 3.2, 1.2], ["case", hit, 7, 2.5]));
    m.setPaintProperty("building-pts", "circle-opacity", ["case", hit, 1, 0.45]);
    m.setPaintProperty("building-pts", "circle-stroke-width", ["case", hit, 1.2, 0]);
    m.setPaintProperty("building-pts", "circle-stroke-color", "#0b1220");
    const { closed, unsafe } = stateExpr(time);
    const alert: ExpressionSpecification = ["any", closed, unsafe];
    m.setFilter("roads-alert", alert);
    m.setFilter("roads-alert-casing", alert);
    m.setPaintProperty("roads-alert", "line-color", ["case", closed, RED, ORANGE]);
    m.setLayoutProperty("fords", "icon-image", ["case", closed, "ford-red", unsafe, "ford-orange", "ford-green"]);
    m.setLayoutProperty("fords", "icon-size", zwBy(["case", closed, 0.8, unsafe, 0.7, 0.4], ["case", closed, 1.3, unsafe, 1.15, 0.7]));
    m.setLayoutProperty("fords", "symbol-sort-key", ["case", closed, 2, unsafe, 1, 0]);
    m.setPaintProperty("fords", "icon-opacity", ["case", ["any", closed, unsafe], 1, 0.55]);
  }, [ready, scenario, time]);

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

  // --- probe (click to inspect) ---------------------------------------------------------------------
  useEffect(() => {
    if (!probe || !scenario) return;
    const px = locate(probe.lngLat[0], probe.lngLat[1]);
    const v = px ? query(scenario.rasters, px[0], px[1]) : null;
    setProbe((o) => (o ? { ...o, v } : o));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probe?.lngLat[0], probe?.lngLat[1], scenario]);

  const legend = LEGENDS[layer];
  const hz = (h: number) => ["—", "Low", "Moderate", "Significant", "Extreme"][h <= 0 ? 0 : h < 0.75 ? 1 : h < 1.25 ? 2 : h < 2 ? 3 : 4];
  return (
    <div className="map-wrap">
      <div ref={box} className="map" />
      {probe && (
        <div className="probe">
          <button className="x" onClick={() => setProbe(null)} aria-label="Close">×</button>
          {!scenario && <p>Choose a forecast, past event or design flood to inspect flood values.</p>}
          {probe.v && probe.v.depth > 0 ? (
            <dl>
              <dt>Deepest water</dt><dd>{probe.v.depth.toFixed(2)} m</dd>
              <dt>Fastest flow</dt><dd>{probe.v.velocity.toFixed(1)} m/s</dd>
              <dt>Danger</dt><dd>{hz(probe.v.hazard)}</dd>
              <dt>Water arrives</dt><dd>{probe.v.firstWater ? clock(t0, probe.v.firstWater) : "—"}</dd>
              <dt>Deeper than 30 cm for</dt><dd>{probe.v.duration03.toFixed(1)} h</dd>
            </dl>
          ) : scenario ? <p>No flooding here in this scenario.</p> : null}
        </div>
      )}
      <div className={`legend${legendOpen ? "" : " closed"}`}>
        <button className="legend-h" onClick={() => setLegendOpen(!legendOpen)}>Legend {legendOpen ? "▾" : "▸"}</button>
        {legendOpen && (
          <>
            <div className="lg"><strong>{legend.title}</strong>
              {legend.items.map(([c, l]) => <span key={l}><i className="sw" style={{ background: c }} />{l}</span>)}</div>
            <div className="lg"><strong>Roads</strong>
              <span><i className="ln" style={{ background: RED }} />Closed — too deep or fast even for a 4×4</span>
              <span><i className="ln" style={{ background: ORANGE }} />Unsafe for cars</span>
              <span><i className="ln thin" />Open</span>
              <span><i className="dm" style={{ background: RED }} /><i className="dm" style={{ background: ORANGE }} /><i className="dm" style={{ background: GREEN }} />Ford (wadi crossing)</span></div>
            <div className="lg"><strong>Villages</strong>
              <span><i className="vd hit" />Water reaches houses</span>
              <span><i className="vd iso" />Cut off by road</span>
              <span><i className="vd safe" />Not affected</span>
              <span>⛺ Shelter (stays dry)</span></div>
            <div className="lg"><strong>Other</strong>
              <span><i className="ln river" />River / wadi</span>
              <span><i className="ln basin" />Catchment boundary</span></div>
          </>
        )}
      </div>
    </div>
  );
}
