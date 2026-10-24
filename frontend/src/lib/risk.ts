import type { ExpressionSpecification } from "maplibre-gl";
import type { MilesByLevel, RiskLevel } from "../api/types";

export interface LevelMeta {
  level: RiskLevel;
  key: keyof MilesByLevel;
  label: string;
  color: string;
}

/** Single source of truth for risk colours, shared by the map, heatmap and sidebar. */
export const LEVELS: readonly LevelMeta[] = [
  { level: 0, key: "low", label: "Low", color: "#2fbf71" },
  { level: 1, key: "moderate", label: "Moderate", color: "#f2c230" },
  { level: 2, key: "high", label: "High", color: "#f28c28" },
  { level: 3, key: "severe", label: "Severe", color: "#e03131" },
  { level: 4, key: "no_travel", label: "No Travel", color: "#7b2cbf" },
];

export const levelMeta = (level: RiskLevel): LevelMeta => LEVELS[level];

/** MapLibre `match` expression mapping a numeric `level` property to its colour. */
export const levelColorExpression = [
  "match",
  ["get", "level"],
  ...LEVELS.flatMap((l) => [l.level, l.color]),
  "#888",
] as unknown as ExpressionSpecification;

export const ROUTE_COLORS: Record<string, string> = {
  "route-a": "#1c7ed6",
  "route-b": "#0ca678",
  "route-c": "#ae3ec9",
};

export const routeColor = (id: string) => ROUTE_COLORS[id] ?? "#495057";
