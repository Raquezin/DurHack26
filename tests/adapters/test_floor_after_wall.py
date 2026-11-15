from pathlib import Path

import pytest

from navigator.adapters.clock.system import SystemClock

pytestmark = [pytest.mark.gpu]

FRAMES = Path(__file__).resolve().parents[2] / "fixtures" / "sessions" / "default" / "frames"


@pytest.fixture(scope="module")
def perception():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    np = pytest.importorskip("numpy")
    pil = pytest.importorskip("PIL.Image")
    gpu = pytest.importorskip("navigator.adapters.perception.gpu")
    frame_mod = pytest.importorskip("navigator.domain.frame")

    def load(path, frame_id):
        image = pil.open(path).convert("RGB")
        pixels = np.asarray(image)[:, :, ::-1].tobytes()
        return frame_mod.Frame(
            frame_id, frame_id * 33_000_000, image.width, image.height, pixels
        )

    rig = gpu.GpuScenePerception(
        clock=SystemClock(),
        model="da3metric-large",
        input_long_side=504,
        rows=3,
        cols=15,
        horizontal_fov_deg=58.0,
        scale=1.0,
        mount_height_m=1.4,
        pitch_deg=0.0,
    )
    with rig:
        rig.warm_up()
        yield rig, load


def test_pitch_and_height_survive_a_wall(perception):
    rig, load = perception
    facing_wall = None
    last = None
    frame_id = 0
    for path in sorted(FRAMES.glob("*.jpg")):
        result = rig.perceive(load(path, frame_id), with_previews=False)
        frame_id += 1
        if path.name == "00298.jpg":
            facing_wall = result.geometry
        last = result.geometry
    for index in range(6):
        result = rig.perceive(
            load(FRAMES / f"{index:05d}.jpg", frame_id), with_previews=False
        )
        frame_id += 1
        last = result.geometry
    assert -12 <= facing_wall.pitch_deg <= 3
    assert -12 <= last.pitch_deg <= 3
    assert 1.2 <= last.mount_height_m <= 1.8
    cols = last.cols
    near = min(
        d
        for row in (1, 2)
        for d, valid in zip(
            last.distances_m[row * cols : (row + 1) * cols],
            last.valid[row * cols : (row + 1) * cols],
        )
        if valid
    )
    assert near < 2.0
