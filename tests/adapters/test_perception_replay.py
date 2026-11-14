import math

from test_camera_replay import write_session

from navigator.adapters.clock.system import SystemClock
from navigator.adapters.perception.replay import ReplayScenePerception
from navigator.domain.frame import Frame


def _frame(frame_id):
    return Frame(frame_id, 42 + frame_id, 4, 2, bytes(24))


def test_geometry_follows_frame_id_modulo_session(tmp_path):
    perception = ReplayScenePerception(
        clock=SystemClock(), session_dir=write_session(tmp_path / "s")
    )
    result = perception.perceive(_frame(7), with_previews=False)
    g = result.geometry
    assert (g.frame_id, g.t_capture_ns) == (7, 49)
    assert g.distances_m[1] == 2.0
    assert math.isinf(g.distances_m[0])
    assert g.valid[0] is False
    assert result.camera_jpeg is None


def test_previews_render_from_session(tmp_path):
    perception = ReplayScenePerception(
        clock=SystemClock(), session_dir=write_session(tmp_path / "s")
    )
    result = perception.perceive(_frame(2), with_previews=True)
    assert result.camera_jpeg.startswith(b"\xff\xd8")
    assert result.depth_jpeg.startswith(b"\xff\xd8")
