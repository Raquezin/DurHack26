import math

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing, HazardLevel
from navigator.domain.policies.hazard import HazardThresholds, evaluate


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


def test_corridor_only_ignores_far_columns():
    distances = [0.5, 5.0, 5.0, 5.0, 0.5] * 3
    assert evaluate(geometry(distances), HazardThresholds()) is None


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
    for row in range(3):
        for col in range(1, 4):
            valid[row * 5 + col] = False
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
