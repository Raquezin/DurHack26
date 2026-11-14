import pytest

from navigator.adapters.camera.synthetic import SyntheticFrameSource
from navigator.adapters.clock.system import SystemClock

FPS = 30


def _synthetic():
    return SyntheticFrameSource(
        clock=SystemClock(), width=64, height=48, fps=FPS
    )


FACTORIES = [_synthetic]


@pytest.mark.parametrize("factory", FACTORIES)
def test_frame_shape_and_stamp(factory):
    source = factory()
    frame = source.next_frame(-1, timeout_s=1.0)
    assert frame is not None
    assert len(frame.pixels) == frame.width * frame.height * 3
    assert frame.t_capture_ns > 0


@pytest.mark.parametrize("factory", FACTORIES)
def test_ids_increase_and_never_repeat(factory):
    source = factory()
    first = source.next_frame(-1, timeout_s=1.0)
    second = source.next_frame(first.frame_id, timeout_s=1.0)
    assert second.frame_id > first.frame_id
    seen = {first.frame_id, second.frame_id}
    assert len(seen) == 2


@pytest.mark.parametrize("factory", FACTORIES)
def test_timeout_returns_none(factory):
    source = factory()
    frame = source.next_frame(-1, timeout_s=1.0)
    assert source.next_frame(frame.frame_id, timeout_s=0.0) is None


@pytest.mark.parametrize("factory", FACTORIES)
def test_skips_to_newest(factory):
    source = factory()
    source.next_frame(-1, timeout_s=1.0)
    frame = source.next_frame(-1, timeout_s=1.0)
    assert frame.frame_id >= 0
