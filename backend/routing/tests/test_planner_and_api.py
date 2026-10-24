from datetime import datetime, timedelta, timezone

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from routing.api import views
from routing.domain.geo import cumulative_miles, haversine_mi, resample
from routing.domain.risk import Conditions
from routing.domain.route import build_route
from routing.providers import weather
from routing.providers.geocoding import Place
from routing.services import heatmap, planner
from routing.services.planner import TripRequest, plan_trip


def make_route(bulge: float, hours: float):
    coords = [(40 + bulge * (1 - (2 * i / 60 - 1) ** 2), -100 + 5 * i / 60) for i in range(61)]
    cum = cumulative_miles(coords)
    return build_route(coords, None, None, total_seconds=hours * 3600, max_speed_mph=200, via="US 36")


FAST_STORMY = make_route(0.0, 5)
SLOW_CALM = make_route(1.0, 6)
MEDIUM = make_route(-1.0, 5.5)


def fake_routes(_origin, _destination):
    return [SLOW_CALM, FAST_STORMY, MEDIUM]


def storm_on_straight_line(queries):
    """45 mph wind only near lat 40.0 (the straight route) — Severe for light loads, No Travel >30k lb."""
    return [Conditions(wind_mph=48 if abs(lat - 40) < 0.05 else 10, rain_in_hr=0, snow_in_hr=0) for lat, _, _ in queries]


def request(load=20_000, interval=25):
    return TripRequest(
        origin=Place("A", 40, -100),
        destination=Place("B", 40, -95),
        departure=datetime(2026, 3, 1, 8, tzinfo=timezone.utc),
        load_lbs=load,
        interval_mi=interval,
    )


def test_planner_avoids_storm_and_names_routes_by_speed():
    plan = plan_trip(request(), fetch_routes=fake_routes, weather_at=storm_on_straight_line)
    assert [r.name for r in plan.routes] == ["Route A", "Route B", "Route C"]
    assert plan.routes[0].route is FAST_STORMY
    assert plan.recommendation.route_id != "route-a"
    assert plan.recommendation.decided_by == "severe_mi"


def test_planner_applies_load_rules():
    plan = plan_trip(request(load=35_000), fetch_routes=fake_routes, weather_at=storm_on_straight_line)
    assert plan.routes[0].exposure.miles_by_level[4] > 0  # No Travel on the stormy straight line
    assert plan.recommendation.decided_by == "no_travel_mi"


def test_planner_looks_up_weather_at_each_checkpoint_eta():
    seen = []

    def spy(queries):
        seen.extend(queries)
        return [Conditions(0, 0, 0) for _ in queries]

    plan = plan_trip(request(interval=50), fetch_routes=lambda o, d: [FAST_STORMY], weather_at=spy)
    etas = [q[2] for q in seen]
    assert etas[0] == datetime(2026, 3, 1, 8, tzinfo=timezone.utc)
    assert etas[-1] == datetime(2026, 3, 1, 13, tzinfo=timezone.utc)
    assert etas == sorted(etas)
    assert len(seen) == len(plan.routes[0].checkpoints)


def test_heatmap_grid_is_bounded_tight_and_aligned_to_weather_cells():
    corridor = [[(40.0, -120.0 + i) for i in range(41)]]  # ~2,100 mi east-west
    points, step = heatmap.corridor_grid(corridor)
    cell = weather.cell_deg()
    assert 0 < len(points) <= heatmap.MAX_POINTS
    # Tight: brute-force count at the next finer spacing must exceed the budget.
    finer = round(step - cell, 4)
    if finer > 0:
        samples = resample(corridor[0], 5.0)
        buffer = min(heatmap.MAX_BUFFER_MI, max(heatmap.MIN_BUFFER_MI, 0.04 * cumulative_miles(corridor[0])[-1]))
        count = sum(
            1
            for i in range(int(38 / finer), int(42 / finer) + 2)
            for j in range(int(-122 / finer) - 1, int(-78 / finer) + 2)
            if min(haversine_mi((i * finer, j * finer), s) for s in samples) <= buffer
        )
        assert count > heatmap.MAX_POINTS
    assert step / cell == pytest.approx(round(step / cell))
    for lat, lon in points:
        assert weather.cell_center(weather.cell_of(lat, lon)) == pytest.approx((lat, lon))


def test_heatmap_does_not_bridge_separate_routes():
    """Two short parallel routes 6° apart: the gap between them must not be filled."""
    north = [(46.0, -100.0), (46.0, -99.0)]
    south = [(40.0, -100.0), (40.0, -99.0)]
    points, _ = heatmap.corridor_grid([north, south])
    assert not any(42.0 < lat < 44.0 for lat, _ in points)


# ------------------------------------------------------------------------------- API


@pytest.fixture
def client():
    cache.clear()
    return APIClient()


def future(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def test_plan_endpoint_shape(client, monkeypatch):
    real = planner.plan_trip
    monkeypatch.setattr(views, "plan_trip", lambda req: real(req, fake_routes, storm_on_straight_line))
    body = {
        "origin": {"label": "A", "lat": 40, "lon": -100},
        "destination": {"label": "B", "lat": 40, "lon": -95},
        "departure": future(),
        "load_weight_lbs": 20000,
        "interval_miles": 10,
    }
    res = client.post("/api/plan", body, format="json")
    assert res.status_code == 200, res.content
    data = res.json()
    assert len(data["routes"]) == 3
    route = data["routes"][0]
    assert route["geometry"]["type"] == "LineString"
    assert len(route["timeline_s"]) == len(route["geometry"]["coordinates"])
    assert sum(route["summary"]["miles_by_level"].values()) == pytest.approx(route["summary"]["distance_mi"], abs=0.5)
    assert {"eta", "weather", "risk", "covers_mi"} <= set(route["checkpoints"][0])
    assert sum(1 for r in data["routes"] if r["recommended"]) == 1


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"interval_miles": 15}, "Interval miles"),
        ({"load_weight_lbs": -1}, "Load weight lbs"),
        ({"departure": "2001-01-01T00:00:00Z"}, "past"),
        ({"origin": {"lat": 200, "lon": 0}}, "Origin"),
    ],
)
def test_plan_validation_errors(client, patch, message):
    body = {
        "origin": {"label": "A", "lat": 40, "lon": -100},
        "destination": {"label": "B", "lat": 40, "lon": -95},
        "departure": future(),
        "load_weight_lbs": 20000,
        "interval_miles": 25,
        **patch,
    }
    res = client.post("/api/plan", body, format="json")
    assert res.status_code == 400
    assert message in res.json()["error"]["message"]


def test_departure_too_far_ahead_is_rejected(client):
    body = {
        "origin": {"lat": 40, "lon": -100},
        "destination": {"lat": 40, "lon": -95},
        "departure": future(hours=24 * 30),
        "load_weight_lbs": 1000,
    }
    assert client.post("/api/plan", body, format="json").status_code == 400


def test_heatmap_endpoint(client, monkeypatch):
    def fake_grid(points, start, hours):
        return [[Conditions(wind_mph=50, rain_in_hr=0, snow_in_hr=0) for _ in points] for _ in range(hours + 1)]

    real = heatmap.corridor_heatmap
    monkeypatch.setattr(views, "corridor_heatmap", lambda *a: real(*a, fetch_grid=fake_grid))
    body = {"corridor": [[[-100, 40], [-98, 40.5], [-95, 40]]], "departure": future(), "load_weight_lbs": 35000}
    res = client.post("/api/heatmap", body, format="json")
    assert res.status_code == 200, res.content
    data = res.json()
    assert len(data["risk"]) == 49
    assert len(data["risk"][0]) == len(data["points"])
    assert data["risk"][0][0] == 4  # 50 mph with > 30k lb → No Travel


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
