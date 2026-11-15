import math

from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import blocking_zone, edge_tangent
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.route import boundary, plan, zone_point
from navigator.domain.policies.steering import (
    SteeringSettings,
    gap,
    path_clearance,
    steer,
)

S = SteeringSettings()
COLS = 15
FOV = 58.0


def scene(columns, valid=None):
    valid = valid or [True] * COLS
    return SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=COLS,
        distances_m=tuple([8.0] * COLS + columns + columns),
        valid=tuple([True] * COLS + valid + valid),
        horizontal_fov_deg=FOV,
    )


def blocked_ahead(distance=2.0, first=6, last=8, far=8.0):
    columns = [far] * COLS
    for col in range(first, last + 1):
        columns[col] = distance
    return columns


def routed(geometry):
    _, committed = steer(geometry, S)
    run = gap(geometry, S, committed) if committed is not None else None
    return plan(geometry, S, run)


def test_open_path_is_one_straight_leg_as_long_as_the_clearance():
    geometry = scene([6.0] * COLS)
    assert routed(geometry) == ((0.0, 0.0), (0.0, path_clearance(geometry, S)))


def test_nothing_within_range_runs_to_the_horizon():
    assert routed(scene([math.inf] * COLS)) == ((0.0, 0.0), (0.0, S.max_m))


def test_route_bends_to_the_side_steering_chose():
    geometry = scene(blocked_ahead())
    phrase, committed = steer(geometry, S)
    waypoints = routed(geometry)
    assert phrase in (PhraseId.VEER_RIGHT, PhraseId.TURN_RIGHT)
    assert committed == 1
    assert waypoints[1][0] > 0
    assert waypoints[1][1] == S.look_m


def test_route_follows_a_committed_left_side():
    geometry = scene(blocked_ahead())
    _, committed = steer(geometry, S, committed=-1)
    waypoints = plan(geometry, S, gap(geometry, S, committed))
    assert committed == -1
    assert waypoints[1][0] < 0


def test_bend_clears_the_blocker_by_half_a_lane_where_the_blocker_stands():
    geometry = scene(blocked_ahead(distance=2.0))
    x_m, z_m = routed(geometry)[1]
    lateral_at_blocker = x_m * 2.0 / z_m
    blocker_edge = 2.0 * edge_tangent(9, COLS, FOV)
    assert lateral_at_blocker - blocker_edge >= S.half_width_m - 0.01


def test_bend_takes_the_smallest_detour_not_the_middle_of_the_gap():
    geometry = scene(blocked_ahead())
    x_m, _ = routed(geometry)[1]
    middle = S.look_m * (edge_tangent(9, COLS, FOV) + edge_tangent(15, COLS, FOV)) / 2
    assert 0 < x_m < middle


def test_second_leg_runs_straight_on_until_the_lane_closes():
    geometry = scene(blocked_ahead(far=6.0))
    waypoints = routed(geometry)
    assert len(waypoints) == 3
    assert waypoints[2][0] == waypoints[1][0]
    assert waypoints[2][1] == 6.0


def test_no_second_leg_when_the_gap_ends_right_after_the_bend():
    geometry = scene(blocked_ahead(far=3.2))
    assert len(routed(geometry)) == 2


def test_blocked_everywhere_stops_the_line_at_the_blocker():
    geometry = scene([2.0] * COLS)
    assert steer(geometry, S) == (None, None)
    assert routed(geometry) == ((0.0, 0.0), (0.0, 2.0))


def test_unknown_centre_column_draws_no_line():
    valid = [True] * COLS
    valid[7] = False
    assert routed(scene([6.0] * COLS, valid)) == ((0.0, 0.0),)


def test_second_leg_stops_where_the_view_is_unknown():
    columns = blocked_ahead()
    valid = [True] * COLS
    valid[9] = False
    columns[9] = 1.0
    geometry = scene(columns, valid)
    waypoints = plan(geometry, S, (10, 14))
    x_m = waypoints[1][0]
    entered_unknown = x_m / edge_tangent(10, COLS, FOV)
    assert waypoints[-1][1] < entered_unknown + 0.25
    assert waypoints[-1][1] < 8.0


def test_boundary_draws_each_column_as_a_wedge():
    points = boundary(scene(blocked_ahead()), S)
    assert len(points) == 2 * COLS
    assert points[0] == (round(8.0 * edge_tangent(0, COLS, FOV), 2), 8.0)
    assert points[14][1] == points[15][1] == 2.0
    assert points[14][0] < 0 < points[15][0]


def test_boundary_collapses_an_unknown_column():
    valid = [True] * COLS
    valid[3] = False
    points = boundary(scene([6.0] * COLS, valid), S)
    assert points[6] == points[7] == (0.0, 0.0)


def test_blocking_zone_names_the_nearest_zone_in_the_lane():
    geometry = scene(blocked_ahead(distance=2.0))
    distance, row, col = blocking_zone(geometry, S.half_width_m)
    assert (distance, row) == (2.0, 1)
    assert col == 7
    assert zone_point(geometry, col, distance) == (0.0, 2.0)


def test_blocking_zone_ignores_what_stands_beside_the_lane():
    columns = [8.0] * COLS
    columns[0] = 1.0
    geometry = scene(columns)
    assert blocking_zone(geometry, S.half_width_m)[0] == 8.0


def test_gap_too_tight_for_a_lane_draws_only_a_short_pointer():
    columns = [1.25] * 13 + [8.0, 8.0]
    geometry = scene(columns)
    phrase, committed = steer(geometry, S)
    waypoints = routed(geometry)
    assert phrase is PhraseId.TURN_RIGHT
    assert len(waypoints) == 2
    x_m, z_m = waypoints[1]
    assert x_m > 0
    assert 0.5 <= z_m <= 1.25 - S.half_width_m


def test_pointer_never_shrinks_below_half_a_metre():
    geometry = scene([0.6] * 13 + [8.0, 8.0])
    assert routed(geometry)[1][1] == 0.5


def test_coarse_grid_route_stops_short_of_the_columns_beside_the_gap():
    geometry = SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=5,
        distances_m=(8.0,) * 5 + (2.5, 2.5, 2.5, 6.0, 2.5) * 2,
        valid=(True,) * 15,
        horizontal_fov_deg=70.0,
    )
    waypoints = routed(geometry)
    assert len(waypoints) == 2
    assert waypoints[1][0] > 0
    assert waypoints[1][1] <= 2.5 - S.half_width_m


def test_lane_aimed_with_exactly_half_a_lane_of_margin_reaches_the_look_distance():
    for distance in (1.1, 1.54, 1.9, 2.3, 2.7):
        for col in (6, 7, 8):
            columns = [4.0] * COLS
            columns[col] = distance
            waypoints = routed(scene(columns))
            assert waypoints[1][1] == S.look_m, (distance, col)
