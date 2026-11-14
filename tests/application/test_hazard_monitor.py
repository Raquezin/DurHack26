import asyncio

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.hazard_monitor import HazardMonitor
from navigator.application.latency_trace import LatencyTrace
from navigator.application.phrase_cache import PhraseCache
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.domain.events import HazardEvent, Outcome, UtteranceEvent
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.hazard import HazardLevel
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.policies.hazard import HazardThresholds


def _perception(distance_m, frame_id=1, t_capture_ns=1_000):
    distances = [5.0] * 15
    for row in range(3):
        distances[row * 5 + 2] = distance_m
    geometry = SceneGeometry(
        frame_id=frame_id,
        t_capture_ns=t_capture_ns,
        rows=3,
        cols=5,
        distances_m=tuple(distances),
        valid=(True,) * 15,
        horizontal_fov_deg=70.0,
    )
    return Perception(
        geometry=geometry,
        t_ready_ns=t_capture_ns,
        camera_jpeg=None,
        depth_jpeg=None,
    )


async def _rig():
    clock = ManualClock()
    sink = RecordingAudioSink(clock=clock)
    synth = ToneSpeechSynthesizer(delay_s=0.0, seconds_per_char=0.01)
    cache = PhraseCache()
    await cache.build(synth)
    events = CollectingEventPublisher()
    arbiter = SpeechArbiter(
        sink=sink,
        synthesizer=synth,
        cache=cache,
        events=events,
        clock=clock,
        loop=asyncio.get_running_loop(),
        trace=LatencyTrace(),
    )
    monitor = HazardMonitor(
        arbiter=arbiter,
        events=events,
        clock=clock,
        trace=LatencyTrace(),
        thresholds=HazardThresholds(),
    )
    return monitor, events, sink


async def test_clear_scene_no_events():
    monitor, events, sink = await _rig()
    monitor.observe(_perception(5.0))
    assert events.events == []
    assert sink.plays == []


async def test_one_frame_is_not_enough():
    monitor, events, sink = await _rig()
    monitor.observe(_perception(1.0))
    assert events.events == []


async def test_stop_alert_submits_stop_utterance():
    monitor, events, sink = await _rig()
    monitor.observe(_perception(1.0))
    monitor.observe(_perception(1.0, frame_id=2))
    hazard = events.events[0]
    assert isinstance(hazard, HazardEvent)
    assert hazard.level is HazardLevel.STOP
    utterance = events.events[1]
    assert isinstance(utterance, UtteranceEvent)
    assert utterance.outcome is Outcome.SPOKEN
    assert utterance.text == PHRASE_TEXT[PhraseId.STOP]
    assert len(sink.plays) == 1


async def test_held_alert_is_spoken_once():
    monitor, events, sink = await _rig()
    for frame_id in range(1, 30):
        monitor.observe(_perception(1.0, frame_id=frame_id))
    assert len(sink.plays) == 1


async def test_caution_phrase_follows_bearing():
    monitor, events, sink = await _rig()
    monitor.observe(_perception(1.5))
    monitor.observe(_perception(1.5, frame_id=2))
    utterance = events.events[1]
    assert utterance.text == PHRASE_TEXT[PhraseId.CAUTION_AHEAD]


async def test_stale_utterance_dropped():
    monitor, events, sink = await _rig()
    monitor._clock.advance(400_000_000)
    monitor.observe(_perception(1.0, t_capture_ns=0))
    monitor.observe(_perception(1.0, frame_id=2, t_capture_ns=0))
    outcomes = [
        e.outcome for e in events.events if isinstance(e, UtteranceEvent)
    ]
    assert Outcome.DROPPED_STALE in outcomes
