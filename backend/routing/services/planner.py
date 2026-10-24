"""Trip planning use-case: routes → checkpoints at ETA → weather → risk → exposure → recommendation.

Providers are injected (defaulting to the real adapters) so the whole pipeline is testable offline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Sequence

from ..domain.geo import LatLon, haversine_mi, resample
from ..domain.recommendation import Exposure, Recommendation, recommend, summarize_exposure
from ..domain.risk import Conditions, RiskAssessment, assess
from ..domain.route import Route
from ..domain.sampling import Checkpoint, place_checkpoints
from ..providers import routing, weather
from ..providers.geocoding import Place

RouteFetcher = Callable[[LatLon, LatLon], list[Route]]
WeatherLookup = Callable[[Sequence[tuple[float, float, datetime]]], list[Conditions]]

ROUTE_NAMES = "ABC"


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime
    load_lbs: float
    interval_mi: int


@dataclass(frozen=True)
class AssessedCheckpoint:
    checkpoint: Checkpoint
    conditions: Conditions
    risk: RiskAssessment


@dataclass(frozen=True)
class PlannedRoute:
    id: str
    name: str
    route: Route
    checkpoints: list[AssessedCheckpoint]
    exposure: Exposure
    label_point: LatLon


@dataclass(frozen=True)
class TripPlan:
    request: TripRequest
    routes: list[PlannedRoute]
    recommendation: Recommendation


def plan_trip(
    request: TripRequest,
    fetch_routes: RouteFetcher = routing.fetch_routes,
    weather_at: WeatherLookup = weather.conditions_at,
) -> TripPlan:
    origin = (request.origin.lat, request.origin.lon)
    destination = (request.destination.lat, request.destination.lon)
    routes = sorted(fetch_routes(origin, destination), key=lambda r: r.duration_s)

    # Place checkpoints on every route first, then make ONE weather call for all of them.
    placed = [place_checkpoints(r, request.interval_mi, request.departure) for r in routes]
    flat = [cp for cps in placed for cp in cps]
    conditions = iter(weather_at([(cp.lat, cp.lon, cp.eta) for cp in flat]))

    planned = []
    for i, (route, checkpoints) in enumerate(zip(routes, placed)):
        assessed = []
        for cp in checkpoints:
            cond = next(conditions)
            assessed.append(AssessedCheckpoint(cp, cond, assess(cond, request.load_lbs)))
        route_id = f"route-{ROUTE_NAMES[i].lower()}"
        exposure = summarize_exposure(route_id, ((a.risk.level, a.checkpoint.coverage_mi) for a in assessed), route.duration_s)
        others = [r for r in routes if r is not route]
        planned.append(PlannedRoute(route_id, f"Route {ROUTE_NAMES[i]}", route, assessed, exposure, _label_point(route, others)))

    return TripPlan(request, planned, recommend([p.exposure for p in planned]))


def _label_point(route: Route, others: list[Route]) -> LatLon:
    """Spot on the route that is farthest from every other route, so map labels don't overlap."""
    candidates = resample(route.coords, max(route.distance_mi / 40, 0.5))
    inner = candidates[len(candidates) // 5 : -(len(candidates) // 5) or None] or candidates
    if not others:
        return inner[len(inner) // 2]
    other_points = [p for o in others for p in resample(o.coords, max(o.distance_mi / 60, 0.5))]
    return max(inner, key=lambda p: min(haversine_mi(p, q) for q in other_points))
