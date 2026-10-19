"""Shared fixtures: synthetic Mapbox and Open-Meteo APIs served through `responses`."""

import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.core.cache import cache

from planner.domain.sampling import METERS_PER_MILE, haversine_miles

ORIGIN = {"lon": -97.0, "lat": 32.8}
DESTINATION = {"lon": -94.0, "lat": 32.8}
NORTH_WIND_LAT = 33.5  # synthetic storm: everything north of this latitude has 60 mph wind


def make_route(bulge_lat: float, n: int = 120, speed_mph: float = 60.0) -> dict:
    """A Mapbox-style route from ORIGIN to DESTINATION bulging to `bulge_lat` mid-way."""
    coords = []
    for i in range(n):
        f = i / (n - 1)
        lat = (
            ORIGIN["lat"] + (bulge_lat - ORIGIN["lat"]) * (1 - abs(2 * f - 1)) ** 0.5
            if bulge_lat != ORIGIN["lat"]
            else ORIGIN["lat"]
        )
        coords.append([ORIGIN["lon"] + (DESTINATION["lon"] - ORIGIN["lon"]) * f, lat])
    dist_m = [haversine_miles(coords[i], coords[i + 1]) * METERS_PER_MILE for i in range(n - 1)]
    dur_s = [d / METERS_PER_MILE / speed_mph * 3600 for d in dist_m]
    return {
        "distance": sum(dist_m),
        "duration": sum(dur_s),
        "geometry": {"type": "LineString", "coordinates": coords},
        "legs": [{"summary": f"via {bulge_lat}", "annotation": {"distance": dist_m, "duration": dur_s}}],
    }


def _directions_callback(routes_by_query):
    def callback(request):
        qs = parse_qs(urlparse(request.url).query)
        exclude = qs.get("exclude", [None])[0]
        return 200, {}, json.dumps({"code": "Ok", "routes": routes_by_query(exclude)})

    return callback


def _weather_callback(request):
    qs = parse_qs(urlparse(request.url).query)
    lats = [float(x) for x in qs["latitude"][0].split(",")]
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(120)]
    locations = []
    for lat in lats:
        wind = 60.0 if lat > NORTH_WIND_LAT else 10.0
        locations.append(
            {
                "hourly": {
                    "time": times,
                    "wind_speed_10m": [wind] * 120,
                    "wind_gusts_10m": [wind + 8] * 120,
                    "rain": [0.0] * 120,
                    "showers": [0.0] * 120,
                    "snowfall": [0.0] * 120,
                }
            }
        )
    body = locations if len(locations) > 1 else locations[0]
    return 200, {}, json.dumps(body)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def mock_apis():
    """Mapbox returns 3 routes (south, mid, north-bulging); the northern one hits the storm."""
    all_routes = [make_route(32.8), make_route(33.2), make_route(34.0, speed_mph=70)]
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add_callback(
            responses.GET,
            re.compile(r"https://api\.mapbox\.com/directions/v5/mapbox/driving/.*"),
            callback=_directions_callback(lambda exclude: all_routes),
        )
        rsps.add_callback(
            responses.GET, re.compile(r"https://api\.open-meteo\.com/v1/forecast.*"), callback=_weather_callback
        )
        rsps.routes = all_routes
        yield rsps


@pytest.fixture
def plan_body():
    return {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "departure_time": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
        "load_weight_lb": 20_000,
        "interval_miles": 25,
    }
