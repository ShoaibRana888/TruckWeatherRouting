import pytest

from planner.domain.risk import RiskLevel as L
from planner.domain.risk import Weather, assess


def wx(wind=0.0, rain=0.0, snow=0.0):
    return Weather(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow)


@pytest.mark.parametrize(
    "wind, expected",
    [(0, L.LOW), (24.9, L.LOW), (25, L.MODERATE), (34.5, L.MODERATE), (35, L.HIGH),
     (44.9, L.HIGH), (45, L.SEVERE), (54.9, L.SEVERE), (55, L.NO_TRAVEL), (80, L.NO_TRAVEL)],
)
def test_wind_bands_light_load(wind, expected):
    assert assess(wx(wind=wind), load_lb=10_000).level == expected


@pytest.mark.parametrize(
    "rain, expected",
    [(0.09, L.LOW), (0.10, L.MODERATE), (0.25, L.HIGH), (0.49, L.HIGH),
     (0.50, L.SEVERE), (1.00, L.SEVERE), (1.01, L.NO_TRAVEL)],
)
def test_rain_bands(rain, expected):
    assert assess(wx(rain=rain), load_lb=10_000).level == expected


@pytest.mark.parametrize(
    "snow, expected",
    [(0.4, L.LOW), (0.5, L.MODERATE), (1.0, L.HIGH), (2.0, L.SEVERE), (3.0, L.SEVERE), (3.1, L.NO_TRAVEL)],
)
def test_snow_bands(snow, expected):
    assert assess(wx(snow=snow), load_lb=10_000).level == expected


def test_overall_level_is_worst_condition():
    result = assess(wx(wind=26, rain=0.3, snow=0.1), load_lb=10_000)
    assert result.level == L.HIGH
    assert (result.wind_level, result.rain_level, result.snow_level) == (L.MODERATE, L.HIGH, L.LOW)


def test_wind_55_is_no_travel_for_any_load():
    assert assess(wx(wind=55), load_lb=0).level == L.NO_TRAVEL


@pytest.mark.parametrize(
    "load, expected",
    [(30_000, L.SEVERE), (30_001, L.NO_TRAVEL), (60_000, L.NO_TRAVEL)],
)
def test_wind_45_to_54_heavy_load_is_no_travel(load, expected):
    assert assess(wx(wind=50), load_lb=load).level == expected


@pytest.mark.parametrize(
    "load, expected",
    [(40_000, L.HIGH), (40_001, L.SEVERE)],
)
def test_wind_35_to_44_over_40k_is_severe(load, expected):
    assert assess(wx(wind=40), load_lb=load).level == expected


def test_load_rule_never_downgrades():
    # Heavy rain alone is No Travel; the 35-44 mph load rule must not lower it.
    assert assess(wx(wind=40, rain=2.0), load_lb=45_000).level == L.NO_TRAVEL


def test_reasons_mention_load_rule():
    result = assess(wx(wind=50), load_lb=35_000)
    assert any("Load 35,000 lb" in r for r in result.reasons)


def test_clear_weather_has_no_reasons():
    result = assess(wx(wind=5), load_lb=50_000)
    assert result.level == L.LOW and result.reasons == []
