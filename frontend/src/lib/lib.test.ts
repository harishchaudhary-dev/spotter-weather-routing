import { describe, expect, it } from "vitest";
import type { HeatmapData, LngLat } from "../api/types";
import { buildHeatmapGeoJSON, toRiskScale, weightKey } from "./heatmap";
import { positionAt } from "./timeline";

describe("toRiskScale", () => {
  const wind = [25, 35, 45, 55];
  it("places each table threshold on the shared colour stop", () => {
    expect(toRiskScale(0, wind)).toBe(0);
    expect(toRiskScale(25, wind)).toBe(0.25);
    expect(toRiskScale(35, wind)).toBe(0.5);
    expect(toRiskScale(45, wind)).toBe(0.75);
    expect(toRiskScale(55, wind)).toBe(1);
    expect(toRiskScale(90, wind)).toBe(1);
  });
  it("interpolates within a band", () => {
    expect(toRiskScale(30, wind)).toBeCloseTo(0.375);
  });
});

describe("buildHeatmapGeoJSON", () => {
  it("stores one normalised weight per metric and hour", () => {
    const data: HeatmapData = {
      start: "2026-01-01T00:00:00Z",
      hours: 1,
      step_deg: 0.3,
      points: [[-100, 40]],
      risk: [[0], [3]],
      wind_mph: [[10], [50]],
      rain_in_hr: [[0], [0.25]],
      snow_in_hr: [[0], [3.5]],
    };
    const props = buildHeatmapGeoJSON(data).features[0].properties!;
    expect(props[weightKey("risk", 1)]).toBe(0.75);
    expect(props[weightKey("rain", 1)]).toBe(0.5);
    expect(props[weightKey("snow", 1)]).toBe(1);
    expect(props[weightKey("risk", 0)]).toBeGreaterThan(0); // calm still shows coverage
  });
});

describe("positionAt", () => {
  const route = {
    geometry: { type: "LineString" as const, coordinates: [[0, 0], [10, 0], [10, 10]] as LngLat[] },
    timeline_s: [0, 100, 300],
  };
  it("is waiting before departure and arrived after the last vertex", () => {
    expect(positionAt(route, -5).state).toBe("waiting");
    expect(positionAt(route, 301)).toEqual({ state: "arrived", at: [10, 10] });
  });
  it("interpolates by time, not by distance", () => {
    const p = positionAt(route, 200);
    expect(p.state).toBe("driving");
    expect(p.at[0]).toBeCloseTo(10);
    expect(p.at[1]).toBeCloseTo(5);
  });
});
