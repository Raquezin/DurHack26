import math

import pytest

from navigator.adapters.clock.system import SystemClock

pytestmark = [pytest.mark.gpu, pytest.mark.camera]


@pytest.fixture(scope="module")
def rig():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    gpu = pytest.importorskip("navigator.adapters.perception.gpu")
    webcam = pytest.importorskip("navigator.adapters.camera.webcam")
    clock = SystemClock()
    camera = webcam.WebcamFrameSource(
        clock=clock, device=0, width=640, height=480, fps=30, fourcc="MJPG"
    )
    perception = gpu.GpuScenePerception(
        clock=clock,
        model="da3metric-large",
        input_long_side=504,
        rows=3,
        cols=5,
        horizontal_fov_deg=70.0,
        scale=1.0,
        mount_height_m=1.4,
        pitch_deg=0.0,
    )
    try:
        camera.__enter__()
    except RuntimeError as error:
        pytest.skip(str(error))
    with perception:
        perception.warm_up()
        yield camera, perception
    camera.__exit__(None, None, None)


def test_live_frames_meet_contract(rig):
    camera, perception = rig
    last = -1
    for index in range(10):
        frame = camera.next_frame(last, timeout_s=1.0)
        last = frame.frame_id
        result = perception.perceive(frame, with_previews=index % 3 == 0)
        g = result.geometry
        assert (g.frame_id, g.t_capture_ns) == (frame.frame_id, frame.t_capture_ns)
        assert len(g.distances_m) == len(g.valid) == 15
        assert all(d > 0 or math.isinf(d) for d in g.distances_m)
        assert result.t_ready_ns >= frame.t_capture_ns
        assert (result.camera_jpeg is not None) == (index % 3 == 0)
    assert any(g.valid)
