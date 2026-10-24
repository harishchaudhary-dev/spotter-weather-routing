import pytest

from routing.domain.recommendation import recommend, summarize_exposure
from routing.domain.risk import RiskLevel

L, M, H, S, N = RiskLevel


def exposure(route_id, hours, **miles):
    levels = {"low": L, "moderate": M, "high": H, "severe": S, "no_travel": N}
    segments = [(levels[k], v) for k, v in miles.items()]
    return summarize_exposure(route_id, segments, duration_s=hours * 3600)


def test_summary_weights_risk_by_distance():
    e = exposure("a", 1, low=75, severe=25)
    assert e.miles(S) == 25
    assert e.avg_risk == pytest.approx(0.75)


def test_fewest_severe_miles_wins_over_speed():
    rec = recommend([exposure("fast", 10, low=500, severe=20), exposure("slow", 12, low=520, high=100)])
    assert rec.route_id == "slow"
    assert rec.decided_by == "severe_mi"
    assert "20.0 mi" in rec.reason


def test_high_miles_break_severe_tie():
    rec = recommend([exposure("a", 10, low=400, high=50), exposure("b", 11, low=430, high=20)])
    assert (rec.route_id, rec.decided_by) == ("b", "high_mi")


def test_average_risk_breaks_severe_and_high_tie():
    rec = recommend([exposure("a", 10, low=100, moderate=300), exposure("b", 11, low=300, moderate=100)])
    assert (rec.route_id, rec.decided_by) == ("b", "avg_risk")
    assert rec.reason.startswith("Tied on Severe miles, High miles.")


def test_travel_time_is_the_last_tiebreaker():
    rec = recommend([exposure("slow", 12, low=500), exposure("fast", 9, low=500)])
    assert (rec.route_id, rec.decided_by) == ("fast", "duration")
    assert rec.ranking == ["fast", "slow"]


def test_no_travel_outranks_severe():
    rec = recommend([exposure("blocked", 8, low=490, no_travel=10), exposure("rough", 9, low=400, severe=100)])
    assert rec.route_id == "rough"
    assert rec.decided_by == "no_travel_mi"
    assert rec.advisories  # still severe on the chosen route


def test_advisory_when_every_route_is_blocked():
    rec = recommend([exposure("a", 8, low=90, no_travel=10), exposure("b", 9, low=95, no_travel=5)])
    assert rec.route_id == "b"
    assert "No Travel" in rec.advisories[0]


def test_floating_point_noise_does_not_decide():
    a = exposure("a", 10, low=100.00001, severe=5.000001)
    b = exposure("b", 9, low=100.0, severe=5.0)
    assert recommend([a, b]).route_id == "b"


def test_single_route():
    rec = recommend([exposure("only", 3, low=10)])
    assert rec.route_id == "only" and rec.decided_by is None
