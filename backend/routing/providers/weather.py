"""Hourly forecasts from Open-Meteo (keyless, multi-location requests, 16-day horizon).

Design:
  * Space is bucketed into WEATHER_CELL_DEG cells (0.2° ≈ 13 mi by default). Checkpoints on
    different routes, and heatmap grid points, that fall in the same cell share one forecast.
  * Forecasts are cached per (cell, UTC day) so a request only fetches days it hasn't seen;
    re-sampling at another interval or re-planning with a different load costs no weather calls.
  * Missing cells are fetched in batches of up to 100 locations, a few batches in parallel.

Time semantics (per Open-Meteo docs): wind/temperature are instantaneous values at the hour
mark; rain/snowfall are totals over the *preceding* hour. For a truck passing at 13:20 we read
wind from the nearest hour (13:00) and precipitation from the 14:00 value (covering 13:00–14:00),
which is exactly an in/hr rate for the hour the truck is in.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from django.conf import settings
from django.core.cache import cache

from ..domain.geo import LatLon
from ..domain.risk import Conditions
from .http import ProviderError, get_json

log = logging.getLogger(__name__)

BATCH_SIZE = 100
MAX_PARALLEL_BATCHES = 4
HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m", "weather_code")
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54

Cell = tuple[int, int]
# One UTC day for one cell: 24 rows of (wind, gust, rain, snow, temp, code)
DaySeries = list[tuple[float, float, float, float, float | None, int | None]]


def cell_deg() -> float:
    return settings.WEATHER_CELL_DEG


def cell_of(lat: float, lon: float) -> Cell:
    return round(lat / cell_deg()), round(lon / cell_deg())


def cell_center(cell: Cell) -> LatLon:
    return round(cell[0] * cell_deg(), 4), round(cell[1] * cell_deg(), 4)


def _floor_hour(t: datetime) -> datetime:
    return t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _nearest_hour(t: datetime) -> datetime:
    return _floor_hour(t + timedelta(minutes=30))


def conditions_at(queries: Sequence[tuple[float, float, datetime]]) -> list[Conditions]:
    """Weather for each (lat, lon, instant). One network round-trip set for the whole list."""
    plan = []
    needed: dict[Cell, set[date]] = {}
    for lat, lon, when in queries:
        cell = cell_of(lat, lon)
        instant_hour = _nearest_hour(when)
        precip_hour = _floor_hour(when) + timedelta(hours=1)
        plan.append((cell, instant_hour, precip_hour))
        needed.setdefault(cell, set()).update({instant_hour.date(), precip_hour.date()})

    days = _load(needed)
    out = []
    for cell, instant_hour, precip_hour in plan:
        wind, gust, _, _, temp, code = days[(cell, instant_hour.date())][instant_hour.hour]
        _, _, rain, snow, _, _ = days[(cell, precip_hour.date())][precip_hour.hour]
        out.append(
            Conditions(wind_mph=wind, gust_mph=gust, rain_in_hr=rain, snow_in_hr=snow, temperature_f=temp, weather_code=code)
        )
    return out


def hourly_grid(points: Sequence[LatLon], start: datetime, hours: int) -> list[list[Conditions]]:
    """result[h][i] = weather at points[i] at start + h hours, for h in [0, hours]."""
    start = _floor_hour(start)
    queries = [(lat, lon, start + timedelta(hours=h)) for h in range(hours + 1) for lat, lon in points]
    flat = conditions_at(queries)
    n = len(points)
    return [flat[h * n : (h + 1) * n] for h in range(hours + 1)]


# --------------------------------------------------------------------------- cache + fetch


def _cache_key(cell: Cell, day: date) -> str:
    return f"wx:v3:{cell_deg()}:{cell[0]}:{cell[1]}:{day.isoformat()}"


def _load(needed: dict[Cell, set[date]]) -> dict[tuple[Cell, date], DaySeries]:
    wanted = {(cell, day): _cache_key(cell, day) for cell, days in needed.items() for day in days}
    hits = cache.get_many(list(wanted.values()))
    result = {pair: hits[key] for pair, key in wanted.items() if key in hits}

    # Group missing cells by the day range they need so each batch is one homogeneous request.
    missing: dict[tuple[date, date], list[Cell]] = {}
    for cell, days in needed.items():
        gaps = [d for d in days if (cell, d) not in result]
        if gaps:
            missing.setdefault((min(gaps), max(gaps)), []).append(cell)

    jobs = [
        (cells[i : i + BATCH_SIZE], first, last)
        for (first, last), cells in missing.items()
        for i in range(0, len(cells), BATCH_SIZE)
    ]
    if not jobs:
        return result

    log.info("weather: %d cache hits, fetching %d cells in %d batches", len(result), sum(len(j[0]) for j in jobs), len(jobs))
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_BATCHES, len(jobs))) as pool:
        for fetched in pool.map(lambda job: _fetch(*job), jobs):
            cache.set_many({_cache_key(*pair): series for pair, series in fetched.items()}, settings.WEATHER_CACHE_TTL_S)
            result.update(fetched)

    absent = [pair for pair in wanted if pair not in result]
    if absent:
        raise ProviderError("Weather forecast is unavailable for part of this trip (outside the forecast window).")
    return result


def _fetch(cells: list[Cell], first: date, last: date) -> dict[tuple[Cell, date], DaySeries]:
    centers = [cell_center(c) for c in cells]
    params = {
        "latitude": ",".join(f"{lat}" for lat, _ in centers),
        "longitude": ",".join(f"{lon}" for _, lon in centers),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
        "start_date": first.isoformat(),
        "end_date": last.isoformat(),
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    data = get_json(settings.OPEN_METEO_URL, params, service="Weather service")
    locations = data if isinstance(data, list) else [data]
    if len(locations) != len(cells):
        raise ProviderError("Weather service returned an unexpected number of locations.")

    out: dict[tuple[Cell, date], DaySeries] = {}
    for cell, loc in zip(cells, locations):
        for day, series in _parse_location(loc).items():
            out[(cell, day)] = series
    return out


def _parse_location(loc: dict) -> dict[date, DaySeries]:
    hourly, units = loc["hourly"], loc.get("hourly_units", {})
    rain_k = _precip_factor(units.get("rain", "inch"))
    snow_k = _precip_factor(units.get("snowfall", "inch"))
    days: dict[date, DaySeries] = {}
    for i, stamp in enumerate(hourly["time"]):
        t = datetime.fromisoformat(stamp)
        rain = (_num(hourly["rain"][i]) + _num(hourly["showers"][i])) * rain_k
        row = (
            _num(hourly["wind_speed_10m"][i]),
            _num(hourly["wind_gusts_10m"][i]),
            round(rain, 3),
            round(_num(hourly["snowfall"][i]) * snow_k, 3),
            hourly["temperature_2m"][i],
            hourly["weather_code"][i],
        )
        days.setdefault(t.date(), [None] * 24)[t.hour] = row  # type: ignore[index]
    # Only keep complete days so a partial response can never poison the cache.
    return {d: rows for d, rows in days.items() if all(r is not None for r in rows)}


def _precip_factor(unit: str) -> float:
    """Multiplier converting the unit Open-Meteo actually used into inches."""
    unit = unit.lower()
    if unit.startswith("inch") or unit == "in":
        return 1.0
    if unit == "cm":
        return 1 / CM_PER_INCH
    if unit == "mm":
        return 1 / MM_PER_INCH
    raise ProviderError(f"Unexpected precipitation unit from weather service: {unit}")


def _num(v) -> float:
    return 0.0 if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
