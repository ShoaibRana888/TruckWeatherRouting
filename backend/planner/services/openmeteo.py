"""Open-Meteo hourly forecast client (batched, chunked, cached)."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

import requests
from django.conf import settings
from django.core.cache import cache

from planner.domain.risk import Weather
from planner.domain.sampling import Coord

from .errors import UpstreamError

logger = logging.getLogger(__name__)

FORECAST_DAYS = 5  # 120 hourly values, from 00:00 UTC today
HOURLY_FIELDS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
CHUNK_SIZE = 60
CACHE_TTL_S = 30 * 60
GRID_DEG = 0.05  # snap to ~3.5 mi; finer than the forecast models' own resolution
MAX_WORKERS = 6


@dataclass(frozen=True)
class HourlySeries:
    """Hourly weather for one location. Index 0 is `start` (UTC)."""

    start: datetime
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in_hr: list[float]
    snow_in_hr: list[float]

    def __len__(self) -> int:
        return len(self.wind_mph)

    def at(self, index: int) -> Weather:
        i = min(max(index, 0), len(self) - 1)
        return Weather(self.wind_mph[i], self.rain_in_hr[i], self.snow_in_hr[i], self.gust_mph[i])

    def index_for(self, when: datetime) -> tuple[int, bool]:
        """Nearest forecast hour for a time, and whether it had to be clamped."""
        raw = round((when - self.start).total_seconds() / 3600)
        index = min(max(raw, 0), len(self) - 1)
        return index, index != raw


def snap(coord: Coord) -> Coord:
    lon, lat = coord
    return (round(round(lon / GRID_DEG) * GRID_DEG, 4), round(round(lat / GRID_DEG) * GRID_DEG, 4))


def _cache_key(point: Coord) -> str:
    return f"openmeteo:{point[0]}:{point[1]}"


def _ffill(values: list[float | None]) -> list[float]:
    """Carry the last good value over gaps so a missing hour never reads as calm weather."""
    out, last = [], 0.0
    for v in values:
        last = last if v is None else float(v)
        out.append(last)
    return out


def parse_location(payload: dict) -> HourlySeries:
    hourly = payload["hourly"]
    start = datetime.fromisoformat(hourly["time"][0]).replace(tzinfo=UTC)
    rain = _ffill(hourly["rain"])
    showers = _ffill(hourly["showers"])
    return HourlySeries(
        start=start,
        wind_mph=_ffill(hourly["wind_speed_10m"]),
        gust_mph=_ffill(hourly["wind_gusts_10m"]),
        rain_in_hr=[r + s for r, s in zip(rain, showers)],
        snow_in_hr=_ffill(hourly["snowfall"]),
    )


def _fetch_chunk(points: list[Coord]) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{lat:.4f}" for _, lat in points),
        "longitude": ",".join(f"{lon:.4f}" for lon, _ in points),
        "hourly": HOURLY_FIELDS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "forecast_days": FORECAST_DAYS,
    }
    try:
        resp = requests.get(settings.OPEN_METEO_URL, params=params, timeout=settings.UPSTREAM_TIMEOUT_S)
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        raise UpstreamError("Weather service is unavailable. Please try again shortly.") from exc

    locations = body if isinstance(body, list) else [body]  # one location returns a bare object
    if len(locations) != len(points):
        raise UpstreamError("Weather service returned an unexpected response.")
    try:
        return [parse_location(loc) for loc in locations]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("Weather service returned an unexpected response.") from exc


def fetch_series(points: list[Coord]) -> dict[Coord, HourlySeries]:
    """Hourly forecast for each point, keyed by its snapped coordinate."""
    wanted = list(dict.fromkeys(snap(p) for p in points))
    result: dict[Coord, HourlySeries] = {}
    missing = []
    for p in wanted:
        hit = cache.get(_cache_key(p))
        if hit is not None:
            result[p] = hit
        else:
            missing.append(p)

    chunks = [missing[i : i + CHUNK_SIZE] for i in range(0, len(missing), CHUNK_SIZE)]
    if chunks:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as pool:
            for chunk, series in zip(chunks, pool.map(_fetch_chunk, chunks)):
                for p, s in zip(chunk, series):
                    cache.set(_cache_key(p), s, CACHE_TTL_S)
                    result[p] = s
    return result
