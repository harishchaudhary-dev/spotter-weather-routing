"""Place search via Photon (OSM-based, keyless, built for type-ahead — unlike public Nominatim,
whose usage policy forbids autocomplete)."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache

from .http import NotFoundError, get_json

CACHE_TTL_S = 24 * 60 * 60


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


def search(query: str, limit: int = 6) -> list[Place]:
    query = " ".join(query.split())
    if len(query) < 2:
        return []
    key = f"geo:v1:{limit}:{hashlib.sha1(query.lower().encode()).hexdigest()}"
    cached = cache.get(key)
    if cached is not None:
        return [Place(**p) for p in cached]

    data = get_json(
        f"{settings.PHOTON_URL}/api/",
        {"q": query, "limit": limit, "lang": "en"},
        service="Geocoder",
    )
    places = _dedupe(_to_place(f) for f in data.get("features", []))
    cache.set(key, [asdict(p) for p in places], CACHE_TTL_S)
    return places


def resolve(query: str) -> Place:
    results = search(query, limit=1)
    if not results:
        raise NotFoundError(f'Could not find "{query}". Try a city and state, e.g. "Denver, CO".')
    return results[0]


def _to_place(feature: dict) -> Place:
    props = feature.get("properties", {})
    lon, lat = feature["geometry"]["coordinates"]
    parts = [props.get("name"), props.get("city"), props.get("state"), props.get("country")]
    label = ", ".join(dict.fromkeys(p for p in parts if p))  # ordered de-dup ("Denver, Denver, CO")
    return Place(label=label or f"{lat:.4f}, {lon:.4f}", lat=float(lat), lon=float(lon))


def _dedupe(places) -> list[Place]:
    seen, out = set(), []
    for p in places:
        if p.label not in seen:
            seen.add(p.label)
            out.append(p)
    return out
