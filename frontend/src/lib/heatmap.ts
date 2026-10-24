import type { FeatureCollection, Point } from "geojson";
import type { ExpressionSpecification } from "maplibre-gl";
import type { HeatmapData } from "../api/types";
import { LEVELS } from "./risk";

export type HeatMetric = "risk" | "wind" | "rain" | "snow";

export interface MetricMeta {
  id: HeatMetric;
  label: string;
  unit: string;
  /** Lower bounds of Moderate, High, Severe, No Travel — straight from the risk table. */
  thresholds: [number, number, number, number];
}

export const METRICS: readonly MetricMeta[] = [
  { id: "risk", label: "Risk", unit: "", thresholds: [1, 2, 3, 4] },
  { id: "wind", label: "Wind", unit: "mph", thresholds: [25, 35, 45, 55] },
  { id: "rain", label: "Rain", unit: "in/hr", thresholds: [0.1, 0.25, 0.5, 1.0] },
  { id: "snow", label: "Snow", unit: "in/hr", thresholds: [0.5, 1.0, 2.0, 3.0] },
];

const PREFIX: Record<HeatMetric, string> = { risk: "r", wind: "w", rain: "p", snow: "s" };

/** Feature property holding the 0–1 weight of `metric` at forecast hour `hour`. */
export const weightKey = (metric: HeatMetric, hour: number) => `${PREFIX[metric]}${hour}`;

/**
 * Map a raw value onto a shared 0–1 "risk scale" where each table threshold lands on the same
 * colour stop (Moderate 0.25, High 0.5, Severe 0.75, No Travel 1). Orange therefore means "High"
 * whether you're looking at wind, rain or snow.
 */
export function toRiskScale(value: number, thresholds: readonly number[]): number {
  const stops = [0, ...thresholds];
  if (value <= 0) return 0;
  for (let i = 1; i < stops.length; i++) {
    if (value < stops[i]) return ((i - 1) + (value - stops[i - 1]) / (stops[i] - stops[i - 1])) / 4;
  }
  return 1;
}

/** Calm points still get a faint weight so the corridor coverage is visible. */
const COVERAGE_FLOOR = 0.06;

/**
 * Build the heatmap GeoJSON ONCE with every hour × metric pre-normalised into feature properties.
 * Scrubbing the slider then only swaps the layer's `heatmap-weight` expression to a different
 * property — no data upload, no re-tiling, so it stays at 60 fps.
 */
export function buildHeatmapGeoJSON(data: HeatmapData): FeatureCollection<Point> {
  const series: Record<HeatMetric, number[][]> = {
    risk: data.risk,
    wind: data.wind_mph,
    rain: data.rain_in_hr,
    snow: data.snow_in_hr,
  };
  return {
    type: "FeatureCollection",
    features: data.points.map((coordinates, i) => {
      const properties: Record<string, number> = {};
      for (const m of METRICS) {
        const rows = series[m.id];
        for (let h = 0; h < rows.length; h++) {
          const w = toRiskScale(rows[h][i], m.thresholds);
          properties[weightKey(m.id, h)] = Math.max(COVERAGE_FLOOR, Math.round(w * 1000) / 1000);
        }
      }
      return { type: "Feature", geometry: { type: "Point", coordinates }, properties };
    }),
  };
}

const rgba = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
};

/** Density → colour ramp whose stops coincide with the risk-scale thresholds above. */
export const heatColorExpression = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0,
  "rgba(0,0,0,0)",
  0.04,
  rgba(LEVELS[0].color, 0.12),
  0.12,
  rgba(LEVELS[0].color, 0.32),
  0.25,
  rgba(LEVELS[1].color, 0.6),
  0.5,
  rgba(LEVELS[2].color, 0.72),
  0.75,
  rgba(LEVELS[3].color, 0.8),
  1,
  rgba(LEVELS[4].color, 0.85),
] as unknown as ExpressionSpecification;

/** Heat kernel radius (px) so neighbouring grid points blend into a continuous surface at any zoom. */
export function radiusExpression(stepDeg: number, latitude: number): ExpressionSpecification {
  const metersPerPixelAtZ0 = (40075016.686 * Math.cos((latitude * Math.PI) / 180)) / 512;
  const stepMeters = stepDeg * 111_320;
  const r0 = (stepMeters / metersPerPixelAtZ0) * 1.15;
  return ["interpolate", ["exponential", 2], ["zoom"], 0, r0, 12, r0 * 2 ** 12];
}
