"""Corridor weather heatmap: a regular grid of points within a buffer around the trip's routes,
with 0–48 h of hourly conditions and load-aware risk at each point.

The grid is aligned to the weather cache's 0.1° cells and its spacing is the finest that keeps the
point count bounded (so it widens on long trips). All hours ship in one payload, so scrubbing the
forecast slider in the browser never touches the network.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from ..domain.geo import LatLon, ProximityIndex, cumulative_miles, resample
from ..domain.risk import Conditions, assess
from ..providers import weather

MAX_POINTS = 260
MIN_BUFFER_MI, MAX_BUFFER_MI = 25.0, 50.0
MILES_PER_DEG_LAT = 69.0

GridFetcher = Callable[[Sequence[LatLon], datetime, int], list[list[Conditions]]]


@dataclass(frozen=True)
class Heatmap:
    start: datetime
    hours: int
    step_deg: float
    points: list[LatLon]
    risk: list[list[int]]  # [hour][point]
    wind_mph: list[list[float]]
    rain_in_hr: list[list[float]]
    snow_in_hr: list[list[float]]


def corridor_heatmap(
    lines: Sequence[Sequence[LatLon]],
    start: datetime,
    load_lbs: float,
    hours: int = 48,
    fetch_grid: GridFetcher = weather.hourly_grid,
) -> Heatmap:
    points, step = corridor_grid(lines)
    start = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    grid = fetch_grid(points, start, hours)
    return Heatmap(
        start=start,
        hours=hours,
        step_deg=step,
        points=points,
        risk=[[int(assess(c, load_lbs).level) for c in row] for row in grid],
        wind_mph=[[round(c.wind_mph, 1) for c in row] for row in grid],
        rain_in_hr=[[round(c.rain_in_hr, 2) for c in row] for row in grid],
        snow_in_hr=[[round(c.snow_in_hr, 2) for c in row] for row in grid],
    )


def corridor_grid(lines: Sequence[Sequence[LatLon]], max_points: int = MAX_POINTS) -> tuple[list[LatLon], float]:
    """Grid points within a buffer of any line, at the finest spacing that keeps ≤ max_points.
    Spacing is a multiple of the weather cell size so every grid point sits on a cell centre."""
    quantum = weather.cell_deg()
    longest = max((cumulative_miles(line)[-1] for line in lines if len(line) > 1), default=0.0)
    buffer_mi = min(MAX_BUFFER_MI, max(MIN_BUFFER_MI, 0.04 * longest))
    samples = [p for line in lines for p in (resample(line, 5.0) if len(line) > 1 else line)]
    index = ProximityIndex(samples, radius_mi=buffer_mi)

    mid_lat = sum(p[0] for p in samples) / len(samples)
    cos_lat = max(math.cos(math.radians(mid_lat)), 0.2)

    def grid(step: float) -> list[LatLon]:
        return _grid_points(samples, index, step, buffer_mi, cos_lat)

    # Start from an area-based estimate, then walk coarser/finer by one quantum until it's tight.
    area = max(longest, 1.0) * 2 * buffer_mi * 1.3 + math.pi * buffer_mi**2
    n = max(1, math.ceil(math.sqrt(area / (max_points * MILES_PER_DEG_LAT**2 * cos_lat)) / quantum - 1e-9))
    points = grid(round(n * quantum, 4))
    while len(points) > max_points:
        n += 1
        points = grid(round(n * quantum, 4))
    while n > 1:
        finer = grid(round((n - 1) * quantum, 4))
        if len(finer) > max_points:
            break
        n, points = n - 1, finer
    return points, round(n * quantum, 4)


def _grid_points(samples, index: ProximityIndex, step: float, buffer_mi: float, cos_lat: float) -> list[LatLon]:
    pad_lat = buffer_mi / MILES_PER_DEG_LAT
    pad_lon = pad_lat / cos_lat
    lat_lo = math.floor((min(p[0] for p in samples) - pad_lat) / step)
    lat_hi = math.ceil((max(p[0] for p in samples) + pad_lat) / step)
    lon_lo = math.floor((min(p[1] for p in samples) - pad_lon) / step)
    lon_hi = math.ceil((max(p[1] for p in samples) + pad_lon) / step)
    points = []
    for i in range(lat_lo, lat_hi + 1):
        for j in range(lon_lo, lon_hi + 1):
            p = (round(i * step, 4), round(j * step, 4))
            if index.near(p):
                points.append(p)
    return points
