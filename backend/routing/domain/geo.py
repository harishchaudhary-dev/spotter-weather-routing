"""Small spherical-geometry toolkit. Coordinates are (lat, lon) tuples in degrees throughout the
backend; they are only flipped to GeoJSON's [lon, lat] order at the API boundary."""
from __future__ import annotations

import math
from bisect import bisect_right
from typing import Sequence

LatLon = tuple[float, float]

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def cumulative_miles(coords: Sequence[LatLon]) -> list[float]:
    """Running distance at every vertex; result[0] == 0 and result[-1] == polyline length."""
    out = [0.0]
    for prev, cur in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_mi(prev, cur))
    return out


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def interpolate_along(coords: Sequence[LatLon], cum: Sequence[float], mile: float) -> LatLon:
    """Point located `mile` miles along the polyline (clamped to its ends)."""
    if mile <= 0:
        return coords[0]
    if mile >= cum[-1]:
        return coords[-1]
    i = bisect_right(cum, mile) - 1
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg == 0 else (mile - cum[i]) / seg
    return lerp(coords[i][0], coords[i + 1][0], t), lerp(coords[i][1], coords[i + 1][1], t)


def interpolate_series(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    """Piecewise-linear lookup of y at x for a monotonically non-decreasing xs."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x) - 1
    span = xs[i + 1] - xs[i]
    t = 0.0 if span == 0 else (x - xs[i]) / span
    return lerp(ys[i], ys[i + 1], t)


def slice_polyline(coords: Sequence[LatLon], cum: Sequence[float], start_mi: float, end_mi: float) -> list[LatLon]:
    """Sub-polyline between two mileposts, including interpolated end points."""
    inner = [coords[i] for i, m in enumerate(cum) if start_mi < m < end_mi]
    return [interpolate_along(coords, cum, start_mi), *inner, interpolate_along(coords, cum, end_mi)]


def simplify_indices(coords: Sequence[LatLon], tolerance_mi: float) -> list[int]:
    """Douglas-Peucker on a local equirectangular projection. Returns kept vertex indices so
    callers can carry parallel arrays (e.g. per-vertex time) through the simplification."""
    n = len(coords)
    if n <= 2:
        return list(range(n))
    lat0 = math.radians(sum(c[0] for c in coords) / n)
    k = EARTH_RADIUS_MI * math.pi / 180
    pts = [(c[1] * k * math.cos(lat0), c[0] * k) for c in coords]

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        (ax, ay), (bx, by) = pts[first], pts[last]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        worst, worst_i = -1.0, -1
        for i in range(first + 1, last):
            px, py = pts[i]
            if norm == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > worst:
                worst, worst_i = d, i
        if worst > tolerance_mi:
            keep[worst_i] = True
            stack.append((first, worst_i))
            stack.append((worst_i, last))
    return [i for i, kept in enumerate(keep) if kept]


def offset_point(origin: LatLon, toward: LatLon, along: float, across: float) -> LatLon:
    """Point at fraction `along` of the origin→toward chord, pushed sideways by `across` × chord
    length (positive = left of travel). Uses a local flat projection, which is fine for picking
    via-points that only need to be roughly placed."""
    lat0 = math.radians((origin[0] + toward[0]) / 2)
    cos0 = max(math.cos(lat0), 1e-6)
    x0, y0 = origin[1] * cos0, origin[0]
    x1, y1 = toward[1] * cos0, toward[0]
    dx, dy = x1 - x0, y1 - y0
    x = x0 + dx * along - dy * across
    y = y0 + dy * along + dx * across
    return y, x / cos0


class ProximityIndex:
    """Grid-bucketed point set answering "is anything within `radius_mi` of this point?" in O(1)."""

    def __init__(self, points: Sequence[LatLon], radius_mi: float):
        self.radius_mi = radius_mi
        self.cell_deg = max(radius_mi / 69.0, 1e-4)  # one degree of latitude ≈ 69 miles
        self.buckets: dict[tuple[int, int], list[LatLon]] = {}
        for p in points:
            self.buckets.setdefault(self._key(p), []).append(p)

    def _key(self, p: LatLon) -> tuple[int, int]:
        return math.floor(p[0] / self.cell_deg), math.floor(p[1] / self.cell_deg)

    def near(self, p: LatLon) -> bool:
        # Longitude degrees shrink with latitude, so widen the lon search accordingly.
        ky, kx = self._key(p)
        lon_span = math.ceil(1 / max(math.cos(math.radians(p[0])), 0.05))
        for dy in (-1, 0, 1):
            for dx in range(-lon_span, lon_span + 1):
                for q in self.buckets.get((ky + dy, kx + dx), ()):
                    if haversine_mi(p, q) <= self.radius_mi:
                        return True
        return False


def resample(coords: Sequence[LatLon], every_mi: float) -> list[LatLon]:
    """Points every `every_mi` miles along the polyline (always including both ends)."""
    cum = cumulative_miles(coords)
    total = cum[-1]
    if total == 0:
        return [coords[0]]
    steps = max(1, math.ceil(total / every_mi))
    return [interpolate_along(coords, cum, total * i / steps) for i in range(steps + 1)]
