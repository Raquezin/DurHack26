import pytest

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.domain.speech import PcmChunk


def _recording():
    return RecordingAudioSink(clock=ManualClock())


FACTORIES = [_recording]


def _chunk(samples=480):
    return PcmChunk(samples=bytes(samples * 2))


@pytest.mark.parametrize("factory", FACTORIES)
def test_play_non_blocking(factory):
    sink = factory()
    sink.play(_chunk())
    sink.play(_chunk())


@pytest.mark.parametrize("factory", FACTORIES)
def test_interrupt_discards_pending(factory):
    sink = factory()
    sink.play(_chunk(480_000))
    assert sink.is_playing()
    sink.interrupt()
    assert not sink.is_playing()
