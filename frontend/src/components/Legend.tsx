import { METRICS, type HeatMetric } from "../lib/heatmap";
import { LEVELS } from "../lib/risk";

export function Legend({ metric }: { metric: HeatMetric }) {
  const meta = METRICS.find((m) => m.id === metric)!;
  return (
    <div className="legend" aria-label="Risk legend">
      {LEVELS.map((l, i) => (
        <div key={l.key} className="legend-row">
          <span className="dot" style={{ background: l.color }} />
          <span>{l.label}</span>
          {metric !== "risk" && (
            <small>
              {i === 0 ? `< ${meta.thresholds[0]}` : `≥ ${meta.thresholds[i - 1]}`} {meta.unit}
            </small>
          )}
        </div>
      ))}
    </div>
  );
}
