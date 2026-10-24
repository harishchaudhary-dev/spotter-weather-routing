"""Request validation. Responses are shaped in presenters.py."""
from datetime import timedelta, timezone

from django.conf import settings
from django.utils import timezone as dj_timezone
from rest_framework import serializers

from ..domain.sampling import ALLOWED_INTERVALS_MI
from ..providers import geocoding
from ..providers.geocoding import Place

MAX_LOAD_LBS = 100_000
DEPARTURE_GRACE = timedelta(hours=1)


class LocationField(serializers.Field):
    """Accepts a picked suggestion {label, lat, lon} or free text that is geocoded server-side."""

    default_error_messages = {"invalid": "Enter a place name or pick a suggestion."}

    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data.strip():
                self.fail("invalid")
            return geocoding.resolve(data)
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                self.fail("invalid")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self.fail("invalid")
            return Place(label=str(data.get("label") or f"{lat:.4f}, {lon:.4f}"), lat=lat, lon=lon)
        self.fail("invalid")

    def to_representation(self, value):
        return {"label": value.label, "lat": value.lat, "lon": value.lon}


class DepartureMixin(serializers.Serializer):
    departure = serializers.DateTimeField()

    def validate_departure(self, value):
        if dj_timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        now = dj_timezone.now()
        if value < now - DEPARTURE_GRACE:
            raise serializers.ValidationError("Departure can't be in the past.")
        if value > now + timedelta(days=settings.MAX_DEPARTURE_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within {settings.MAX_DEPARTURE_DAYS_AHEAD} days so the trip stays inside the forecast window."
            )
        return value


class PlanRequestSerializer(DepartureMixin):
    origin = LocationField()
    destination = LocationField()
    load_weight_lbs = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LBS)
    interval_miles = serializers.ChoiceField(choices=ALLOWED_INTERVALS_MI, default=25)


MAX_CORRIDOR_POINTS = 6000


class HeatmapRequestSerializer(DepartureMixin):
    corridor = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
            min_length=2,
        ),
        min_length=1,
        max_length=5,
        help_text="One line per route, each a list of [lon, lat] pairs (GeoJSON MultiLineString order).",
    )
    load_weight_lbs = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LBS)
    hours = serializers.IntegerField(min_value=1, max_value=48, default=48)

    def validate_corridor(self, value):
        if sum(len(line) for line in value) > MAX_CORRIDOR_POINTS:
            raise serializers.ValidationError(f"Corridor is limited to {MAX_CORRIDOR_POINTS} points.")
        lines = []
        for line in value:
            points = []
            for lon, lat in line:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise serializers.ValidationError("Corridor contains an invalid coordinate.")
                points.append((lat, lon))
            lines.append(points)
        return lines
