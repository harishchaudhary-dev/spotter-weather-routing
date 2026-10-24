/** Mirrors the Django API contract (backend/routing/api/presenters.py). */

export type RiskLevel = 0 | 1 | 2 | 3 | 4;
export type LngLat = [number, number];

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface CheckpointWeather {
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  temperature_f: number | null;
  weather_code: number | null;
}

export interface RiskAssessment {
  level: RiskLevel;
  label: string;
  by_condition: { wind: RiskLevel; rain: RiskLevel; snow: RiskLevel };
  load_rule_applied: boolean;
  drivers: Array<"wind" | "rain" | "snow">;
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  covers_mi: [number, number];
  weather: CheckpointWeather;
  risk: RiskAssessment;
}

export interface MilesByLevel {
  low: number;
  moderate: number;
  high: number;
  severe: number;
  no_travel: number;
}

export interface RouteSummary {
  distance_mi: number;
  duration_s: number;
  arrival: string;
  miles_by_level: MilesByLevel;
  avg_risk: number;
  max_level: RiskLevel;
  checkpoint_count: number;
}

export interface RiskSegment {
  level: RiskLevel;
  from_mi: number;
  to_mi: number;
  coordinates: LngLat[];
}

export interface RouteOption {
  id: string;
  name: string;
  via: string;
  rank: number;
  recommended: boolean;
  summary: RouteSummary;
  geometry: { type: "LineString"; coordinates: LngLat[] };
  timeline_s: number[];
  segments: RiskSegment[];
  checkpoints: Checkpoint[];
  label_point: LngLat;
}

export type DecidingCriterion = "no_travel_mi" | "severe_mi" | "high_mi" | "avg_risk" | "duration";

export interface TripPlan {
  origin: Place;
  destination: Place;
  departure: string;
  load_weight_lbs: number;
  interval_miles: SampleInterval;
  recommendation: {
    route_id: string;
    ranking: string[];
    decided_by: DecidingCriterion | null;
    reason: string;
    advisories: string[];
  };
  routes: RouteOption[];
}

export interface HeatmapData {
  start: string;
  hours: number;
  step_deg: number;
  points: LngLat[];
  /** [hour][point] */
  risk: RiskLevel[][];
  wind_mph: number[][];
  rain_in_hr: number[][];
  snow_in_hr: number[][];
}

export type SampleInterval = 10 | 25 | 50;

export interface PlanRequest {
  origin: Place | string;
  destination: Place | string;
  departure: string;
  load_weight_lbs: number;
  interval_miles: SampleInterval;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
