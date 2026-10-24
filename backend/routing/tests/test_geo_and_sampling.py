from datetime import datetime, timezone

import pytest

from routing.domain.geo import (
    ProximityIndex,
    cumulative_miles,
    haversine_mi,
    offset_point,
    simplify_indices,
    slice_polyline,
)
from routing.domain.route import build_route
from routing.domain.sampling import checkpoint_miles, place_checkpoints

DEPART = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def straight_route(miles: float, speed_mph: float = 60.0, n: int = 50):
    """A due-north line (1° lat ≈ 69.09 mi) with constant speed."""
    deg = miles / 69.09
    coords = [(40 + deg * i / n, -100.0) for i in range(n + 1)]
    cum = cumulative_miles(coords)
    seg_m = [(b - a) * 1609.344 for a, b in zip(cum, cum[1:])]
    seg_s = [(b - a) / speed_mph * 3600 for a, b in zip(cum, cum[1:])]
    return build_route(coords, seg_m, seg_s, total_seconds=sum(seg_s), max_speed_mph=80)


def test_haversine_known_distance():
    # Denver → Kansas City is ~ 558 mi great-circle
    assert haversine_mi((39.7392, -104.9903), (39.0997, -94.5786)) == pytest.approx(558, abs=3)


@pytest.mark.parametrize(
    "total, interval, expected",
    [(100, 25, [0, 25, 50, 75, 100]), (60, 25, [0, 25, 50, 60]), (5, 10, [0, 5])],
)
def test_checkpoint_miles_always_include_destination(total, interval, expected):
    assert checkpoint_miles(total, interval) == expected


def test_checkpoint_coverage_sums_to_route_length_for_every_interval():
    route = straight_route(237)
    for interval in (10, 25, 50):
        cps = place_checkpoints(route, interval, DEPART)
        assert sum(cp.coverage_mi for cp in cps) == pytest.approx(route.distance_mi)
        assert cps[0].covers_from_mi == 0 and cps[-1].covers_to_mi == pytest.approx(route.distance_mi)


def test_eta_follows_route_time_profile():
    route = straight_route(120, speed_mph=60)
    cps = place_checkpoints(route, 25, DEPART)
    assert cps[0].eta == DEPART
    assert (cps[1].eta - DEPART).total_seconds() == pytest.approx(25 * 60, abs=5)
    assert (cps[-1].eta - DEPART).total_seconds() == pytest.approx(2 * 3600, abs=30)


def test_eta_reflects_slow_stretches():
    """First half crawls at 30 mph, second half at 60 mph: ETA at the midpoint is 2/3 of the trip."""
    coords = [(40 + i * 0.1, -100.0) for i in range(11)]
    cum = cumulative_miles(coords)
    seg_m = [(b - a) * 1609.344 for a, b in zip(cum, cum[1:])]
    seg_s = [(b - a) / (30 if i < 5 else 60) * 3600 for i, (a, b) in enumerate(zip(cum, cum[1:]))]
    route = build_route(coords, seg_m, seg_s, sum(seg_s), max_speed_mph=80)
    assert route.seconds_at(route.distance_mi / 2) == pytest.approx(route.duration_s * 2 / 3, rel=1e-6)


def test_truck_speed_cap_slows_fast_segments():
    route = straight_route(130, speed_mph=80)
    capped = build_route(route.coords, None, None, total_seconds=130 / 80 * 3600, max_speed_mph=65)
    assert capped.duration_s == pytest.approx(route.distance_mi / 65 * 3600, rel=1e-6)


def test_misaligned_annotations_fall_back_to_proportional_time():
    route = straight_route(50)
    fallback = build_route(route.coords, [1.0], [1.0], total_seconds=3600, max_speed_mph=200)
    assert fallback.duration_s == pytest.approx(3600)


def test_simplify_keeps_endpoints_and_drops_collinear_points():
    coords = [(40 + i * 0.01, -100.0) for i in range(100)]
    kept = simplify_indices(coords, 0.01)
    assert kept == [0, 99]


def test_slice_polyline_endpoints_are_interpolated():
    coords = [(40.0, -100.0), (41.0, -100.0)]
    cum = cumulative_miles(coords)
    part = slice_polyline(coords, cum, cum[-1] * 0.25, cum[-1] * 0.75)
    assert part[0][0] == pytest.approx(40.25) and part[-1][0] == pytest.approx(40.75)


def test_offset_point_is_left_of_travel_for_positive_offset():
    lat, lon = offset_point((40, -100), (40, -90), 0.5, 0.2)  # heading east → left is north
    assert lat > 40 and lon == pytest.approx(-95)


def test_proximity_index():
    index = ProximityIndex([(40.0, -100.0)], radius_mi=5)
    assert index.near((40.05, -100.0))  # ~3.5 mi
    assert not index.near((40.2, -100.0))  # ~14 mi
