import type { ApiErrorBody, HeatmapData, LngLat, Place, PlanRequest, TripPlan } from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit & { signal?: AbortSignal } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0, "network");
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(body?.error.message ?? `Request failed (${res.status}).`, res.status, body?.error.code ?? "http");
  }
  return res.json() as Promise<T>;
}

export function searchPlaces(q: string, signal?: AbortSignal): Promise<Place[]> {
  return request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }).then((r) => r.results);
}

export function planTrip(body: PlanRequest, signal?: AbortSignal): Promise<TripPlan> {
  return request<TripPlan>("/api/plan", { method: "POST", body: JSON.stringify(body), signal });
}

export function fetchHeatmap(
  body: { corridor: LngLat[][]; departure: string; load_weight_lbs: number; hours?: number },
  signal?: AbortSignal,
): Promise<HeatmapData> {
  return request<HeatmapData>("/api/heatmap", { method: "POST", body: JSON.stringify(body), signal });
}
