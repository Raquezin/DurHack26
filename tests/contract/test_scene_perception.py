import math

import pytest

from navigator.adapters.clock.system import SystemClock
from navigator.adapters.perception.scripted import ScriptedScenePerception
from navigator.domain.frame import Frame

ROWS, COLS = 3, 5


def _scripted():
    return ScriptedScenePerception(
        clock=SystemClock(),
        rows=ROWS,
        cols=COLS,
        horizontal_fov_deg=70.0,
        start_m=4.0,
        speed_mps=0.5,
    )


FACTORIES = [_scripted]


def _frame(frame_id=0, t_capture_ns=1_000_000):
    return Frame(
        frame_id=frame_id,
        t_capture_ns=t_capture_ns,
        width=8,
        height=6,
        pixels=bytes(8 * 6 * 3),
    )


@pytest.mark.parametrize("factory", FACTORIES)
def test_perceive_provenance_and_shape(factory):
    perception = factory()
    frame = _frame()
    result = perception.perceive(frame, with_previews=False)
    g = result.geometry
    assert g.frame_id == frame.frame_id
    assert g.t_capture_ns == frame.t_capture_ns
    assert len(g.distances_m) == g.rows * g.cols
    assert len(g.valid) == g.rows * g.cols
    for d in g.distances_m:
        assert d > 0 or math.isinf(d)


@pytest.mark.parametrize("factory", FACTORIES)
def test_previews_only_when_requested(factory):
    perception = factory()
    without = perception.perceive(_frame(1, 2_000_000), False)
    assert without.camera_jpeg is None
    assert without.depth_jpeg is None
    with_previews = perception.perceive(_frame(2, 3_000_000), True)
    assert with_previews.camera_jpeg.startswith(b"\xff\xd8")
    assert with_previews.depth_jpeg.startswith(b"\xff\xd8")


@pytest.mark.parametrize("factory", FACTORIES)
def test_warm_up_then_perceive(factory):
    perception = factory()
    perception.warm_up()
    result = perception.perceive(_frame(), False)
    assert result.t_ready_ns > 0
