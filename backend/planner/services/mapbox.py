"""Mapbox geocoding and directions client."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from planner.domain.sampling import Coord

from .errors import NotFoundError, UpstreamError

logger = logging.getLogger(__name__)

GEOCODE_PATH = "/search/geocode/v6/forward"
DIRECTIONS_PATH = "/directions/v5/mapbox/driving/{coords}"
WANTED_ROUTES = 3
DIRECTIONS_CACHE_TTL_S = 15 * 60
DUPLICATE_OVERLAP = 0.9  # a route sharing this much of its path with another is the same route
# Extra queries used only when the plain alternatives request returns fewer than 3 routes.
FALLBACK_EXCLUDES = ("toll", "motorway", "toll,motorway")


@dataclass(frozen=True)
class Place:
    name: str
    lon: float
    lat: float


@dataclass(frozen=True)
class DirectionsRoute:
    coords: list[Coord]
    seg_distances_m: list[float] | None
    seg_durations_s: list[float] | None
    distance_m: float
    duration_s: float
    summary: str


def _get(url: str, params: dict) -> dict:
    if not settings.MAPBOX_TOKEN:
        raise UpstreamError("Mapbox is not configured on the server (MAPBOX_TOKEN is missing).")
    try:
        resp = requests.get(
            url, params={**params, "access_token": settings.MAPBOX_TOKEN}, timeout=settings.UPSTREAM_TIMEOUT_S
        )
    except requests.RequestException as exc:
        logger.warning("Mapbox request failed: %s", exc)
        raise UpstreamError("Routing service is unavailable. Please try again shortly.") from exc

    if resp.status_code == 422 or (resp.status_code == 200 and not resp.content):
        return {}
    if resp.status_code in (401, 403):
        raise UpstreamError("Mapbox rejected the server's access token.")
    if resp.status_code == 429:
        raise UpstreamError("Routing service rate limit reached. Please try again in a minute.")
    try:
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Mapbox bad response (%s): %s", resp.status_code, resp.text[:200])
        raise UpstreamError("Routing service returned an unexpected response.") from exc


def geocode(query: str, limit: int = 5) -> list[Place]:
    body = _get(
        settings.MAPBOX_API_URL + GEOCODE_PATH,
        {"q": query, "limit": limit, "autocomplete": "true", "country": "us", "language": "en"},
    )
    places = []
    for feature in body.get("features", []):
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"]
        name = props.get("full_address") or props.get("name_preferred") or props.get("name") or query
        places.append(Place(name=name, lon=lon, lat=lat))
    return places


def _parse_route(raw: dict) -> DirectionsRoute:
    coords = [tuple(c) for c in raw["geometry"]["coordinates"]]
    dists: list[float] = []
    durs: list[float] = []
    for leg in raw.get("legs", []):
        ann = leg.get("annotation") or {}
        dists += ann.get("distance", [])
        durs += ann.get("duration", [])
    summary = ", ".join(leg["summary"] for leg in raw.get("legs", []) if leg.get("summary"))
    return DirectionsRoute(coords, dists or None, durs or None, raw["distance"], raw["duration"], summary)


def _directions_request(origin: Coord, dest: Coord, exclude: str | None = None) -> list[DirectionsRoute]:
    params = {
        "alternatives": "true",
        "geometries": "geojson",
        "overview": "full",
        "annotations": "distance,duration",
        "steps": "false",
    }
    if exclude:
        params["exclude"] = exclude
    coords = f"{origin[0]:.6f},{origin[1]:.6f};{dest[0]:.6f},{dest[1]:.6f}"
    body = _get(settings.MAPBOX_API_URL + DIRECTIONS_PATH.format(coords=coords), params)
    try:
        return [_parse_route(r) for r in body.get("routes", [])]
    except (KeyError, TypeError) as exc:
        raise UpstreamError("Routing service returned an unexpected response.") from exc


def _fallback_request(origin: Coord, dest: Coord, exclude: str) -> list[DirectionsRoute]:
    """Best-effort extra routes: a failure here must not sink the routes we already have."""
    try:
        return _directions_request(origin, dest, exclude)
    except UpstreamError:
        logger.info("Fallback directions (exclude=%s) failed; continuing without it", exclude)
        return []


def _cells(route: DirectionsRoute) -> set[tuple[float, float]]:
    # ~100 m grid cells; routes on the same road share identical coordinates.
    return {(round(lon, 3), round(lat, 3)) for lon, lat in route.coords}


def is_duplicate(candidate: DirectionsRoute, existing: list[DirectionsRoute]) -> bool:
    cand = _cells(candidate)
    return any(len(cand & _cells(r)) / len(cand) >= DUPLICATE_OVERLAP for r in existing)


def get_routes(origin: Coord, dest: Coord) -> list[DirectionsRoute]:
    """Up to 3 distinct driving routes, fastest first. Cached briefly per origin/destination."""
    key = f"directions:{origin[0]:.4f}:{origin[1]:.4f}:{dest[0]:.4f}:{dest[1]:.4f}"
    if (cached := cache.get(key)) is not None:
        return cached

    routes = _directions_request(origin, dest)
    if not routes:
        raise NotFoundError("No drivable route was found between those locations.")

    if len(routes) < WANTED_ROUTES:
        with ThreadPoolExecutor(max_workers=len(FALLBACK_EXCLUDES)) as pool:
            extras = list(pool.map(lambda ex: _fallback_request(origin, dest, ex), FALLBACK_EXCLUDES))
        for candidate in (r for batch in extras for r in batch):
            if len(routes) >= WANTED_ROUTES:
                break
            if not is_duplicate(candidate, routes):
                routes.append(candidate)

    routes = routes[:WANTED_ROUTES]
    cache.set(key, routes, DIRECTIONS_CACHE_TTL_S)
    return routes
