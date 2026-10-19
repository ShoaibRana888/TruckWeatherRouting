import json
import re
from datetime import UTC, datetime, timedelta

import pytest
import requests
import responses
from rest_framework.test import APIClient

from .conftest import _directions_callback, make_route

client = APIClient()


def post(path, body):
    return client.post(path, json.dumps(body), content_type="application/json")


def test_plan_returns_three_scored_routes_and_recommends_the_storm_free_one(mock_apis, plan_body):
    resp = post("/api/plan/", plan_body)
    assert resp.status_code == 200, resp.content
    data = resp.json()

    assert [r["id"] for r in data["routes"]] == ["A", "B", "C"]
    assert data["recommended_route_id"] == "A"
    by_id = {r["id"]: r for r in data["routes"]}
    assert by_id["A"]["recommended"] and by_id["A"]["rank"] == 1
    assert not by_id["A"]["blocked"]
    # Route C bulges into the 60 mph region: it must be blocked and ranked last.
    assert by_id["C"]["blocked"] and by_id["C"]["rank"] == 3
    assert by_id["C"]["metrics"]["miles_by_level"]["4"] > 0
    # A and B tie on risk (both storm-free), so the explanation falls through to travel time.
    assert "Route A is faster" in data["recommendation"]["explanation"]


def test_plan_checkpoints_have_etas_weather_and_endpoints(mock_apis, plan_body):
    route = post("/api/plan/", plan_body).json()["routes"][0]
    cps = route["checkpoints"]
    assert cps[0]["mile"] == 0 and cps[-1]["mile"] == pytest.approx(route["distance_miles"], abs=0.1)
    assert all(a["mile"] < b["mile"] for a, b in zip(cps, cps[1:]))
    etas = [datetime.fromisoformat(c["eta"]) for c in cps]
    assert etas == sorted(etas)
    assert etas[0] == datetime.fromisoformat(plan_body["departure_time"])
    assert cps[0]["weather"]["wind_mph"] == 10.0 and cps[0]["level_label"] == "Low"
    assert route["segments"] and all(len(s["coordinates"]) >= 2 for s in route["segments"])


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_interval_controls_checkpoint_spacing(mock_apis, plan_body, interval):
    plan_body["interval_miles"] = interval
    route = post("/api/plan/", plan_body).json()["routes"][0]
    miles = [c["mile"] for c in route["checkpoints"]]
    assert miles[1] - miles[0] == pytest.approx(interval, abs=0.1)


def test_heavy_load_escalates_risk_in_moderate_wind(mock_apis, plan_body):
    # Re-point the weather at 40 mph everywhere: heavy loads become Severe, light ones High.
    mock_apis.remove(responses.GET, re.compile(r"https://api\.open-meteo\.com/v1/forecast.*"))
    from .conftest import _weather_callback

    def forty_mph(request):
        status, headers, body = _weather_callback(request)
        parsed = json.loads(body)
        for loc in parsed if isinstance(parsed, list) else [parsed]:
            loc["hourly"]["wind_speed_10m"] = [40.0] * 120
        return status, headers, json.dumps(parsed)

    mock_apis.add_callback(responses.GET, re.compile(r"https://api\.open-meteo\.com/v1/forecast.*"), callback=forty_mph)
    light = post("/api/plan/", {**plan_body, "load_weight_lb": 20_000}).json()["routes"][0]
    assert light["metrics"]["miles_by_level"]["2"] > 0 and light["metrics"]["miles_by_level"]["3"] == 0
    from django.core.cache import cache

    cache.clear()
    heavy = post("/api/plan/", {**plan_body, "load_weight_lb": 45_000}).json()["routes"][0]
    assert heavy["metrics"]["miles_by_level"]["3"] > 0


def test_fewer_than_three_routes_triggers_fallback_queries(plan_body):
    primary = [make_route(32.8)]
    distinct = make_route(33.2)
    duplicate = make_route(32.8)

    def routes_for(exclude):
        return primary if exclude is None else [duplicate, distinct] if exclude == "toll" else [duplicate]

    from .conftest import _weather_callback

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add_callback(
            responses.GET,
            re.compile(r"https://api\.mapbox\.com/directions/.*"),
            callback=_directions_callback(routes_for),
        )
        rsps.add_callback(responses.GET, re.compile(r"https://api\.open-meteo\.com/.*"), callback=_weather_callback)
        data = post("/api/plan/", plan_body).json()
    # Duplicate of the primary route is discarded; the distinct one is kept.
    assert [r["id"] for r in data["routes"]] == ["A", "B"]


def test_heatmap_has_49_hours_per_point(mock_apis, plan_body):
    resp = post("/api/heatmap/", {k: plan_body[k] for k in ("origin", "destination", "load_weight_lb")})
    assert resp.status_code == 200, resp.content
    data = resp.json()
    feats = data["points"]["features"]
    assert data["hours"] == 49 and len(feats) > 10
    assert all(f"r{h}" in feats[0]["properties"] for h in range(49))
    levels = {p for f in feats for p in f["properties"].values()}
    assert levels == {0, 4}  # calm south, 60 mph north in the synthetic storm


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"interval_miles": 15}, "interval_miles"),
        ({"load_weight_lb": 90_000}, "load_weight_lb"),
        ({"load_weight_lb": -1}, "load_weight_lb"),
        ({"departure_time": "2020-01-01T00:00:00Z"}, "departure_time"),
        ({"departure_time": (datetime.now(UTC) + timedelta(days=10)).isoformat()}, "departure_time"),
        ({"destination": {"lon": -97.0, "lat": 32.8}}, "non_field_errors"),
        ({"origin": {"lon": 500, "lat": 0}}, "origin"),
    ],
)
def test_plan_validation(mock_apis, plan_body, patch, message):
    resp = post("/api/plan/", {**plan_body, **patch})
    assert resp.status_code == 400
    assert message in resp.json()


def test_mapbox_failure_becomes_502(plan_body):
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, re.compile(r"https://api\.mapbox\.com/directions/.*"), body=requests.ConnectionError())
        resp = post("/api/plan/", plan_body)
    assert resp.status_code == 502 and "unavailable" in resp.json()["detail"]


def test_no_route_becomes_404(plan_body):
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            re.compile(r"https://api\.mapbox\.com/directions/.*"),
            json={"code": "NoRoute", "routes": []},
        )
        resp = post("/api/plan/", plan_body)
    assert resp.status_code == 404


def test_weather_failure_becomes_502(plan_body):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add_callback(
            responses.GET,
            re.compile(r"https://api\.mapbox\.com/directions/.*"),
            callback=_directions_callback(lambda _: [make_route(32.8), make_route(33.2), make_route(34.0)]),
        )
        rsps.add(responses.GET, re.compile(r"https://api\.open-meteo\.com/.*"), status=500)
        resp = post("/api/plan/", plan_body)
    assert resp.status_code == 502 and "Weather" in resp.json()["detail"]


def test_geocode_proxy(monkeypatch):
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            re.compile(r"https://api\.mapbox\.com/search/geocode/v6/forward.*"),
            json={
                "features": [
                    {
                        "geometry": {"coordinates": [-96.79, 32.77]},
                        "properties": {"full_address": "Dallas, Texas, United States"},
                    }
                ]
            },
        )
        resp = client.get("/api/geocode/", {"q": "dallas"})
    assert resp.json()["results"] == [{"name": "Dallas, Texas, United States", "lon": -96.79, "lat": 32.77}]


def test_geocode_short_query_skips_upstream():
    assert client.get("/api/geocode/", {"q": "d"}).json() == {"results": []}


def test_config_exposes_only_public_tokens(settings):
    settings.MAPBOX_TOKEN = "pk.public-token"
    assert client.get("/api/config/").json()["mapbox_token"] == "pk.public-token"
    settings.MAPBOX_TOKEN = "sk.secret-token"
    assert client.get("/api/config/").json()["mapbox_token"] == ""
