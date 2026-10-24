"""Route exposure summary and recommendation.

Ranking is lexicographic, exactly in the order the assessment specifies, with one addition in
front: **No Travel miles**. The spec's list starts at "fewest Severe miles", but a No Travel
stretch is strictly worse than a Severe one; without this key a route through a closed-wind
corridor could beat a route with a few Severe miles. Order:

    1. No Travel miles   2. Severe miles   3. High miles   4. average risk   5. travel time

Mileage is compared at 0.1 mi and average risk at 0.01 so floating-point noise never decides.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .risk import RiskLevel


@dataclass(frozen=True)
class Exposure:
    route_id: str
    miles_by_level: dict[RiskLevel, float]
    avg_risk: float  # distance-weighted mean of level scores (Low=0 … No Travel=4)
    duration_s: float

    def miles(self, level: RiskLevel) -> float:
        return self.miles_by_level.get(level, 0.0)


def summarize_exposure(route_id: str, segments: Iterable[tuple[RiskLevel, float]], duration_s: float) -> Exposure:
    """segments: (level, miles covered) per checkpoint."""
    miles_by_level = {level: 0.0 for level in RiskLevel}
    weighted = total = 0.0
    for level, miles in segments:
        miles_by_level[level] += miles
        weighted += int(level) * miles
        total += miles
    return Exposure(
        route_id=route_id,
        miles_by_level=miles_by_level,
        avg_risk=weighted / total if total else 0.0,
        duration_s=duration_s,
    )


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    value: Callable[[Exposure], float]
    fmt: Callable[[float], str]


def _fmt_miles(v: float) -> str:
    return f"{v:,.1f} mi"


def _fmt_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


CRITERIA: tuple[Criterion, ...] = (
    Criterion("no_travel_mi", "No Travel miles", lambda e: round(e.miles(RiskLevel.NO_TRAVEL), 1), _fmt_miles),
    Criterion("severe_mi", "Severe miles", lambda e: round(e.miles(RiskLevel.SEVERE), 1), _fmt_miles),
    Criterion("high_mi", "High miles", lambda e: round(e.miles(RiskLevel.HIGH), 1), _fmt_miles),
    Criterion("avg_risk", "average risk", lambda e: round(e.avg_risk, 2), lambda v: f"{v:.2f}"),
    Criterion("duration", "travel time", lambda e: round(e.duration_s), _fmt_duration),
)


def rank_key(exposure: Exposure) -> tuple[float, ...]:
    return tuple(c.value(exposure) for c in CRITERIA)


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    ranking: list[str]  # best first
    decided_by: str | None  # criterion key that separated #1 from #2 (None if only one route / exact tie)
    reason: str
    advisories: list[str]


def recommend(exposures: Sequence[Exposure]) -> Recommendation:
    if not exposures:
        raise ValueError("no routes to rank")
    ordered = sorted(exposures, key=rank_key)
    best = ordered[0]
    advisories = _advisories(best)

    if len(ordered) == 1:
        return Recommendation(best.route_id, [best.route_id], None, "Only one route was available.", advisories)

    runner_up = ordered[1]
    for criterion in CRITERIA:
        mine, theirs = criterion.value(best), criterion.value(runner_up)
        if mine != theirs:
            reason = (
                f"Fewest {criterion.label}" if criterion.key.endswith("_mi") else f"Lowest {criterion.label}"
            ) + f": {criterion.fmt(mine)} vs {criterion.fmt(theirs)} on the next-best route."
            if CRITERIA.index(criterion) > 0:
                tied = [c.label for c in CRITERIA[: CRITERIA.index(criterion)] if c.key != "no_travel_mi"]
                if tied:
                    reason = f"Tied on {', '.join(tied)}. " + reason
            return Recommendation(best.route_id, [e.route_id for e in ordered], criterion.key, reason, advisories)

    return Recommendation(
        best.route_id,
        [e.route_id for e in ordered],
        None,
        "All routes are equivalent on weather risk and travel time.",
        advisories,
    )


def _advisories(best: Exposure) -> list[str]:
    notes = []
    if best.miles(RiskLevel.NO_TRAVEL) > 0:
        notes.append(
            "Every option crosses No Travel conditions at this departure time. "
            "Delay departure or reduce load before driving."
        )
    elif best.miles(RiskLevel.SEVERE) > 0:
        notes.append("The recommended route still includes Severe weather. Consider a later departure.")
    return notes
