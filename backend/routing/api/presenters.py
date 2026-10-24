"""Domain objects → JSON. Geometry leaves the backend in GeoJSON [lon, lat] order."""
from __future__ import annotations

from datetime import timedelta
from itertools import groupby

from ..domain.geo import LatLon, simplify_indices, slice_polyline
from ..domain.risk import RiskLevel
from ..services.heatmap import Heatmap
from ..services.planner import AssessedCheckpoint, PlannedRoute, TripPlan


def _lonlat(p: LatLon) -> list[float]:
    return [round(p[1], 5), round(p[0], 5)]


def _place(place) -> dict:
    return {"label": place.label, "lat": place.lat, "lon": place.lon}


def present_plan(plan: TripPlan) -> dict:
    req, rec = plan.request, plan.recommendation
    rank = {route_id: i + 1 for i, route_id in enumerate(rec.ranking)}
    return {
        "origin": _place(req.origin),
        "destination": _place(req.destination),
        "departure": req.departure.isoformat(),
        "load_weight_lbs": req.load_lbs,
        "interval_miles": req.interval_mi,
        "recommendation": {
            "route_id": rec.route_id,
            "ranking": rec.ranking,
            "decided_by": rec.decided_by,
            "reason": rec.reason,
            "advisories": rec.advisories,
        },
        "routes": [_present_route(r, req.departure, rank[r.id], r.id == rec.route_id) for r in plan.routes],
    }


def _present_route(planned: PlannedRoute, departure, rank: int, recommended: bool) -> dict:
    route, exposure = planned.route, planned.exposure
    # Simplify for transport, keeping per-vertex time so the UI can animate the truck exactly.
    tolerance = min(0.15, max(0.02, route.distance_mi / 10_000))
    kept = simplify_indices(route.coords, tolerance)
    coords = [route.coords[i] for i in kept]
    cum_mi = [route.cum_miles[i] for i in kept]

    return {
        "id": planned.id,
        "name": planned.name,
        "via": route.via,
        "rank": rank,
        "recommended": recommended,
        "summary": {
            "distance_mi": round(route.distance_mi, 1),
            "duration_s": round(route.duration_s),
            "arrival": (departure + timedelta(seconds=route.duration_s)).isoformat(),
            "miles_by_level": {lvl.name.lower(): round(m, 1) for lvl, m in exposure.miles_by_level.items()},
            "avg_risk": round(exposure.avg_risk, 2),
            "max_level": int(max(cp.risk.level for cp in planned.checkpoints)),
            "checkpoint_count": len(planned.checkpoints),
        },
        "geometry": {"type": "LineString", "coordinates": [_lonlat(p) for p in coords]},
        "timeline_s": [round(route.cum_seconds[i]) for i in kept],
        "segments": _risk_segments(planned.checkpoints, coords, cum_mi),
        "checkpoints": [_present_checkpoint(c) for c in planned.checkpoints],
        "label_point": _lonlat(planned.label_point),
    }


def _risk_segments(checkpoints: list[AssessedCheckpoint], coords, cum_mi) -> list[dict]:
    """Consecutive checkpoints sharing a level are merged into one coloured stretch of road."""
    stretches = []
    for level, group in groupby(checkpoints, key=lambda c: c.risk.level):
        group = list(group)
        start, end = group[0].checkpoint.covers_from_mi, group[-1].checkpoint.covers_to_mi
        if end - start <= 0:
            continue
        stretches.append(
            {
                "level": int(level),
                "from_mi": round(start, 2),
                "to_mi": round(end, 2),
                "coordinates": [_lonlat(p) for p in slice_polyline(coords, cum_mi, start, end)],
            }
        )
    return stretches


def _present_checkpoint(a: AssessedCheckpoint) -> dict:
    cp, wx = a.checkpoint, a.conditions
    return {
        "index": cp.index,
        "mile": round(cp.mile, 1),
        "lat": round(cp.lat, 5),
        "lon": round(cp.lon, 5),
        "eta": cp.eta.isoformat(),
        "covers_mi": [round(cp.covers_from_mi, 2), round(cp.covers_to_mi, 2)],
        "weather": {
            "wind_mph": round(wx.wind_mph, 1),
            "gust_mph": round(wx.gust_mph, 1),
            "rain_in_hr": round(wx.rain_in_hr, 3),
            "snow_in_hr": round(wx.snow_in_hr, 3),
            "temperature_f": None if wx.temperature_f is None else round(wx.temperature_f),
            "weather_code": wx.weather_code,
        },
        "risk": a.risk.as_dict(),
    }


def present_heatmap(h: Heatmap) -> dict:
    return {
        "start": h.start.isoformat(),
        "hours": h.hours,
        "step_deg": h.step_deg,
        "points": [_lonlat(p) for p in h.points],
        "risk": h.risk,
        "wind_mph": h.wind_mph,
        "rain_in_hr": h.rain_in_hr,
        "snow_in_hr": h.snow_in_hr,
        "levels": [lvl.label for lvl in RiskLevel],
    }
