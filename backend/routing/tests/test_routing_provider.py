import pytest
from django.core.cache import cache

from routing.domain.geo import cumulative_miles
from routing.providers import routing
from routing.providers.http import NotFoundError


def osrm_route(coords_lonlat, duration):
    lat_lon = [(lat, lon) for lon, lat in coords_lonlat]
    cum = cumulative_miles(lat_lon)
    meters = [(b - a) * 1609.344 for a, b in zip(cum, cum[1:])]
    seconds = [duration * m / sum(meters) for m in meters]
    steps = [
        {"name": "Main St", "ref": "", "distance": 500},
        {"name": "Interstate 80", "ref": "I 80", "distance": sum(meters) * 0.7},
        {"name": "", "ref": "US 6;US 34", "distance": sum(meters) * 0.3},
    ]
    return {
        "duration": duration,
        "distance": sum(meters),
        "geometry": {"coordinates": coords_lonlat},
        "legs": [{"steps": steps, "annotation": {"distance": meters, "duration": seconds}}],
    }


def line(lon0, lat0, lon1, lat1, n=40, bulge=0.0):
    return [
        [lon0 + (lon1 - lon0) * i / n, lat0 + (lat1 - lat0) * i / n + bulge * (1 - (2 * i / n - 1) ** 2)]
        for i in range(n + 1)
    ]


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def test_uses_osrm_alternatives_when_three_are_returned(monkeypatch):
    calls = []

    def fake(url, params, **_):
        calls.append(url)
        return {"code": "Ok", "routes": [osrm_route(line(-100, 40, -95, 40, bulge=b), 18000 + i) for i, b in enumerate((0, 1, -1))]}

    monkeypatch.setattr(routing, "get_json", fake)
    routes = routing.fetch_routes((40, -100), (40, -95))
    assert len(routes) == 3 and len(calls) == 1
    assert routes[0].via == "I 80, US 6"  # refs over names, minor roads dropped, driving order kept


def test_synthesises_alternatives_via_offset_points(monkeypatch):
    def fake(url, params, **_):
        n_waypoints = url.rsplit("/", 1)[1].count(";") + 1
        if n_waypoints == 2:
            return {"code": "Ok", "routes": [osrm_route(line(-100, 40, -95, 40), 18000)]}
        via_lat = float(url.rsplit("/", 1)[1].split(";")[1].split(",")[1])
        return {"code": "Ok", "routes": [osrm_route(line(-100, 40, -95, 40, bulge=via_lat - 40), 20000)]}

    monkeypatch.setattr(routing, "get_json", fake)
    routes = routing.fetch_routes((40, -100), (40, -95))
    assert len(routes) == 3
    assert routes[0].duration_s < routes[1].duration_s


def test_rejects_duplicates_and_much_slower_candidates(monkeypatch):
    def fake(url, params, **_):
        n_waypoints = url.rsplit("/", 1)[1].count(";") + 1
        if n_waypoints == 2:
            return {"code": "Ok", "routes": [osrm_route(line(-100, 40, -95, 40), 18000)]}
        # every via-route is either identical to the main route or 3x slower
        return {"code": "Ok", "routes": [osrm_route(line(-100, 40, -95, 40), 18000 if "40.0" in url else 54000)]}

    monkeypatch.setattr(routing, "get_json", fake)
    assert len(routing.fetch_routes((40, -100), (40, -95))) == 1


def test_no_route_maps_to_not_found(monkeypatch):
    monkeypatch.setattr(routing, "get_json", lambda *a, **k: {"code": "NoRoute", "routes": []})
    with pytest.raises(NotFoundError):
        routing.fetch_routes((40, -100), (10, 0))


def test_spur_detection():
    out_and_back = [(40 + i * 0.01, -100.0) for i in range(10)] + [(40 + (9 - i) * 0.01, -100.0) for i in range(10)]
    straight = [(40 + i * 0.015, -100.0) for i in range(20)]
    assert routing._has_spur(out_and_back)
    assert not routing._has_spur(straight)
