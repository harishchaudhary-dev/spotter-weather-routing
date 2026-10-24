import { useState } from "react";
import type { Place, PlanRequest, SampleInterval } from "../api/types";
import { toLocalInputValue } from "../lib/format";
import { PlaceInput } from "./PlaceInput";

const INTERVALS: SampleInterval[] = [10, 25, 50];
const LOAD_PRESETS = [15_000, 35_000, 45_000];

interface Props {
  loading: boolean;
  onSubmit: (req: PlanRequest) => void;
}

function defaultDeparture(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  return toLocalInputValue(d);
}

export function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | string>("Denver, CO");
  const [destination, setDestination] = useState<Place | string>("Chicago, IL");
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState(35_000);
  const [interval, setInterval] = useState<SampleInterval>(25);
  const [submitted, setSubmitted] = useState(false);

  const now = new Date();
  const maxDeparture = new Date(now.getTime() + 7 * 24 * 3600 * 1000);

  const build = (overrides: Partial<PlanRequest> = {}): PlanRequest => ({
    origin,
    destination,
    departure: new Date(departure).toISOString(),
    load_weight_lbs: load,
    interval_miles: interval,
    ...overrides,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    onSubmit(build());
  };

  const swap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  return (
    <form className="trip-form" onSubmit={submit}>
      <div className="od">
        <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City, state or address" />
        <button type="button" className="swap" onClick={swap} aria-label="Swap origin and destination" title="Swap">
          ⇅
        </button>
        <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="City, state or address" />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={toLocalInputValue(new Date(now.getTime() - 30 * 60 * 1000))}
            max={toLocalInputValue(maxDeparture)}
            onChange={(e) => setDeparture(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input
            id="load"
            type="number"
            min={0}
            max={100_000}
            step={500}
            value={load}
            onChange={(e) => setLoad(Number(e.target.value))}
            required
          />
        </div>
      </div>

      <div className="presets" role="group" aria-label="Load presets">
        {LOAD_PRESETS.map((p) => (
          <button type="button" key={p} className={p === load ? "chip on" : "chip"} onClick={() => setLoad(p)}>
            {p / 1000}k lb
          </button>
        ))}
        <span className="hint">Load rules kick in above 30k / 40k lb</span>
      </div>

      <div className="field">
        <span className="label" id="interval-label">
          Weather checkpoint every
        </span>
        <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((v) => (
            <button
              type="button"
              role="radio"
              aria-checked={v === interval}
              key={v}
              className={v === interval ? "on" : undefined}
              onClick={() => {
                setInterval(v);
                // Re-sample immediately once a plan exists (routes + weather are cached server-side).
                if (submitted && !loading) onSubmit(build({ interval_miles: v }));
              }}
            >
              {v} mi
            </button>
          ))}
        </div>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? "Analyzing routes…" : "Find safest route"}
      </button>
    </form>
  );
}
