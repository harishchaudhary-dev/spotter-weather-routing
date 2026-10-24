import { useEffect, useState } from "react";
import { fmtDateTime } from "../lib/format";
import { METRICS, type HeatMetric } from "../lib/heatmap";

interface Props {
  start: Date;
  maxHour: number;
  hour: number;
  onHour: (h: number) => void;
  metric: HeatMetric;
  onMetric: (m: HeatMetric) => void;
  visible: boolean;
  onVisible: (v: boolean) => void;
  status: "idle" | "loading" | "success" | "error";
  error?: string;
  truckNote?: string;
}

const PLAY_STEP_MS = 400;

export function ForecastControl(props: Props) {
  const { start, maxHour, hour, onHour, metric, onMetric, visible, onVisible, status, error, truckNote } = props;
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      onHour(hour >= maxHour ? 0 : hour + 1);
    }, PLAY_STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, hour, maxHour, onHour]);

  const at = new Date(start.getTime() + hour * 3600_000);

  return (
    <div className="forecast" aria-label="Weather forecast timeline">
      <div className="forecast-top">
        <button
          type="button"
          className="play"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}
          disabled={status !== "success"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="forecast-time">
          <b>+{hour}h</b> <span>{fmtDateTime(at)}</span>
        </div>
        <div className="segmented small" role="radiogroup" aria-label="Heatmap layer">
          {METRICS.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={metric === m.id}
              className={metric === m.id ? "on" : undefined}
              onClick={() => onMetric(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} /> Heatmap
        </label>
      </div>
      <input
        className="slider"
        type="range"
        min={0}
        max={maxHour}
        step={1}
        value={hour}
        onChange={(e) => onHour(Number(e.target.value))}
        aria-label="Hours after departure"
        aria-valuetext={`${hour} hours after departure, ${fmtDateTime(at)}`}
      />
      <div className="forecast-ticks" aria-hidden="true">
        {[0, 12, 24, 36, 48].map((t) => (
          <span key={t}>{t}h</span>
        ))}
      </div>
      <div className="forecast-status">
        {status === "loading" && <span className="spinner" aria-live="polite">Loading corridor forecast…</span>}
        {status === "error" && <span className="error-text">Heatmap unavailable: {error}</span>}
        {truckNote && <span className="truck-note">{truckNote}</span>}
      </div>
    </div>
  );
}
