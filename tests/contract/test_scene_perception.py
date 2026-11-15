import contextlib
import math
from pathlib import Path

import pytest

from navigator.adapters.clock.system import SystemClock
from navigator.adapters.perception.replay import ReplayScenePerception
from navigator.adapters.perception.scripted import ScriptedScenePerception
from navigator.domain.frame import Frame

ROWS, COLS = 3, 5
SESSION = Path(__file__).resolve().parents[2] / "fixtures" / "sessions" / "default"


def _scripted():
    return ScriptedScenePerception(
        clock=SystemClock(),
        rows=ROWS,
        cols=COLS,
        horizontal_fov_deg=70.0,
        mount_height_m=1.4,
        pitch_deg=0.0,
        start_m=4.0,
        speed_mps=0.5,
    )


def _replay():
    return ReplayScenePerception(clock=SystemClock(), session_dir=SESSION)


def _gpu():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    gpu = pytest.importorskip("navigator.adapters.perception.gpu")
    return gpu.GpuScenePerception(
        clock=SystemClock(),
        model="da3metric-large",
        input_long_side=504,
        rows=ROWS,
        cols=COLS,
        horizontal_fov_deg=70.0,
        scale=1.0,
        mount_height_m=1.4,
        pitch_deg=0.0,
    )


FACTORIES = [
    pytest.param(_scripted, id="scripted"),
    pytest.param(_replay, id="replay"),
    pytest.param(_gpu, id="gpu", marks=pytest.mark.gpu),
]


@pytest.fixture(scope="module", params=FACTORIES)
def perception(request):
    adapter = request.param()
    with contextlib.ExitStack() as stack:
        if hasattr(adapter, "__enter__"):
            stack.enter_context(adapter)
        yield adapter


def _frame(frame_id=0, t_capture_ns=1_000_000):
    return Frame(
        frame_id=frame_id,
        t_capture_ns=t_capture_ns,
        width=64,
        height=48,
        pixels=bytes(range(256)) * (64 * 48 * 3 // 256),
    )


def test_perceive_provenance_and_shape(perception):
    frame = _frame()
    result = perception.perceive(frame, with_previews=False)
    g = result.geometry
    assert g.frame_id == frame.frame_id
    assert g.t_capture_ns == frame.t_capture_ns
    assert len(g.distances_m) == g.rows * g.cols
    assert len(g.valid) == g.rows * g.cols
    for d in g.distances_m:
        assert d > 0 or math.isinf(d)


def test_previews_only_when_requested(perception):
    without = perception.perceive(_frame(1, 2_000_000), False)
    assert without.camera_jpeg is None
    assert without.depth_jpeg is None
    with_previews = perception.perceive(_frame(2, 3_000_000), True)
    assert with_previews.camera_jpeg.startswith(b"\xff\xd8")
    assert with_previews.depth_jpeg.startswith(b"\xff\xd8")


def test_warm_up_then_perceive(perception):
    perception.warm_up()
    result = perception.perceive(_frame(), False)
    assert result.t_ready_ns > 0
