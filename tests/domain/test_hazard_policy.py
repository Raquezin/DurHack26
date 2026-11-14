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


def test_clear_scene_no_alert():
    g = geometry([10.0] * 15)
    assert evaluate(g, HazardThresholds()) is None


def test_wall_at_caution_distance():
    g = geometry([2.5, 3.0, 1.5, 3.0, 2.5] * 3)
    alert = evaluate(g, HazardThresholds())
    assert alert is not None
    assert alert.level is HazardLevel.CAUTION
    assert alert.bearing is Bearing.AHEAD
    assert alert.distance_m == 1.5


def test_wall_below_stop_distance():
    g = geometry([1.0] * 15)
    alert = evaluate(g, HazardThresholds())
    assert alert is not None
    assert alert.level is HazardLevel.STOP


def test_corridor_only_ignores_far_columns():
    distances = [0.5, 5.0, 5.0, 5.0, 0.5] * 3
    assert evaluate(geometry(distances), HazardThresholds()) is None


def test_bearing_from_column():
    distances = [5.0] * 15
    distances[6] = 1.0
    alert = evaluate(geometry(distances), HazardThresholds())
    assert alert.bearing is Bearing.LEFT
    distances[6] = 5.0
    distances[8] = 1.0
    alert = evaluate(geometry(distances), HazardThresholds())
    assert alert.bearing is Bearing.RIGHT


def test_invalid_zones_ignored():
    distances = [0.4] * 15
    valid = [True] * 15
    for row in range(3):
        for col in range(1, 4):
            valid[row * 5 + col] = False
    g = geometry(distances, valid=valid)
    assert evaluate(g, HazardThresholds()) is None


def test_provenance_carried():
    g = geometry([1.0] * 15)
    alert = evaluate(g, HazardThresholds())
    assert alert.frame_id == 1
    assert alert.t_capture_ns == 1_000
