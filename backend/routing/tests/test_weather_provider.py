from datetime import date, datetime, timedelta, timezone

import pytest
from django.core.cache import cache

from routing.providers import weather
from routing.providers.http import ProviderError


def fake_location(first: date, last: date, rain_unit="inch", snow_unit="inch"):
    """Hourly series where every value encodes its hour index, so lookups are easy to assert."""
    times, n = [], (last - first).days * 24 + 24
    start = datetime(first.year, first.month, first.day)
    for i in range(n):
        times.append((start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M"))
    return {
        "hourly_units": {"rain": rain_unit, "snowfall": snow_unit},
        "hourly": {
            "time": times,
            "wind_speed_10m": [float(i) for i in range(n)],
            "wind_gusts_10m": [float(i) + 10 for i in range(n)],
            "rain": [i / 100 for i in range(n)],
            "showers": [0.0] * n,
            "snowfall": [None] * n,
            "temperature_2m": [50.0] * n,
            "weather_code": [0] * n,
        },
    }


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def fake_api(monkeypatch):
    calls = []

    def fake_get_json(url, params, service, **_):
        calls.append(params)
        first, last = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        locs = [fake_location(first, last) for _ in params["latitude"].split(",")]
        return locs if len(locs) > 1 else locs[0]

    monkeypatch.setattr(weather, "get_json", fake_get_json)
    return calls


def test_instant_values_use_nearest_hour_and_precip_uses_the_hour_being_driven(fake_api):
    when = datetime(2026, 3, 1, 13, 20, tzinfo=timezone.utc)
    [c] = weather.conditions_at([(40.0, -100.0, when)])
    assert c.wind_mph == 13  # 13:00 value (nearest hour)
    assert c.rain_in_hr == pytest.approx(0.14)  # 14:00 value = total over 13:00–14:00
    assert c.snow_in_hr == 0  # nulls become 0


def test_nearest_hour_rounds_up_after_half_past(fake_api):
    [c] = weather.conditions_at([(40.0, -100.0, datetime(2026, 3, 1, 13, 40, tzinfo=timezone.utc))])
    assert c.wind_mph == 14


def test_precip_lookup_crosses_midnight(fake_api):
    [c] = weather.conditions_at([(40.0, -100.0, datetime(2026, 3, 1, 23, 10, tzinfo=timezone.utc))])
    assert c.rain_in_hr == pytest.approx(0.24)  # 00:00 of the next day = index 24 in the fake series


def test_points_in_same_cell_share_one_fetch_and_cache_is_reused(fake_api):
    when = datetime(2026, 3, 1, 10, tzinfo=timezone.utc)
    weather.conditions_at([(40.01, -100.01, when), (40.02, -100.02, when)])
    assert len(fake_api) == 1 and fake_api[0]["latitude"] == "40.0"
    weather.conditions_at([(40.03, -100.03, when)])
    assert len(fake_api) == 1  # served from cache


def test_many_cells_are_batched(fake_api):
    when = datetime(2026, 3, 1, 10, tzinfo=timezone.utc)
    weather.conditions_at([(30 + i * weather.cell_deg(), -100.0, when) for i in range(250)])
    assert sorted(len(c["latitude"].split(",")) for c in fake_api) == [50, 100, 100]


def test_metric_units_are_converted_to_inches():
    loc = fake_location(date(2026, 3, 1), date(2026, 3, 1), rain_unit="mm", snow_unit="cm")
    loc["hourly"]["rain"] = [25.4] * 24
    loc["hourly"]["snowfall"] = [2.54] * 24
    row = weather._parse_location(loc)[date(2026, 3, 1)][0]
    assert row[2] == pytest.approx(1.0) and row[3] == pytest.approx(1.0)


def test_missing_days_raise_provider_error(monkeypatch):
    monkeypatch.setattr(weather, "get_json", lambda *a, **k: fake_location(date(2020, 1, 1), date(2020, 1, 1)))
    with pytest.raises(ProviderError):
        weather.conditions_at([(40.0, -100.0, datetime(2026, 3, 1, 10, tzinfo=timezone.utc))])


def test_hourly_grid_shape(fake_api):
    grid = weather.hourly_grid([(40.0, -100.0), (41.0, -101.0)], datetime(2026, 3, 1, 6, 45, tzinfo=timezone.utc), 48)
    assert len(grid) == 49 and all(len(row) == 2 for row in grid)
    assert grid[0][0].wind_mph == 6 and grid[48][1].wind_mph == 54
