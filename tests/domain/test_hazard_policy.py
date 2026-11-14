import math

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing, HazardLevel
from navigator.domain.policies.hazard import (
    AlertState,
    HazardThresholds,
    announce,
    evaluate,
)


def geometry(distances, valid=None, rows=3, cols=5):
    if valid is None:
        valid = (True,) * (rows * cols)
    return SceneGeometry(
        frame_id=1,
        t_capture_ns=1_000,
        rows=rows,
        cols=cols,
        distances_m=tuple(distances),
        valid=tuple(valid),
        horizontal_fov_deg=70.0,
    )


def corridor(distance, col, far=5.0):
    distances = [far] * 15
    for row in range(3):
        distances[row * 5 + col] = distance
    return geometry(distances)


def test_clear_scene_no_alert():
    assert evaluate(geometry([10.0] * 15), HazardThresholds()) is None


def test_wall_at_caution_distance():
    g = geometry([2.5, 3.0, 1.5, 3.0, 2.5] * 3)
    alert = evaluate(g, HazardThresholds())
    assert alert is not None
    assert alert.level is HazardLevel.CAUTION
    assert alert.bearing is Bearing.AHEAD
    assert alert.distance_m == 1.5


def test_wall_below_stop_distance():
    alert = evaluate(geometry([1.0] * 15), HazardThresholds())
    assert alert is not None
    assert alert.level is HazardLevel.STOP


def test_stop_boundary_uses_strict_less_than():
    alert = evaluate(corridor(1.2, 2), HazardThresholds())
    assert alert is not None
    assert alert.level is HazardLevel.CAUTION
    alert = evaluate(corridor(1.19, 2), HazardThresholds())
    assert alert.level is HazardLevel.STOP


def test_caution_boundary_uses_strict_less_than():
    assert evaluate(corridor(2.0, 2), HazardThresholds()) is None
    alert = evaluate(corridor(1.99, 2), HazardThresholds())
    assert alert is not None
    assert alert.level is HazardLevel.CAUTION


def test_wall_beside_the_path_is_ignored():
    distances = [1.5, 5.0, 5.0, 5.0, 1.5] * 3
    assert evaluate(geometry(distances), HazardThresholds()) is None


def test_far_column_counts_once_it_reaches_the_path():
    alert = evaluate(corridor(0.5, 0), HazardThresholds())
    assert alert.level is HazardLevel.STOP
    assert alert.bearing is Bearing.LEFT


def test_wider_path_catches_more():
    assert evaluate(corridor(1.5, 0), HazardThresholds(half_width_m=0.7)) is not None


def test_bearing_per_column():
    assert evaluate(corridor(1.0, 1), HazardThresholds()).bearing is Bearing.LEFT
    assert evaluate(corridor(1.0, 2), HazardThresholds()).bearing is Bearing.AHEAD
    assert evaluate(corridor(1.0, 3), HazardThresholds()).bearing is Bearing.RIGHT


def test_all_rows_count():
    for row in range(3):
        distances = [5.0] * 15
        distances[row * 5 + 2] = 1.0
        alert = evaluate(geometry(distances), HazardThresholds())
        assert alert is not None
        assert alert.level is HazardLevel.STOP


def test_inf_distances_no_alert():
    assert (
        evaluate(
            geometry([math.inf] * 15), HazardThresholds()
        )
        is None
    )


def test_invalid_zones_ignored():
    distances = [0.4] * 15
    valid = [True] * 15
    for i in range(15):
        valid[i] = False
    g = geometry(distances, valid=valid)
    assert evaluate(g, HazardThresholds()) is None


def test_invalid_zone_does_not_shadow_valid():
    distances = [5.0] * 15
    valid = [True] * 15
    distances[6] = 0.4
    valid[6] = False
    distances[7] = 1.6
    alert = evaluate(geometry(distances, valid=valid), HazardThresholds())
    assert alert.distance_m == 1.6
    assert alert.bearing is Bearing.AHEAD


def test_tie_prefers_central_column():
    alert = evaluate(geometry([1.0] * 15), HazardThresholds())
    assert alert.bearing is Bearing.AHEAD


def test_provenance_carried():
    alert = evaluate(geometry([1.0] * 15), HazardThresholds())
    assert alert.frame_id == 1
    assert alert.t_capture_ns == 1_000


def _walk(distances, thresholds=None):
    thresholds = thresholds or HazardThresholds()
    state, spoken = AlertState(), []
    for d in distances:
        state, speak = announce(state, evaluate(corridor(d, 2), thresholds), thresholds)
        spoken.append(speak)
    return spoken


def test_single_frame_flicker_is_not_announced():
    assert _walk([5.0, 1.0, 5.0, 5.0]) == [False] * 4


def test_alert_announced_once_while_it_holds():
    assert _walk([1.5] * 6) == [False, True, False, False, False, False]


def test_escalation_announced():
    assert _walk([1.5, 1.5, 1.0, 1.0, 1.0]) == [False, True, False, True, False]


def test_stop_repeats_only_when_still_closing():
    spoken = _walk([1.1, 1.1, 1.05, 1.0, 0.95, 0.75, 0.75])
    assert spoken == [False, True, False, False, False, True, False]


def test_new_approach_after_clearing_is_announced():
    spoken = _walk([1.5, 1.5, 5.0, 5.0, 1.5, 1.5])
    assert spoken == [False, True, False, False, False, True]


def test_backing_off_is_silent_then_approach_again_speaks():
    spoken = _walk([1.0, 1.0, 1.5, 1.5, 1.0, 1.0])
    assert spoken == [False, True, False, False, False, True]


def test_bearing_change_announced():
    thresholds = HazardThresholds()
    state = AlertState()
    spoken = []
    for col in (1, 1, 3, 3):
        alert = evaluate(corridor(1.5, col), thresholds)
        state, speak = announce(state, alert, thresholds)
        spoken.append(speak)
    assert spoken == [False, True, False, True]


def test_stop_does_not_repeat_when_only_the_side_flickers():
    thresholds = HazardThresholds()
    state = AlertState()
    spoken = []
    for col in (2, 2, 1, 3, 2, 1):
        state, speak = announce(state, evaluate(corridor(1.0, col), thresholds), thresholds)
        spoken.append(speak)
    assert spoken == [False, True, False, False, False, False]


def test_swaying_at_a_wall_after_stop_stays_quiet():
    thresholds = HazardThresholds()
    state = AlertState()
    spoken = []
    for distance, col in [(1.0, 2), (1.0, 2), (1.4, 1), (1.4, 1), (1.4, 3), (1.4, 3), (1.4, 1), (1.4, 1)]:
        state, speak = announce(state, evaluate(corridor(distance, col), thresholds), thresholds)
        spoken.append(speak)
    assert spoken == [False, True] + [False] * 6
