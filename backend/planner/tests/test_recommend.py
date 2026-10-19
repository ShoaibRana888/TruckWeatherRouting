import pytest

from planner.domain.recommend import compute_metrics, recommend
from planner.domain.risk import RiskLevel as L


def metrics(levels, miles, duration_min=600):
    return compute_metrics(levels, miles, sum(miles), duration_min * 60)


def test_miles_by_level_and_weighted_average():
    m = metrics([L.LOW, L.HIGH, L.SEVERE], [10, 20, 10])
    assert m.miles_by_level[L.HIGH] == 20
    assert m.avg_risk == pytest.approx((0 * 10 + 2 * 20 + 3 * 10) / 40)


def test_average_falls_back_when_no_distance():
    m = metrics([L.LOW, L.SEVERE], [0, 0])
    assert m.avg_risk == pytest.approx(1.5)


def test_fewest_severe_miles_wins_even_if_slower():
    safe_slow = metrics([L.HIGH, L.HIGH], [50, 50], 900)
    fast_severe = metrics([L.LOW, L.SEVERE], [50, 50], 500)
    rec = recommend([fast_severe, safe_slow], ["Route A", "Route B"])
    assert rec.order == [1, 0]
    assert "Severe" in rec.explanation


def test_fewest_high_miles_breaks_severe_tie():
    a = metrics([L.HIGH, L.LOW], [50, 50])
    b = metrics([L.MODERATE, L.MODERATE], [50, 50])
    assert recommend([a, b], ["A", "B"]).order == [1, 0]


def test_lowest_average_risk_breaks_high_tie():
    a = metrics([L.MODERATE, L.MODERATE], [50, 50])
    b = metrics([L.LOW, L.MODERATE], [50, 50])
    assert recommend([a, b], ["A", "B"]).order == [1, 0]


def test_shortest_time_breaks_full_tie():
    a = metrics([L.LOW, L.LOW], [50, 50], 700)
    b = metrics([L.LOW, L.LOW], [50, 50], 650)
    rec = recommend([a, b], ["A", "B"])
    assert rec.order == [1, 0]
    assert "faster" in rec.explanation


def test_sub_minute_differences_are_ties_falling_back_to_original_order():
    a = metrics([L.LOW], [100], 600)
    b = metrics([L.LOW], [100], 600.4)
    assert recommend([a, b], ["A", "B"]).order == [0, 1]


def test_no_travel_route_loses_to_one_that_avoids_it():
    blocked = metrics([L.NO_TRAVEL, L.LOW], [10, 90], 500)
    clear = metrics([L.SEVERE, L.SEVERE], [50, 50], 800)
    rec = recommend([blocked, clear], ["A", "B"])
    assert rec.order == [1, 0] and not rec.all_blocked
    assert "avoids No Travel" in rec.explanation


def test_all_blocked_is_flagged_and_least_exposure_wins():
    a = metrics([L.NO_TRAVEL, L.LOW], [60, 40])
    b = metrics([L.NO_TRAVEL, L.LOW], [20, 80])
    rec = recommend([a, b], ["A", "B"])
    assert rec.order == [1, 0] and rec.all_blocked
    assert rec.explanation.startswith("Every route crosses No Travel")


def test_single_route():
    rec = recommend([metrics([L.LOW], [10])], ["Route A"])
    assert rec.order == [0] and "only route" in rec.explanation
