"""Weather risk classification for a single checkpoint.

Pure functions only: no I/O, no Django. Thresholds come straight from the
assessment brief; the boundary conventions are documented next to them.
"""

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


# Load rule limits (lb).
WIND_NO_TRAVEL_MPH = 55
WIND_SEVERE_MPH = 45
WIND_HIGH_MPH = 35
HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_LB = 40_000


@dataclass(frozen=True)
class Thresholds:
    """Lower bounds for Moderate, High, Severe, No Travel.

    Bands are lower-bound inclusive, so 25 mph is Moderate and 35 mph is High,
    which also closes the gaps in the brief's table (34.5 mph is Moderate).
    The brief writes No Travel as ">1.00" / ">3.0" for rain and snow but
    "≥55" for wind, so `no_travel_inclusive` records which one applies.
    """

    moderate: float
    high: float
    severe: float
    no_travel: float
    no_travel_inclusive: bool

    def classify(self, value: float) -> RiskLevel:
        if value > self.no_travel or (self.no_travel_inclusive and value == self.no_travel):
            return RiskLevel.NO_TRAVEL
        if value >= self.severe:
            return RiskLevel.SEVERE
        if value >= self.high:
            return RiskLevel.HIGH
        if value >= self.moderate:
            return RiskLevel.MODERATE
        return RiskLevel.LOW


WIND_MPH = Thresholds(25, 35, 45, 55, no_travel_inclusive=True)
RAIN_IN_PER_HR = Thresholds(0.10, 0.25, 0.50, 1.00, no_travel_inclusive=False)
SNOW_IN_PER_HR = Thresholds(0.5, 1.0, 2.0, 3.0, no_travel_inclusive=False)


@dataclass(frozen=True)
class Weather:
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float
    gust_mph: float | None = None


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind_level: RiskLevel
    rain_level: RiskLevel
    snow_level: RiskLevel
    reasons: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return int(self.level)


def assess(weather: Weather, load_lb: float) -> RiskAssessment:
    """Classify one checkpoint: worst of wind/rain/snow, then the load rules."""
    wind_level = WIND_MPH.classify(weather.wind_mph)
    rain_level = RAIN_IN_PER_HR.classify(weather.rain_in_hr)
    snow_level = SNOW_IN_PER_HR.classify(weather.snow_in_hr)
    level = max(wind_level, rain_level, snow_level)

    reasons = []
    for name, value, unit, cond_level in (
        ("Wind", weather.wind_mph, "mph", wind_level),
        ("Rain", weather.rain_in_hr, "in/hr", rain_level),
        ("Snow", weather.snow_in_hr, "in/hr", snow_level),
    ):
        if cond_level >= RiskLevel.MODERATE:
            reasons.append(f"{name} {value:g} {unit}: {cond_level.label}")

    wind = weather.wind_mph
    if WIND_SEVERE_MPH <= wind < WIND_NO_TRAVEL_MPH and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        level = RiskLevel.NO_TRAVEL
        reasons.append(
            f"Load {load_lb:,.0f} lb exceeds {HEAVY_LOAD_NO_TRAVEL_LB:,} lb in "
            f"{WIND_SEVERE_MPH}–{WIND_NO_TRAVEL_MPH - 1} mph wind: No Travel"
        )
    elif WIND_HIGH_MPH <= wind < WIND_SEVERE_MPH and load_lb > HEAVY_LOAD_SEVERE_LB:
        level = max(level, RiskLevel.SEVERE)
        reasons.append(
            f"Load {load_lb:,.0f} lb exceeds {HEAVY_LOAD_SEVERE_LB:,} lb in "
            f"{WIND_HIGH_MPH}–{WIND_SEVERE_MPH - 1} mph wind: Severe"
        )

    return RiskAssessment(level, wind_level, rain_level, snow_level, reasons)
