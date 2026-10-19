"""Route geometry helpers: cumulative distance/time profile and checkpoint sampling."""

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344

Coord = tuple[float, float]  # (lon, lat)


def haversine_miles(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class Checkpoint:
    index: int
    lon: float
    lat: float
    mile: float
    elapsed_s: float
    eta: datetime
    segment_miles: float  # miles from this checkpoint to the next (0 for the last one)


class RouteProfile:
    """A route polyline with cumulative miles and seconds at every vertex."""

    def __init__(
        self,
        coords: list[Coord],
        seg_distances_m: list[float] | None,
        seg_durations_s: list[float] | None,
        total_duration_s: float,
    ):
        if len(coords) < 2:
            raise ValueError("A route needs at least two coordinates")
        self.coords = coords
        n_segments = len(coords) - 1

        if seg_distances_m is not None and len(seg_distances_m) == n_segments:
            miles = [d / METERS_PER_MILE for d in seg_distances_m]
        else:
            miles = [haversine_miles(coords[i], coords[i + 1]) for i in range(n_segments)]
        total_miles = sum(miles)

        if seg_durations_s is not None and len(seg_durations_s) == n_segments:
            seconds = list(seg_durations_s)
        else:
            # No per-segment timing: spread the route duration proportionally to distance.
            seconds = [total_duration_s * (m / total_miles) if total_miles else 0.0 for m in miles]

        self.cum_miles = [0.0]
        self.cum_seconds = [0.0]
        for m, s in zip(miles, seconds):
            self.cum_miles.append(self.cum_miles[-1] + m)
            self.cum_seconds.append(self.cum_seconds[-1] + s)

    @property
    def total_miles(self) -> float:
        return self.cum_miles[-1]

    @property
    def total_seconds(self) -> float:
        return self.cum_seconds[-1]

    def _locate(self, mile: float) -> tuple[int, float]:
        """Return (segment index, fraction along that segment) for a mile marker."""
        mile = min(max(mile, 0.0), self.total_miles)
        i = min(bisect_right(self.cum_miles, mile) - 1, len(self.coords) - 2)
        span = self.cum_miles[i + 1] - self.cum_miles[i]
        frac = (mile - self.cum_miles[i]) / span if span > 0 else 0.0
        return i, frac

    def position_at(self, mile: float) -> tuple[Coord, float]:
        """Interpolated (coordinate, elapsed seconds) at a mile marker."""
        i, f = self._locate(mile)
        (lon1, lat1), (lon2, lat2) = self.coords[i], self.coords[i + 1]
        coord = (lon1 + (lon2 - lon1) * f, lat1 + (lat2 - lat1) * f)
        seconds = self.cum_seconds[i] + (self.cum_seconds[i + 1] - self.cum_seconds[i]) * f
        return coord, seconds

    def slice(self, start_mile: float, end_mile: float) -> list[Coord]:
        """Polyline between two mile markers, with interpolated end points."""
        start, _ = self.position_at(start_mile)
        end, _ = self.position_at(end_mile)
        i0, _ = self._locate(start_mile)
        i1, _ = self._locate(end_mile)
        return [start, *self.coords[i0 + 1 : i1 + 1], end]


def sample_checkpoints(profile: RouteProfile, interval_miles: float, departure: datetime) -> list[Checkpoint]:
    """Checkpoints every `interval_miles`, always including the origin and destination."""
    if interval_miles <= 0:
        raise ValueError("interval_miles must be positive")

    total = profile.total_miles
    miles = [0.0]
    step = 1
    while step * interval_miles < total - 1e-6:
        miles.append(step * interval_miles)
        step += 1
    if total > 0:
        miles.append(total)

    checkpoints = []
    for idx, mile in enumerate(miles):
        (lon, lat), elapsed = profile.position_at(mile)
        next_mile = miles[idx + 1] if idx + 1 < len(miles) else mile
        checkpoints.append(
            Checkpoint(
                index=idx,
                lon=lon,
                lat=lat,
                mile=mile,
                elapsed_s=elapsed,
                eta=departure + timedelta(seconds=elapsed),
                segment_miles=next_mile - mile,
            )
        )
    return checkpoints


def offset_point(coord: Coord, bearing_deg: float, miles: float) -> Coord:
    """Point `miles` away from `coord` along a great-circle bearing."""
    lon, lat = map(math.radians, coord)
    brg = math.radians(bearing_deg)
    d = miles / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat) * math.cos(d) + math.cos(lat) * math.sin(d) * math.cos(brg))
    lon2 = lon + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat), math.cos(d) - math.sin(lat) * math.sin(lat2))
    return (math.degrees(lon2), math.degrees(lat2))


def bearing_degrees(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def simplify(coords: list[Coord], tolerance_deg: float) -> list[Coord]:
    """Ramer–Douglas–Peucker (iterative) for display geometry."""
    n = len(coords)
    if n <= 2:
        return list(coords)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        (x1, y1), (x2, y2) = coords[lo], coords[hi]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        worst, worst_i = 0.0, -1
        for i in range(lo + 1, hi):
            px, py = coords[i]
            if norm == 0:
                dist = math.hypot(px - x1, py - y1)
            else:
                dist = abs(dy * (px - x1) - dx * (py - y1)) / norm
            if dist > worst:
                worst, worst_i = dist, i
        if worst > tolerance_deg:
            keep[worst_i] = True
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return [c for c, k in zip(coords, keep) if k]
