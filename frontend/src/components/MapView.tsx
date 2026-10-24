import type { Feature, FeatureCollection, LineString, Point } from "geojson";
import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import type { Checkpoint, HeatmapData, LngLat, RouteOption, TripPlan } from "../api/types";
import { describeWeatherCode, escapeHtml, fmtDateTime } from "../lib/format";
import { buildHeatmapGeoJSON, heatColorExpression, radiusExpression, weightKey, type HeatMetric } from "../lib/heatmap";
import { levelColorExpression, levelMeta, routeColor } from "../lib/risk";
import type { TruckPosition } from "../lib/timeline";

const BASEMAP = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

interface Props {
  plan?: TripPlan;
  selectedId?: string;
  onSelect: (id: string) => void;
  heatmap?: HeatmapData;
  heatVisible: boolean;
  metric: HeatMetric;
  hour: number;
  truck?: TruckPosition;
  focus?: { checkpoint: Checkpoint; nonce: number } | null;
}

/**
 * MapLibre (WebGL) map managed imperatively: React effects push data into long-lived sources and
 * flip paint properties, so neither selecting a route nor scrubbing the forecast re-creates layers.
 */
export function MapView({ plan, selectedId, onSelect, heatmap, heatVisible, metric, hour, truck, focus }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const lookup = useRef(new Map<string, { route: RouteOption; cp: Checkpoint }>());
  const hoverPopup = useRef<maplibregl.Popup | null>(null);
  const labelMarkers = useRef<maplibregl.Marker[]>([]);
  const endpointMarkers = useRef<maplibregl.Marker[]>([]);
  const truckMarker = useRef<maplibregl.Marker | null>(null);
  const fittedFor = useRef<string>("");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // ---- one-time map setup -------------------------------------------------------------------
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: BASEMAP,
      center: [-96, 39],
      zoom: 3.4,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-right");
    mapRef.current = map;

    map.on("load", () => {
      addLayers(map);
      wireInteractions(map);
      setReady(true);
    });

    function wireInteractions(m: MlMap) {
      hoverPopup.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: "280px" });

      m.on("mouseenter", "checkpoints", (e) => {
        m.getCanvas().style.cursor = "pointer";
        const key = e.features?.[0]?.properties?.key as string | undefined;
        const hit = key ? lookup.current.get(key) : undefined;
        if (hit) hoverPopup.current!.setLngLat([hit.cp.lon, hit.cp.lat]).setHTML(popupHtml(hit.route, hit.cp)).addTo(m);
      });
      m.on("mouseleave", "checkpoints", () => {
        m.getCanvas().style.cursor = "";
        hoverPopup.current?.remove();
      });
      m.on("click", "checkpoints", (e) => {
        const id = e.features?.[0]?.properties?.routeId as string | undefined;
        if (id) onSelectRef.current(id);
      });
      m.on("mouseenter", "routes-hit", () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", "routes-hit", () => (m.getCanvas().style.cursor = ""));
      m.on("click", "routes-hit", (e) => {
        if (m.queryRenderedFeatures(e.point, { layers: ["checkpoints"] }).length) return;
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (id) onSelectRef.current(id);
      });
    }

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- routes, checkpoints, labels ----------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;

    lookup.current.clear();
    plan?.routes.forEach((r) => r.checkpoints.forEach((cp) => lookup.current.set(`${r.id}:${cp.index}`, { route: r, cp })));

    const routes = plan?.routes ?? [];
    // Draw the selected route last so it sits on top.
    const ordered = [...routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId));
    setData(map, "routes", {
      type: "FeatureCollection",
      features: ordered.map(
        (r): Feature<LineString> => ({
          type: "Feature",
          geometry: r.geometry,
          properties: { id: r.id, color: routeColor(r.id), selected: r.id === selectedId ? 1 : 0 },
        }),
      ),
    });

    const selected = routes.find((r) => r.id === selectedId);
    setData(map, "risk", {
      type: "FeatureCollection",
      features: (selected?.segments ?? []).map(
        (s): Feature<LineString> => ({
          type: "Feature",
          geometry: { type: "LineString", coordinates: s.coordinates },
          properties: { level: s.level },
        }),
      ),
    });

    setData(map, "checkpoints", {
      type: "FeatureCollection",
      features: routes.flatMap((r) =>
        r.checkpoints.map(
          (cp): Feature<Point> => ({
            type: "Feature",
            geometry: { type: "Point", coordinates: [cp.lon, cp.lat] },
            properties: { key: `${r.id}:${cp.index}`, routeId: r.id, level: cp.risk.level, selected: r.id === selectedId ? 1 : 0 },
          }),
        ),
      ),
    });

    labelMarkers.current.forEach((m) => m.remove());
    labelMarkers.current = routes.map((r) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `route-label${r.id === selectedId ? " selected" : ""}`;
      el.style.setProperty("--route", routeColor(r.id));
      const severe = r.summary.miles_by_level.severe + r.summary.miles_by_level.no_travel;
      el.innerHTML = `<b>${escapeHtml(r.name)}</b> ${formatHours(r.summary.duration_s)} · ${Math.round(
        r.summary.distance_mi,
      ).toLocaleString()} mi${
        severe > 0 ? ` · <span class="warn">${Math.round(severe)} mi severe+</span>` : ""
      }${r.recommended ? ' <span class="star" title="Recommended">★</span>' : ""}`;
      el.addEventListener("click", () => onSelectRef.current(r.id));
      return new maplibregl.Marker({ element: el }).setLngLat(r.label_point).addTo(map);
    });
  }, [ready, plan, selectedId]);

  // ---- endpoints + fit bounds (only when the trip itself changes) ---------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !plan) return;
    endpointMarkers.current.forEach((m) => m.remove());
    endpointMarkers.current = [
      endpoint(plan.origin.lon, plan.origin.lat, "A", plan.origin.label).addTo(map),
      endpoint(plan.destination.lon, plan.destination.lat, "B", plan.destination.label).addTo(map),
    ];

    const tripKey = `${plan.origin.lat},${plan.origin.lon}->${plan.destination.lat},${plan.destination.lon}`;
    if (fittedFor.current === tripKey) return;
    fittedFor.current = tripKey;
    const bounds = new maplibregl.LngLatBounds();
    plan.routes.forEach((r) => r.geometry.coordinates.forEach((c) => bounds.extend(c as LngLat)));
    map.fitBounds(bounds, { padding: { top: 60, bottom: 150, left: 60, right: 60 }, duration: 900 });
  }, [ready, plan]);

  // ---- heatmap data (once per response) -----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setData(map, "heat", heatmap ? buildHeatmapGeoJSON(heatmap) : EMPTY);
    if (heatmap?.points.length) {
      const midLat = heatmap.points.reduce((s, p) => s + p[1], 0) / heatmap.points.length;
      map.setPaintProperty("heat", "heatmap-radius", radiusExpression(heatmap.step_deg, midLat));
    }
  }, [ready, heatmap]);

  // ---- heatmap hour / metric (per slider tick: a single paint-property swap) -----------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setPaintProperty("heat", "heatmap-weight", ["coalesce", ["get", weightKey(metric, hour)], 0]);
    map.setLayoutProperty("heat", "visibility", heatVisible ? "visible" : "none");
  }, [ready, metric, hour, heatVisible]);

  // ---- truck position ------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!truck) {
      truckMarker.current?.remove();
      truckMarker.current = null;
      return;
    }
    if (!truckMarker.current) {
      const el = document.createElement("div");
      el.className = "truck";
      el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h11v9H3zM14 9h4l3 3v3h-7z" fill="currentColor"/><circle cx="7" cy="17" r="2" fill="#fff" stroke="currentColor" stroke-width="1.5"/><circle cx="17" cy="17" r="2" fill="#fff" stroke="currentColor" stroke-width="1.5"/></svg>`;
      truckMarker.current = new maplibregl.Marker({ element: el }).setLngLat(truck.at).addTo(map);
    }
    truckMarker.current.setLngLat(truck.at);
    truckMarker.current.getElement().dataset.state = truck.state;
  }, [ready, truck]);

  // ---- fly to a checkpoint picked from the table ----------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !focus) return;
    const hit = [...lookup.current.values()].find((v) => v.cp === focus.checkpoint);
    map.flyTo({ center: [focus.checkpoint.lon, focus.checkpoint.lat], zoom: Math.max(map.getZoom(), 8), duration: 700 });
    if (hit) hoverPopup.current?.setLngLat([hit.cp.lon, hit.cp.lat]).setHTML(popupHtml(hit.route, hit.cp)).addTo(map);
  }, [ready, focus]);

  return <div ref={container} className="map" role="region" aria-label="Route map" />;
}

// ----------------------------------------------------------------------------------- helpers

function addLayers(map: MlMap) {
  // Put weather and routes beneath the basemap's place labels so city names stay readable.
  const firstSymbol = map.getStyle().layers?.find((l) => l.type === "symbol")?.id;

  for (const id of ["heat", "routes", "risk", "checkpoints"]) {
    map.addSource(id, { type: "geojson", data: EMPTY });
  }

  map.addLayer(
    {
      id: "heat",
      type: "heatmap",
      source: "heat",
      maxzoom: 11,
      paint: {
        "heatmap-weight": 0,
        "heatmap-intensity": 1,
        "heatmap-color": heatColorExpression,
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.85, 11, 0.3],
      },
    },
    firstSymbol,
  );

  map.addLayer(
    {
      id: "routes-casing",
      type: "line",
      source: "routes",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#fff", "line-width": ["case", ["==", ["get", "selected"], 1], 13, 7], "line-opacity": 0.9 },
    },
  );
  map.addLayer({
    id: "routes-line",
    type: "line",
    source: "routes",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": ["get", "color"],
      "line-width": ["case", ["==", ["get", "selected"], 1], 10, 4],
      "line-opacity": ["case", ["==", ["get", "selected"], 1], 1, 0.6],
    },
  });
  map.addLayer({
    id: "risk-line",
    type: "line",
    source: "risk",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": levelColorExpression, "line-width": 4.5 },
  });
  map.addLayer({
    id: "routes-hit",
    type: "line",
    source: "routes",
    paint: { "line-color": "#000", "line-width": 18, "line-opacity": 0 },
  });
  map.addLayer({
    id: "checkpoints",
    type: "circle",
    source: "checkpoints",
    layout: { "circle-sort-key": ["get", "selected"] },
    paint: {
      "circle-color": levelColorExpression,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, ["case", ["==", ["get", "selected"], 1], 4.5, 2.5], 10, ["case", ["==", ["get", "selected"], 1], 8, 5]],
      "circle-stroke-color": "#fff",
      "circle-stroke-width": ["case", ["==", ["get", "selected"], 1], 2, 1],
      "circle-opacity": ["case", ["==", ["get", "selected"], 1], 1, 0.75],
    },
  });
}

function setData(map: MlMap, source: string, data: FeatureCollection) {
  (map.getSource(source) as GeoJSONSource | undefined)?.setData(data);
}

function endpoint(lon: number, lat: number, letter: string, label: string) {
  const el = document.createElement("div");
  el.className = `endpoint endpoint-${letter.toLowerCase()}`;
  el.textContent = letter;
  el.title = label;
  return new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([lon, lat]);
}

function formatHours(seconds: number) {
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

function popupHtml(route: RouteOption, cp: Checkpoint): string {
  const meta = levelMeta(cp.risk.level);
  const w = cp.weather;
  const drivers = cp.risk.drivers.length ? `Driven by ${cp.risk.drivers.join(" & ")}` : "No hazards";
  const desc = describeWeatherCode(w.weather_code);
  return `
    <div class="popup">
      <div class="popup-head"><b>${escapeHtml(route.name)}</b> · mile ${Math.round(cp.mile)}</div>
      <div class="popup-eta">ETA ${escapeHtml(fmtDateTime(cp.eta))}</div>
      <span class="pill" style="background:${meta.color}">${meta.label}</span>
      <span class="popup-drivers">${escapeHtml(drivers)}${cp.risk.load_rule_applied ? " · load rule applied" : ""}</span>
      <table>
        <tr><td>Wind</td><td>${w.wind_mph.toFixed(0)} mph <small>(gust ${w.gust_mph.toFixed(0)})</small></td></tr>
        <tr><td>Rain</td><td>${w.rain_in_hr.toFixed(2)} in/hr</td></tr>
        <tr><td>Snow</td><td>${w.snow_in_hr.toFixed(2)} in/hr</td></tr>
        ${w.temperature_f !== null ? `<tr><td>Temp</td><td>${w.temperature_f}°F ${escapeHtml(desc)}</td></tr>` : ""}
      </table>
    </div>`;
}
