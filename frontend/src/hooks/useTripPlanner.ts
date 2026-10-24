import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchHeatmap, planTrip } from "../api/client";
import type { HeatmapData, LngLat, PlanRequest, TripPlan } from "../api/types";

type Async<T> =
  | { status: "idle" }
  | { status: "loading"; previous?: T }
  | { status: "success"; data: T }
  | { status: "error"; message: string; previous?: T };

const MAX_CORRIDOR_POINTS = 3000;

/**
 * Plans a trip, then loads the corridor heatmap in the background so routes appear as soon as
 * they're ready. Superseded requests are aborted, so a slow old response can never overwrite a
 * newer one.
 */
export function useTripPlanner() {
  const [plan, setPlan] = useState<Async<TripPlan>>({ status: "idle" });
  const [heatmap, setHeatmap] = useState<Async<HeatmapData>>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (req: PlanRequest) => {
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;

    setPlan((s) => ({ status: "loading", previous: latest(s) }));
    setHeatmap({ status: "idle" });

    let result: TripPlan;
    try {
      result = await planTrip(req, ctrl.signal);
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setPlan((s) => ({ status: "error", message: messageOf(err), previous: latest(s) }));
      return;
    }
    setPlan({ status: "success", data: result });

    setHeatmap({ status: "loading" });
    try {
      const data = await fetchHeatmap(
        { corridor: corridorOf(result), departure: result.departure, load_weight_lbs: result.load_weight_lbs },
        ctrl.signal,
      );
      setHeatmap({ status: "success", data });
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setHeatmap({ status: "error", message: messageOf(err) });
    }
  }, []);

  useEffect(() => () => controller.current?.abort(), []);

  return { plan, heatmap, run };
}

/** Most recent successful data, kept visible while a new request is loading or after it fails. */
export function latest<T>(s: Async<T>): T | undefined {
  if (s.status === "success") return s.data;
  if (s.status === "loading" || s.status === "error") return s.previous;
  return undefined;
}

function messageOf(err: unknown): string {
  return err instanceof ApiError ? err.message : "Unexpected error. Please try again.";
}

/** One line per route (never joined, so no bogus segment bridges routes), thinned to stay small. */
function corridorOf(plan: TripPlan): LngLat[][] {
  const total = plan.routes.reduce((n, r) => n + r.geometry.coordinates.length, 0);
  const stride = Math.max(1, Math.ceil(total / MAX_CORRIDOR_POINTS));
  return plan.routes.map(({ geometry: { coordinates: c } }) =>
    c.filter((_, i) => i % stride === 0 || i === c.length - 1),
  );
}
