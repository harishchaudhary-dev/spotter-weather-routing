"""Weather risk classification — a direct encoding of the assessment's risk and load tables.

Boundary interpretation (the table gives ranges like "25–34" for continuous measurements):
  * Each band's lower bound is inclusive, so 25.0 mph is Moderate and 34.9 mph is still Moderate.
  * Wind No Travel is "≥55 mph" (inclusive); rain/snow No Travel is strictly "> 1.00" / "> 3.0",
    so exactly 1.00 in/hr of rain is Severe.
  * Load rules escalate the *wind* level only, and never lower it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class Band:
    """Lower bounds for Moderate/High/Severe plus the No Travel threshold for one condition."""

    moderate: float
    high: float
    severe: float
    no_travel: float
    no_travel_inclusive: bool

    def classify(self, value: float) -> RiskLevel:
        if value > self.no_travel or (self.no_travel_inclusive and value >= self.no_travel):
            return RiskLevel.NO_TRAVEL
        if value >= self.severe:
            return RiskLevel.SEVERE
        if value >= self.high:
            return RiskLevel.HIGH
        if value >= self.moderate:
            return RiskLevel.MODERATE
        return RiskLevel.LOW


WIND_MPH = Band(moderate=25, high=35, severe=45, no_travel=55, no_travel_inclusive=True)
RAIN_IN_HR = Band(moderate=0.10, high=0.25, severe=0.50, no_travel=1.00, no_travel_inclusive=False)
SNOW_IN_HR = Band(moderate=0.5, high=1.0, severe=2.0, no_travel=3.0, no_travel_inclusive=False)

# Load rules: (wind lower bound inclusive, upper bound exclusive, load strictly above, resulting level)
LOAD_RULES: tuple[tuple[float, float, float, RiskLevel], ...] = (
    (45, 55, 30_000, RiskLevel.NO_TRAVEL),
    (35, 45, 40_000, RiskLevel.SEVERE),
)


@dataclass(frozen=True)
class Conditions:
    """Weather at one place and hour, in the units the risk table uses."""

    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float
    gust_mph: float = 0.0
    temperature_f: float | None = None
    weather_code: int | None = None


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    load_rule_applied: bool = False
    drivers: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        return {
            "level": int(self.level),
            "label": self.level.label,
            "by_condition": {"wind": int(self.wind), "rain": int(self.rain), "snow": int(self.snow)},
            "load_rule_applied": self.load_rule_applied,
            "drivers": list(self.drivers),
        }


def wind_level(wind_mph: float, load_lbs: float) -> tuple[RiskLevel, bool]:
    """Wind level after load rules. Returns (level, whether a load rule raised it)."""
    base = WIND_MPH.classify(wind_mph)
    for lower, upper, load_over, escalated in LOAD_RULES:
        if lower <= wind_mph < upper and load_lbs > load_over and escalated > base:
            return escalated, True
    return base, False


def assess(conditions: Conditions, load_lbs: float) -> RiskAssessment:
    """Overall level is the worst of wind (load-adjusted), rain and snow."""
    wind, load_applied = wind_level(conditions.wind_mph, load_lbs)
    rain = RAIN_IN_HR.classify(conditions.rain_in_hr)
    snow = SNOW_IN_HR.classify(conditions.snow_in_hr)
    level = max(wind, rain, snow)
    drivers = tuple(
        name for name, lvl in (("wind", wind), ("rain", rain), ("snow", snow)) if lvl == level and level > RiskLevel.LOW
    )
    return RiskAssessment(level=level, wind=wind, rain=rain, snow=snow, load_rule_applied=load_applied, drivers=drivers)
