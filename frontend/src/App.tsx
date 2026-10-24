import { useCallback, useEffect, useMemo, useState } from "react";
import type { Checkpoint } from "./api/types";
import { CheckpointTable } from "./components/CheckpointTable";
import { ForecastControl } from "./components/ForecastControl";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import { RouteCards } from "./components/RouteCards";
import { TripForm } from "./components/TripForm";
import { latest, useTripPlanner } from "./hooks/useTripPlanner";
import { fmtLbs } from "./lib/format";
import type { HeatMetric } from "./lib/heatmap";
import { positionAt } from "./lib/timeline";

const FORECAST_HOURS = 48;

export default function App() {
  const { plan: planState, heatmap: heatState, run } = useTripPlanner();
  const plan = latest(planState);
  const heatmap = heatState.status === "success" ? heatState.data : undefined;

  const [selectedId, setSelectedId] = useState<string>();
  const [hour, setHour] = useState(0);
  const [metric, setMetric] = useState<HeatMetric>("risk");
  const [heatVisible, setHeatVisible] = useState(true);
  const [focus, setFocus] = useState<{ checkpoint: Checkpoint; nonce: number } | null>(null);

  // New plan → select the recommended route (unless the current selection still exists) and rewind.
  useEffect(() => {
    if (!plan) return;
    setSelectedId((cur) => (cur && plan.routes.some((r) => r.id === cur) ? cur : plan.recommendation.route_id));
    setHour(0);
  }, [plan]);

  const selected = plan?.routes.find((r) => r.id === selectedId);

  // Slider position h means "departure + h hours". The heatmap's forecast hours are whole UTC hours,
  // so pick the nearest one (matters in half-hour time zones such as IST).
  const departure = useMemo(() => (plan ? new Date(plan.departure) : new Date()), [plan]);
  const heatHour = useMemo(() => {
    if (!heatmap) return hour;
    const offsetH = (departure.getTime() - new Date(heatmap.start).getTime()) / 3600_000;
    return Math.min(heatmap.hours, Math.max(0, Math.round(hour + offsetH)));
  }, [heatmap, departure, hour]);

  const truck = useMemo(() => (selected ? positionAt(selected, hour * 3600) : undefined), [selected, hour]);

  const truckNote = useMemo(() => {
    if (!truck || !selected) return undefined;
    if (truck.state === "waiting") return `${selected.name}: not departed yet`;
    if (truck.state === "arrived") return `${selected.name}: arrived`;
    return `${selected.name}: ${Math.round(truck.progress * selected.summary.distance_mi)} of ${Math.round(selected.summary.distance_mi)} mi`;
  }, [truck, selected]);

  const onFocus = useCallback((checkpoint: Checkpoint) => setFocus({ checkpoint, nonce: Date.now() }), []);
  const loading = planState.status === "loading";

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <div className="logo" aria-hidden="true">
            ◆
          </div>
          <div>
            <h1>Stormline</h1>
            <p>Weather-aware truck routing</p>
          </div>
        </header>

        <TripForm loading={loading} onSubmit={run} />

        {planState.status === "error" && (
          <div className="banner error" role="alert">
            {planState.message}
          </div>
        )}

        {plan && selectedId && (
          <>
            <div className="trip-meta">
              {plan.routes.length} routes · checkpoints every {plan.interval_miles} mi · {fmtLbs(plan.load_weight_lbs)}
              {plan.routes.length < 3 && <span className="muted"> · only {plan.routes.length} distinct route(s) exist</span>}
            </div>
            <RouteCards plan={plan} selectedId={selectedId} onSelect={setSelectedId} />
            {selected && <CheckpointTable route={selected} onFocus={onFocus} />}
          </>
        )}

        {!plan && !loading && (
          <div className="empty">
            <p>
              Enter a trip to compare three routes. Weather is sampled along each route at the truck's estimated arrival
              time, scored against wind / rain / snow thresholds and your load weight, and the safest route is recommended.
            </p>
          </div>
        )}
      </aside>

      <main className="map-pane">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          heatmap={heatmap}
          heatVisible={heatVisible}
          metric={metric}
          hour={heatHour}
          truck={truck}
          focus={focus}
        />
        {loading && (
          <div className="map-loading" role="status">
            <span className="spinner" /> Fetching routes and forecasts…
          </div>
        )}
        <Legend metric={metric} />
        {plan && (
          <ForecastControl
            start={departure}
            maxHour={FORECAST_HOURS}
            hour={hour}
            onHour={setHour}
            metric={metric}
            onMetric={setMetric}
            visible={heatVisible}
            onVisible={setHeatVisible}
            status={heatState.status}
            error={heatState.status === "error" ? heatState.message : undefined}
            truckNote={truckNote}
          />
        )}
      </main>
    </div>
  );
}
