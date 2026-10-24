import pytest

from routing.domain.risk import Conditions, RiskLevel, assess, wind_level

L, M, H, S, N = RiskLevel


@pytest.mark.parametrize(
    "mph, expected",
    [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, N), (80, N)],
)
def test_wind_bands_light_load(mph, expected):
    assert wind_level(mph, load_lbs=10_000) == (expected, False)


@pytest.mark.parametrize(
    "rain, expected",
    [(0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H), (0.50, S), (1.00, S), (1.001, N)],
)
def test_rain_bands(rain, expected):
    assert assess(Conditions(wind_mph=0, rain_in_hr=rain, snow_in_hr=0), 0).rain == expected


@pytest.mark.parametrize(
    "snow, expected",
    [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_bands(snow, expected):
    assert assess(Conditions(wind_mph=0, rain_in_hr=0, snow_in_hr=snow), 0).snow == expected


class TestLoadRules:
    def test_55_mph_is_no_travel_for_any_load(self):
        assert wind_level(55, 0)[0] == N

    def test_45_54_over_30k_is_no_travel(self):
        assert wind_level(45, 30_001) == (N, True)
        assert wind_level(54.9, 45_000) == (N, True)

    def test_45_54_at_exactly_30k_is_not_escalated(self):
        assert wind_level(50, 30_000) == (S, False)

    def test_35_44_over_40k_is_severe(self):
        assert wind_level(35, 40_001) == (S, True)
        assert wind_level(44.9, 80_000) == (S, True)

    def test_35_44_at_exactly_40k_stays_high(self):
        assert wind_level(40, 40_000) == (H, False)

    def test_35_44_between_30k_and_40k_stays_high(self):
        assert wind_level(40, 35_000) == (H, False)

    def test_load_rules_do_not_touch_lower_winds(self):
        assert wind_level(34.9, 80_000) == (M, False)


def test_overall_level_is_worst_condition_and_lists_drivers():
    result = assess(Conditions(wind_mph=30, rain_in_hr=0.3, snow_in_hr=0.2), 0)
    assert result.level == H
    assert result.drivers == ("rain",)


def test_ties_report_every_driver():
    result = assess(Conditions(wind_mph=36, rain_in_hr=0.3, snow_in_hr=0), 0)
    assert result.level == H
    assert result.drivers == ("wind", "rain")


def test_calm_weather_has_no_drivers():
    assert assess(Conditions(0, 0, 0), 80_000).drivers == ()


def test_heavy_load_escalation_is_flagged():
    result = assess(Conditions(wind_mph=40, rain_in_hr=0, snow_in_hr=0), 45_000)
    assert result.level == S and result.load_rule_applied
