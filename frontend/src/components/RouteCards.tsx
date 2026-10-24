import type { RouteOption, TripPlan } from "../api/types";
import { fmtDuration, fmtMiles, fmtTime } from "../lib/format";
import { levelMeta, routeColor } from "../lib/risk";
import { RiskBar } from "./RiskBar";

interface Props {
  plan: TripPlan;
  selectedId: string;
  onSelect: (id: string) => void;
}

export function RouteCards({ plan, selectedId, onSelect }: Props) {
  const { recommendation } = plan;
  const ordered = [...plan.routes].sort((a, b) => a.rank - b.rank);
  return (
    <section className="routes" aria-label="Route options">
      <div className="recommendation">
        <div className="eyebrow">Recommendation</div>
        <p>
          <strong>{plan.routes.find((r) => r.id === recommendation.route_id)?.name}</strong> — {recommendation.reason}
        </p>
        {recommendation.advisories.map((a) => (
          <p key={a} className="advisory" role="alert">
            ⚠ {a}
          </p>
        ))}
      </div>
      {ordered.map((r) => (
        <RouteCard key={r.id} route={r} selected={r.id === selectedId} onSelect={() => onSelect(r.id)} />
      ))}
    </section>
  );
}

function RouteCard({ route, selected, onSelect }: { route: RouteOption; selected: boolean; onSelect: () => void }) {
  const s = route.summary;
  const worst = levelMeta(s.max_level);
  return (
    <button
      type="button"
      className={`route-card${selected ? " selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
      style={{ ["--route" as string]: routeColor(route.id) }}
    >
      <div className="route-card-head">
        <span className="swatch" />
        <span className="route-name">{route.name}</span>
        {route.recommended && <span className="badge best">Recommended</span>}
        <span className="rank">#{route.rank}</span>
      </div>
      {route.via && <div className="via">via {route.via}</div>}
      <div className="stats">
        <Stat label="Drive time" value={fmtDuration(s.duration_s)} />
        <Stat label="Distance" value={fmtMiles(s.distance_mi)} />
        <Stat label="Arrive" value={fmtTime(s.arrival)} />
      </div>
      <RiskBar miles={s.miles_by_level} />
      <div className="exposure">
        <span>
          Severe+ <b>{fmtMiles(s.miles_by_level.severe + s.miles_by_level.no_travel)}</b>
        </span>
        <span>
          High <b>{fmtMiles(s.miles_by_level.high)}</b>
        </span>
        <span>
          Avg risk <b>{s.avg_risk.toFixed(2)}</b>
        </span>
        <span className="worst" style={{ color: worst.color }}>
          Worst: {worst.label}
        </span>
      </div>
    </button>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
