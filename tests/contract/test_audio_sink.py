import time

import pytest

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.clock.system import SystemClock
from navigator.domain.speech import PcmChunk

from _phone_harness import FakePhone


def _recording():
    return RecordingAudioSink(clock=ManualClock())


def _device():
    import sounddevice as sd

    from navigator.adapters.audio.device import SoundDeviceAudioSink

    try:
        sink = SoundDeviceAudioSink(device=None, block_frames=240)
        stream = sink.__enter__()
    except Exception as exc:
        pytest.skip(f"no usable output device: {exc}")
    return sink


def _phone():
    from navigator.adapters.phone.audio import PhoneAudioSink

    harness = FakePhone()
    return PhoneAudioSink(clock=SystemClock(), link=harness.link)


FACTORIES = [
    _recording,
    pytest.param(_device, marks=pytest.mark.audio_device),
    pytest.param(_phone, id="phone"),
]


def _chunk(samples=480):
    return PcmChunk(samples=bytes(samples * 2))


def _tone_chunk(seconds):
    samples = int(24_000 * seconds)
    return PcmChunk(samples=bytes(samples * 2))


@pytest.mark.parametrize("factory", FACTORIES)
def test_play_non_blocking(factory):
    sink = factory()
    try:
        sink.play(_chunk())
        sink.play(_chunk())
    finally:
        _close(sink)


@pytest.mark.parametrize("factory", FACTORIES)
def test_interrupt_discards_pending(factory):
    sink = factory()
    try:
        sink.play(_chunk(480_000))
        assert sink.is_playing()
        sink.interrupt()
        assert not sink.is_playing()
    finally:
        _close(sink)


@pytest.mark.audio_device
def test_interrupt_silences_within_one_block():
    sink = _device()
    try:
        sink.play(_tone_chunk(2.0))
        time.sleep(0.05)
        rendered_before = sink.blocks_rendered
        audio_before = sink.blocks_with_audio
        sink.interrupt()
        time.sleep(0.1)
        assert sink.blocks_rendered - rendered_before >= 1
        assert sink.blocks_with_audio - audio_before <= 1
    finally:
        _close(sink)


def _close(sink):
    if hasattr(sink, "__exit__"):
        sink.__exit__(None, None, None)


def test_phone_play_sends_pcm_and_interrupt():
    import json

    harness = FakePhone()
    from navigator.adapters.phone.audio import PhoneAudioSink

    sink = PhoneAudioSink(clock=SystemClock(), link=harness.link)
    sink.play(_chunk(48000))
    pcm = harness.wait_received(lambda m: m[0] == 2)
    assert pcm is not None
    assert pcm[1:] == _chunk(48000).samples
    assert sink.is_playing()
    sink.interrupt()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if any(json.loads(t).get("type") == "interrupt" for t in harness.texts):
            break
        time.sleep(0.02)
    assert any(
        json.loads(t).get("type") == "interrupt" for t in harness.texts
    )
    assert not sink.is_playing()
