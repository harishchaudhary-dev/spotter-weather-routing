"""Route options from OSRM.

OSRM's `alternatives` often yields fewer than three routes (it only returns genuinely different
paths that pass its internal quality checks). When that happens we synthesise more options by
routing through via-points pushed sideways off the origin→destination chord, then keep a candidate
only if it is (a) not much slower than the fastest route, (b) mostly different from the routes
already chosen, and (c) free of out-and-back spurs caused by a via-point snapping to a side road.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

from ..domain.geo import LatLon, ProximityIndex, haversine_mi, offset_point, resample
from ..domain.route import Route, build_route
from .http import NotFoundError, ProviderError, get_json

log = logging.getLogger(__name__)

MAX_SLOWDOWN = 1.5  # synthetic alternatives may be at most 50% slower than the fastest route
MAX_OVERLAP = 0.8  # …and must share at most 80% of their length with any route already chosen
MAX_VIA_ATTEMPTS = 6
# (fraction along the chord, sideways offset as a fraction of chord length; + is left)
VIA_CANDIDATES = ((0.5, 0.15), (0.5, -0.15), (0.4, 0.3), (0.6, -0.3), (0.6, 0.3), (0.4, -0.3), (0.5, 0.45), (0.5, -0.45))


def fetch_routes(origin: LatLon, destination: LatLon, count: int = 3) -> list[Route]:
    if haversine_mi(origin, destination) < 1:
        raise NotFoundError("Origin and destination are the same place.")

    key = f"route:v2:{count}:{origin[0]:.4f},{origin[1]:.4f}:{destination[0]:.4f},{destination[1]:.4f}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    routes = _osrm_routes([origin, destination], alternatives=count)
    fastest = routes[0].duration_s
    attempts = 0
    for along, across in VIA_CANDIDATES:
        if len(routes) >= count or attempts >= MAX_VIA_ATTEMPTS:
            break
        attempts += 1
        via = offset_point(origin, destination, along, across)
        try:
            candidate = _osrm_routes([origin, via, destination], alternatives=0)[0]
        except (ProviderError, NotFoundError) as exc:
            log.info("via-point %s rejected: %s", via, exc)
            continue
        if _acceptable(candidate, routes, fastest):
            routes.append(candidate)

    routes = sorted(routes, key=lambda r: r.duration_s)[:count]
    cache.set(key, routes, settings.ROUTE_CACHE_TTL_S)
    return routes


def _osrm_routes(waypoints: list[LatLon], alternatives: int) -> list[Route]:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    data = get_json(
        f"{settings.OSRM_URL}/route/v1/driving/{path}",
        {
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "alternatives": str(alternatives) if alternatives else "false",
            "steps": "true",  # needed only to name the major roads ("via I 76, I 80")
        },
        service="Routing service",
        ok_statuses=(200, 400),  # OSRM reports NoRoute / InvalidQuery as 400 with a JSON body
    )
    if data.get("code") != "Ok" or not data.get("routes"):
        raise NotFoundError("No drivable route was found between those places.")
    return [_to_route(r) for r in data["routes"]]


def _to_route(raw: dict) -> Route:
    coords = [(lat, lon) for lon, lat in raw["geometry"]["coordinates"]]
    meters: list[float] = []
    seconds: list[float] = []
    for leg in raw.get("legs", []):
        annotation = leg.get("annotation") or {}
        meters.extend(annotation.get("distance", []))
        seconds.extend(annotation.get("duration", []))
    return build_route(
        coords,
        meters or None,
        seconds or None,
        total_seconds=raw["duration"],
        max_speed_mph=settings.TRUCK_MAX_SPEED_MPH,
        via=_major_roads(raw.get("legs", [])),
    )


def _major_roads(legs: list[dict], top: int = 3) -> str:
    """The few roads carrying the most distance, listed in driving order (e.g. "I 76, I 80")."""
    distance: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for step in (s for leg in legs for s in leg.get("steps", [])):
        road = (step.get("ref") or step.get("name") or "").split(";")[0].strip()
        if road:
            distance[road] = distance.get(road, 0.0) + step.get("distance", 0.0)
            first_seen.setdefault(road, len(first_seen))
    total = sum(distance.values()) or 1.0
    biggest = [r for r in sorted(distance, key=distance.get, reverse=True)[:top] if distance[r] / total >= 0.1]
    return ", ".join(sorted(biggest, key=first_seen.get))


def _acceptable(candidate: Route, chosen: list[Route], fastest_s: float) -> bool:
    if candidate.duration_s > fastest_s * MAX_SLOWDOWN:
        return False
    probe = resample(candidate.coords, 1.0)
    for existing in chosen:
        index = ProximityIndex(resample(existing.coords, 0.5), radius_mi=0.4)
        shared = sum(1 for p in probe if index.near(p)) / len(probe)
        if shared > MAX_OVERLAP:
            return False
    return not _has_spur(probe)


def _has_spur(points: list[LatLon], min_gap: int = 4, radius_mi: float = 0.2) -> bool:
    """True if the path comes back within `radius_mi` of where it was ≥ `min_gap` samples earlier,
    the signature of a detour into a via-point and straight back out."""
    cell = radius_mi / 69.0
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, (lat, lon) in enumerate(points):
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-2, -1, 0, 1, 2):
                for j in buckets.get((ky + dy, kx + dx), ()):
                    if i - j >= min_gap and haversine_mi(points[i], points[j]) <= radius_mi:
                        return True
        buckets.setdefault((ky, kx), []).append(i)
    return False
