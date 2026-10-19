"""Use cases: turn a trip request into scored routes and a forecast heatmap.

Orchestrates the services (Mapbox, Open-Meteo) and the pure domain layer, and
shapes the JSON the frontend renders.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .domain.recommend import RouteMetrics, compute_metrics, recommend
from .domain.risk import RiskAssessment, RiskLevel, assess
from .domain.sampling import (
    Checkpoint,
    Coord,
    RouteProfile,
    bearing_degrees,
    offset_point,
    sample_checkpoints,
    simplify,
)
from .services import mapbox, openmeteo

DISPLAY_TOLERANCE_DEG = 0.0004  # ~40 m; display geometry only, sampling uses the full polyline
HEATMAP_HOURS = 49  # forecast hours 0..48 from now
HEATMAP_ALONG_MILES = 30.0
HEATMAP_LATERAL_MILES = (-20.0, 0.0, 20.0)
HEATMAP_MAX_POINTS = 450
ROUTE_NAMES = "ABC"


@dataclass
class ScoredCheckpoint:
    checkpoint: Checkpoint
    assessment: RiskAssessment
    weather: dict
    forecast_clamped: bool


def _profile(route: mapbox.DirectionsRoute) -> RouteProfile:
    return RouteProfile(route.coords, route.seg_distances_m, route.seg_durations_s, route.duration_s)


def _score(
    checkpoints: list[Checkpoint], series_by_point: dict[Coord, openmeteo.HourlySeries], load_lb: float
) -> list[ScoredCheckpoint]:
    scored = []
    for cp in checkpoints:
        series = series_by_point[openmeteo.snap((cp.lon, cp.lat))]
        index, clamped = series.index_for(cp.eta)
        wx = series.at(index)
        scored.append(
            ScoredCheckpoint(
                cp,
                assess(wx, load_lb),
                {
                    "wind_mph": round(wx.wind_mph, 1),
                    "gust_mph": round(wx.gust_mph or 0.0, 1),
                    "rain_in_hr": round(wx.rain_in_hr, 2),
                    "snow_in_hr": round(wx.snow_in_hr, 2),
                },
                clamped,
            )
        )
    return scored


def _segments(profile: RouteProfile, scored: list[ScoredCheckpoint]) -> list[dict]:
    """Display polyline split into runs of equal risk level."""
    runs: list[dict] = []
    for s in scored[:-1]:
        cp = s.checkpoint
        piece = profile.slice(cp.mile, cp.mile + cp.segment_miles)
        level = int(s.assessment.level)
        if runs and runs[-1]["level"] == level:
            runs[-1]["coordinates"].extend(piece[1:])
        else:
            runs.append({"level": level, "coordinates": list(piece)})
    return [
        {
            "level": run["level"],
            "coordinates": [
                [round(lon, 5), round(lat, 5)] for lon, lat in simplify(run["coordinates"], DISPLAY_TOLERANCE_DEG)
            ],
        }
        for run in runs
    ]


def _checkpoint_json(s: ScoredCheckpoint) -> dict:
    cp = s.checkpoint
    return {
        "index": cp.index,
        "lon": round(cp.lon, 5),
        "lat": round(cp.lat, 5),
        "mile": round(cp.mile, 1),
        "eta": cp.eta.isoformat(),
        "level": int(s.assessment.level),
        "level_label": s.assessment.level.label,
        "weather": s.weather,
        "reasons": s.assessment.reasons,
        "forecast_clamped": s.forecast_clamped,
    }


def _metrics_json(m: RouteMetrics) -> dict:
    return {
        "miles_by_level": {int(level): round(miles, 1) for level, miles in m.miles_by_level.items()},
        "avg_risk": round(m.avg_risk, 2),
    }


def plan_trip(origin: Coord, destination: Coord, departure: datetime, load_lb: float, interval_miles: int) -> dict:
    routes = mapbox.get_routes(origin, destination)
    profiles = [_profile(r) for r in routes]
    checkpoints = [sample_checkpoints(p, interval_miles, departure) for p in profiles]

    series = openmeteo.fetch_series([(cp.lon, cp.lat) for cps in checkpoints for cp in cps])
    scored = [_score(cps, series, load_lb) for cps in checkpoints]

    names = [f"Route {ROUTE_NAMES[i]}" for i in range(len(routes))]
    metrics = [
        compute_metrics(
            [s.assessment.level for s in sc],
            [s.checkpoint.segment_miles for s in sc],
            profile.total_miles,
            profile.total_seconds,
        )
        for sc, profile in zip(scored, profiles)
    ]
    rec = recommend(metrics, names)
    rank_of = {route_idx: rank + 1 for rank, route_idx in enumerate(rec.order)}

    out_routes = []
    for i, (route, profile, sc, m) in enumerate(zip(routes, profiles, scored, metrics)):
        out_routes.append(
            {
                "id": ROUTE_NAMES[i],
                "name": names[i],
                "summary": route.summary,
                "rank": rank_of[i],
                "recommended": i == rec.order[0],
                "blocked": m.blocked,
                "distance_miles": round(profile.total_miles, 1),
                "duration_s": round(profile.total_seconds),
                "arrival_time": (departure + timedelta(seconds=profile.total_seconds)).isoformat(),
                "metrics": _metrics_json(m),
                "segments": _segments(profile, sc),
                "checkpoints": [_checkpoint_json(s) for s in sc],
            }
        )

    return {
        "departure_time": departure.isoformat(),
        "interval_miles": interval_miles,
        "load_weight_lb": load_lb,
        "recommended_route_id": ROUTE_NAMES[rec.order[0]],
        "recommendation": {"explanation": rec.explanation, "all_blocked": rec.all_blocked},
        "routes": out_routes,
    }


def _corridor_points(profiles: list[RouteProfile]) -> list[Coord]:
    """Grid of points along every route plus lateral offsets, thinned to a point budget."""
    interval = HEATMAP_ALONG_MILES
    while True:
        seen: dict[Coord, Coord] = {}
        for profile in profiles:
            samples = sample_checkpoints(profile, interval, datetime(2000, 1, 1, tzinfo=UTC))
            for i, cp in enumerate(samples):
                here = (cp.lon, cp.lat)
                if i + 1 < len(samples):
                    bearing = bearing_degrees(here, (samples[i + 1].lon, samples[i + 1].lat))
                else:
                    bearing = bearing_degrees((samples[i - 1].lon, samples[i - 1].lat), here) if i else 0.0
                for offset in HEATMAP_LATERAL_MILES:
                    point = (
                        here if offset == 0 else offset_point(here, bearing + (90 if offset > 0 else -90), abs(offset))
                    )
                    seen.setdefault(openmeteo.snap(point), point)
        if len(seen) <= HEATMAP_MAX_POINTS:
            return list(seen.values())
        interval *= 1.5


def build_heatmap(origin: Coord, destination: Coord, load_lb: float, now: datetime | None = None) -> dict:
    """Risk score (0-4) per corridor point for each of the next 49 forecast hours.

    All hours ship in one payload as properties r0..r48 so the frontend slider
    never has to refetch while it is dragged.
    """
    routes = mapbox.get_routes(origin, destination)
    points = _corridor_points([_profile(r) for r in routes])
    series = openmeteo.fetch_series(points)

    now = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    features = []
    for point in points:
        s = series[openmeteo.snap(point)]
        props = {}
        for h in range(HEATMAP_HOURS):
            index, _ = s.index_for(now + timedelta(hours=h))
            props[f"r{h}"] = int(assess(s.at(index), load_lb).level)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(point[0], 4), round(point[1], 4)]},
                "properties": props,
            }
        )

    return {
        "start": now.isoformat(),
        "hours": HEATMAP_HOURS,
        "max_level": int(RiskLevel.NO_TRAVEL),
        "points": {"type": "FeatureCollection", "features": features},
    }
