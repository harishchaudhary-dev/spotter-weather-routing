"""Provider-agnostic route model with a per-vertex distance *and* time profile, so ETAs at any
milepost reflect where the truck is actually slow (cities, ramps) rather than an average speed."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .geo import LatLon, METERS_PER_MILE, cumulative_miles, interpolate_along, interpolate_series


@dataclass(frozen=True)
class Route:
    coords: tuple[LatLon, ...]
    cum_miles: tuple[float, ...]
    cum_seconds: tuple[float, ...]
    via: str = ""  # human summary of major roads, e.g. "I 80, I 76"

    @property
    def distance_mi(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_seconds[-1]

    def seconds_at(self, mile: float) -> float:
        return interpolate_series(self.cum_miles, self.cum_seconds, mile)

    def point_at(self, mile: float) -> LatLon:
        return interpolate_along(self.coords, self.cum_miles, mile)


def build_route(
    coords: Sequence[LatLon],
    segment_meters: Sequence[float] | None,
    segment_seconds: Sequence[float] | None,
    total_seconds: float,
    max_speed_mph: float,
    via: str = "",
) -> Route:
    """Assemble a Route from provider output.

    When the provider gives per-segment distance/duration aligned with the geometry, each segment's
    time is floored at what a truck capped at `max_speed_mph` needs. Otherwise we fall back to
    spreading the provider's total time proportionally to distance (still capped).
    """
    cum_mi = cumulative_miles(coords)
    n_segments = len(coords) - 1
    aligned = (
        segment_meters is not None
        and segment_seconds is not None
        and len(segment_meters) == n_segments
        and len(segment_seconds) == n_segments
    )

    seconds = [0.0]
    if aligned:
        for meters, secs in zip(segment_meters, segment_seconds):
            seconds.append(seconds[-1] + max(secs, _min_seconds(meters / METERS_PER_MILE, max_speed_mph)))
    else:
        total_mi = cum_mi[-1] or 1.0
        for i in range(n_segments):
            miles = cum_mi[i + 1] - cum_mi[i]
            secs = total_seconds * miles / total_mi
            seconds.append(seconds[-1] + max(secs, _min_seconds(miles, max_speed_mph)))

    return Route(coords=tuple(coords), cum_miles=tuple(cum_mi), cum_seconds=tuple(seconds), via=via)


def _min_seconds(miles: float, max_speed_mph: float) -> float:
    return miles / max_speed_mph * 3600
