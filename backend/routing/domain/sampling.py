"""Checkpoint placement along a route and the ETA at each one."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .route import Route

ALLOWED_INTERVALS_MI = (10, 25, 50)


@dataclass(frozen=True)
class Checkpoint:
    index: int
    mile: float
    lat: float
    lon: float
    eta: datetime
    # The stretch of road this checkpoint's weather is taken to represent (midpoint to midpoint
    # between neighbours). Coverage sums exactly to the route length for any interval, which is
    # what makes "Severe miles" comparable across routes and intervals.
    covers_from_mi: float
    covers_to_mi: float

    @property
    def coverage_mi(self) -> float:
        return self.covers_to_mi - self.covers_from_mi


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """0, interval, 2·interval, … plus the destination itself."""
    if interval_mi <= 0:
        raise ValueError("interval must be positive")
    miles: list[float] = []
    mile = 0.0
    while mile < total_mi:
        miles.append(mile)
        mile += interval_mi
    miles.append(total_mi)
    return miles


def place_checkpoints(route: Route, interval_mi: float, departure: datetime) -> list[Checkpoint]:
    miles = checkpoint_miles(route.distance_mi, interval_mi)
    edges = [0.0, *[(a + b) / 2 for a, b in zip(miles, miles[1:])], route.distance_mi]
    checkpoints = []
    for i, mile in enumerate(miles):
        lat, lon = route.point_at(mile)
        checkpoints.append(
            Checkpoint(
                index=i,
                mile=mile,
                lat=lat,
                lon=lon,
                eta=departure + timedelta(seconds=route.seconds_at(mile)),
                covers_from_mi=edges[i],
                covers_to_mi=edges[i + 1],
            )
        )
    return checkpoints
