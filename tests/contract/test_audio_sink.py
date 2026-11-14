import time

import pytest

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.domain.speech import PcmChunk


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


FACTORIES = [
    _recording,
    pytest.param(_device, marks=pytest.mark.audio_device),
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
