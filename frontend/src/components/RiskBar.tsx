import type { MilesByLevel } from "../api/types";
import { fmtMiles } from "../lib/format";
import { LEVELS } from "../lib/risk";

/** Stacked bar of road miles per risk level. */
export function RiskBar({ miles }: { miles: MilesByLevel }) {
  const total = LEVELS.reduce((sum, l) => sum + miles[l.key], 0) || 1;
  const description = LEVELS.filter((l) => miles[l.key] > 0)
    .map((l) => `${l.label} ${fmtMiles(miles[l.key])}`)
    .join(", ");
  return (
    <div className="risk-bar" role="img" aria-label={`Miles by risk: ${description}`}>
      {LEVELS.map((l) =>
        miles[l.key] > 0 ? (
          <span
            key={l.key}
            style={{ width: `${(miles[l.key] / total) * 100}%`, background: l.color }}
            title={`${l.label}: ${fmtMiles(miles[l.key])}`}
          />
        ) : null,
      )}
    </div>
  );
}
