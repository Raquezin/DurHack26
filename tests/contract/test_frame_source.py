import contextlib
import time
from pathlib import Path

import pytest

from navigator.adapters.camera.replay import ReplayFrameSource
from navigator.adapters.camera.synthetic import SyntheticFrameSource
from navigator.adapters.clock.system import SystemClock

from _phone_harness import FakePhone, make_h264, make_jpeg

FPS = 30
SESSION = Path(__file__).resolve().parents[2] / "fixtures" / "sessions" / "default"


def _synthetic():
    return SyntheticFrameSource(
        clock=SystemClock(), width=64, height=48, fps=FPS
    )


def _replay():
    return ReplayFrameSource(clock=SystemClock(), session_dir=SESSION)


def _phone():
    from navigator.adapters.phone.camera import PhoneFrameSource

    harness = FakePhone()
    harness.start_streaming([bytes([1]) + make_jpeg()])
    return PhoneFrameSource(clock=SystemClock(), link=harness.link)


def _phone_h264():
    from navigator.adapters.phone.camera import PhoneFrameSource

    harness = FakePhone()
    harness.start_streaming([bytes([3]) + unit for unit in make_h264()])
    return PhoneFrameSource(clock=SystemClock(), link=harness.link)


def _webcam():
    webcam = pytest.importorskip("navigator.adapters.camera.webcam")
    return webcam.WebcamFrameSource(
        clock=SystemClock(), device=0, width=640, height=480, fps=FPS, fourcc="MJPG"
    )


FACTORIES = [
    pytest.param(_synthetic, id="synthetic"),
    pytest.param(_replay, id="replay"),
    pytest.param(_webcam, id="webcam", marks=pytest.mark.camera),
    pytest.param(_phone, id="phone"),
    pytest.param(_phone_h264, id="phone-h264"),
]


@pytest.fixture(params=FACTORIES)
def source(request):
    adapter = request.param()
    with contextlib.ExitStack() as stack:
        if hasattr(adapter, "__enter__"):
            try:
                stack.enter_context(adapter)
            except RuntimeError as error:
                pytest.skip(str(error))
        yield adapter


def test_frame_shape_and_stamp(source):
    frame = source.next_frame(-1, timeout_s=1.0)
    assert frame is not None
    assert len(frame.pixels) == frame.width * frame.height * 3
    assert frame.t_capture_ns > 0


def test_ids_increase_and_never_repeat(source):
    first = source.next_frame(-1, timeout_s=1.0)
    second = source.next_frame(first.frame_id, timeout_s=1.0)
    assert second.frame_id > first.frame_id
    assert source.next_frame(-1, timeout_s=1.0).frame_id > second.frame_id


def test_timeout_returns_none(source):
    frame = source.next_frame(-1, timeout_s=1.0)
    assert source.next_frame(frame.frame_id, timeout_s=0.0) is None


def test_phone_link_acks_every_frame():
    harness = FakePhone()
    for _ in range(3):
        harness.send_frame(make_jpeg())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and len(harness.texts) < 3:
        time.sleep(0.02)
    assert harness.texts == ['{"type":"ack"}'] * 3


def test_phone_link_rejects_undecodable_video():
    from navigator.adapters.phone.camera import PhoneFrameSource

    harness = FakePhone()
    PhoneFrameSource(clock=SystemClock(), link=harness.link)
    harness.send_raw(bytes([3]) + b"\x00\x01\x02\x03" * 50)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not harness.texts:
        time.sleep(0.02)
    assert harness.texts == ['{"type":"jpeg"}']


def test_skips_to_newest(source):
    first = source.next_frame(-1, timeout_s=1.0)
    time.sleep(0.2)
    newest = source.next_frame(-1, timeout_s=1.0)
    assert newest.frame_id > first.frame_id + 1
