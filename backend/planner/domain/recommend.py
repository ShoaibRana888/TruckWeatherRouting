"""Per-route risk metrics and the route recommendation."""

from dataclasses import dataclass

from .risk import RiskLevel


@dataclass(frozen=True)
class RouteMetrics:
    distance_miles: float
    duration_s: float
    miles_by_level: dict[RiskLevel, float]
    avg_risk: float  # distance-weighted risk score, 0 (Low) .. 4 (No Travel)

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[RiskLevel.NO_TRAVEL]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[RiskLevel.SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[RiskLevel.HIGH]

    @property
    def blocked(self) -> bool:
        return self.no_travel_miles > 0


def compute_metrics(
    levels: list[RiskLevel], segment_miles: list[float], distance_miles: float, duration_s: float
) -> RouteMetrics:
    """Each checkpoint's level applies to the miles from it to the next checkpoint."""
    miles_by_level = {level: 0.0 for level in RiskLevel}
    for level, miles in zip(levels, segment_miles):
        miles_by_level[level] += miles

    covered = sum(segment_miles)
    if covered > 0:
        avg = sum(int(level) * miles for level, miles in zip(levels, segment_miles)) / covered
    else:
        avg = sum(int(level) for level in levels) / len(levels) if levels else 0.0

    return RouteMetrics(distance_miles, duration_s, miles_by_level, avg)


# Ranking criteria in priority order: (label, key, formatter). The brief asks for
# fewest Severe miles, fewest High miles, lowest average risk, then shortest time;
# No Travel miles lead because they are strictly worse than Severe.
# Keys are rounded so float noise or sub-mile / sub-minute differences count as ties.
CRITERIA = (
    ("No Travel miles", lambda m: round(m.no_travel_miles, 1), lambda v: f"{v:.1f} mi"),
    ("Severe miles", lambda m: round(m.severe_miles, 1), lambda v: f"{v:.1f} mi"),
    ("High miles", lambda m: round(m.high_miles, 1), lambda v: f"{v:.1f} mi"),
    ("average risk", lambda m: round(m.avg_risk, 2), lambda v: f"{v:.2f}"),
    ("travel time", lambda m: round(m.duration_s / 60), lambda v: _fmt_minutes(v)),
)


def _fmt_minutes(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def rank_key(metrics: RouteMetrics) -> tuple:
    return tuple(key(metrics) for _, key, _ in CRITERIA)


@dataclass(frozen=True)
class Recommendation:
    order: list[int]  # route indexes, best first
    explanation: str
    all_blocked: bool = False


def recommend(metrics: list[RouteMetrics], names: list[str]) -> Recommendation:
    """Rank routes and explain the deciding criterion against the runner-up."""
    order = sorted(range(len(metrics)), key=lambda i: (rank_key(metrics[i]), i))
    best = order[0]
    all_blocked = all(m.blocked for m in metrics)

    if len(metrics) == 1:
        text = f"{names[best]} is the only route available."
    else:
        runner = order[1]
        text = _explain(metrics[best], metrics[runner], names[best], names[runner])

    # The best route is blocked only when every route is.
    if all_blocked:
        miles = metrics[best].no_travel_miles
        if len(metrics) > 1:
            text = f"Every route crosses No Travel conditions; {names[best]} has the least ({miles:.1f} mi). {text}"
        else:
            text = f"{names[best]} crosses {miles:.1f} mi of No Travel conditions. {text}"

    return Recommendation(order, text, all_blocked)


def _explain(best: RouteMetrics, other: RouteMetrics, best_name: str, other_name: str) -> str:
    for label, key, fmt in CRITERIA:
        a, b = key(best), key(other)
        if a != b:
            if label == "No Travel miles" and a == 0:
                return f"{best_name} avoids No Travel conditions ({other_name} has {fmt(b)})."
            if label == "travel time":
                return f"Weather risk is equivalent to {other_name}, and {best_name} is faster ({fmt(a)} vs {fmt(b)})."
            return f"{best_name} has less {label} than {other_name} ({fmt(a)} vs {fmt(b)})."
    return f"{best_name} ties with {other_name} on every criterion; shown first."
