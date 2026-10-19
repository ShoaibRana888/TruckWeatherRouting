from datetime import UTC, datetime, timedelta

import pytest

from planner.domain.sampling import (
    METERS_PER_MILE,
    RouteProfile,
    haversine_miles,
    offset_point,
    sample_checkpoints,
    simplify,
)

DEPART = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)


def straight_route(miles=100.0, hours=2.0, n=101):
    """Due-east route along the equator-ish with uniform speed."""
    coords = [(i * 0.0145, 0.0) for i in range(n)]  # ~1 mi per 0.0145 deg lon at equator
    seg_m = [haversine_miles(coords[i], coords[i + 1]) * METERS_PER_MILE for i in range(n - 1)]
    seg_s = [hours * 3600 / (n - 1)] * (n - 1)
    return RouteProfile(coords, seg_m, seg_s, hours * 3600)


def test_haversine_known_distance():
    # Dallas -> Houston is about 225 miles great-circle.
    assert haversine_miles((-96.797, 32.777), (-95.370, 29.760)) == pytest.approx(225, abs=5)


def test_checkpoints_include_origin_and_destination():
    route = straight_route()
    cps = sample_checkpoints(route, 25, DEPART)
    miles = [round(c.mile) for c in cps]
    assert miles[0] == 0 and miles[-1] == round(route.total_miles)
    assert miles[:4] == [0, 25, 50, 75]


def test_destination_not_duplicated_when_total_is_a_multiple():
    route = straight_route()
    miles = [c.mile for c in sample_checkpoints(route, route.total_miles / 4, DEPART)]
    assert len(miles) == 5


def test_eta_uses_cumulative_duration():
    route = straight_route(hours=2.0)
    cps = sample_checkpoints(route, 25, DEPART)
    # 2h over ~100 mi => the 50 mi checkpoint is ~1h in.
    mid = next(c for c in cps if round(c.mile) == 50)
    assert mid.eta - DEPART == timedelta(hours=1) or abs((mid.eta - DEPART).total_seconds() - 3600) < 60


def test_eta_respects_nonuniform_speed():
    coords = [(0.0, 0.0), (0.145, 0.0), (0.29, 0.0)]  # two ~10 mi segments
    seg_m = [haversine_miles(coords[0], coords[1]) * METERS_PER_MILE] * 2
    route = RouteProfile(coords, seg_m, [600, 3000], 3600)  # fast then slow
    cps = sample_checkpoints(route, route.total_miles / 2, DEPART)
    assert (cps[1].eta - DEPART).total_seconds() == pytest.approx(600, abs=1)


def test_segment_miles_sum_to_total():
    route = straight_route()
    cps = sample_checkpoints(route, 10, DEPART)
    assert sum(c.segment_miles for c in cps) == pytest.approx(route.total_miles)
    assert cps[-1].segment_miles == 0


def test_short_route_has_two_checkpoints():
    route = straight_route(miles=8, hours=0.2, n=9)
    cps = sample_checkpoints(route, 50, DEPART)
    assert len(cps) == 2 and cps[0].segment_miles == pytest.approx(route.total_miles)


def test_missing_annotations_fall_back_to_proportional_time():
    coords = [(0.0, 0.0), (0.145, 0.0), (0.29, 0.0)]
    route = RouteProfile(coords, None, None, 7200)
    assert route.total_seconds == pytest.approx(7200)
    assert route.cum_seconds[1] == pytest.approx(3600)


def test_slice_endpoints_match_positions():
    route = straight_route()
    piece = route.slice(10, 20)
    assert piece[0] == route.position_at(10)[0] and piece[-1] == route.position_at(20)[0]
    assert len(piece) >= 2


def test_offset_point_distance():
    p = offset_point((-96.0, 35.0), 90, 15)
    assert haversine_miles((-96.0, 35.0), p) == pytest.approx(15, abs=0.05)


def test_simplify_drops_collinear_points_and_keeps_corners():
    line = [(0, 0), (1, 0.00001), (2, 0), (3, 5), (4, 0)]
    out = simplify(line, 0.001)
    assert (3, 5) in out and (1, 0.00001) not in out
    assert out[0] == (0, 0) and out[-1] == (4, 0)
