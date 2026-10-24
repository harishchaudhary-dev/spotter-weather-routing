import type { LngLat, RouteOption } from "../api/types";

export type TruckPosition =
  | { state: "waiting"; at: LngLat }
  | { state: "driving"; at: LngLat; progress: number }
  | { state: "arrived"; at: LngLat };

/** Where the truck is `elapsedS` seconds after departure, using the route's per-vertex time profile. */
export function positionAt(route: Pick<RouteOption, "geometry" | "timeline_s">, elapsedS: number): TruckPosition {
  const coords = route.geometry.coordinates;
  const times = route.timeline_s;
  const total = times[times.length - 1];
  if (elapsedS < 0) return { state: "waiting", at: coords[0] };
  if (elapsedS >= total) return { state: "arrived", at: coords[coords.length - 1] };

  // Binary search for the segment containing elapsedS.
  let lo = 0;
  let hi = times.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= elapsedS) lo = mid;
    else hi = mid;
  }
  const span = times[hi] - times[lo];
  const t = span === 0 ? 0 : (elapsedS - times[lo]) / span;
  const [x0, y0] = coords[lo];
  const [x1, y1] = coords[hi];
  return { state: "driving", at: [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t], progress: elapsedS / total };
}
