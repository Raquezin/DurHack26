import asyncio

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.phrase_cache import PhraseCache
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.domain.events import Outcome, UtteranceEvent
from navigator.domain.phrases import PhraseId
from navigator.domain.speech import Priority, Utterance


async def _rig():
    clock = ManualClock()
    sink = RecordingAudioSink(clock=clock)
    synth = ToneSpeechSynthesizer(delay_s=0.0, seconds_per_char=0.02)
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
    )
    return arbiter, sink, events, clock


def _utt(text, priority, deadline_ns, phrase=None, t_capture_ns=0):
    return Utterance(
        priority=priority,
        phrase=phrase,
        text=text,
        frame_id=1,
        t_capture_ns=t_capture_ns,
        deadline_ns=deadline_ns,
    )


def _outcomes(events):
    return [
        e.outcome for e in events.events if isinstance(e, UtteranceEvent)
    ]


async def test_phrase_plays_from_cache_on_calling_thread():
    arbiter, sink, events, _ = await _rig()
    arbiter.submit(_utt("Stop.", Priority.HAZARD, 1_000_000, PhraseId.STOP))
    assert len(sink.plays) == 1
    assert _outcomes(events) == [Outcome.SPOKEN]


async def test_stale_dropped_before_first_sample():
    arbiter, sink, events, clock = await _rig()
    clock.advance(2_000_000)
    arbiter.submit(_utt("late", Priority.HAZARD, 1_000_000, PhraseId.STOP))
    assert sink.plays == []
    assert _outcomes(events) == [Outcome.DROPPED_STALE]


async def test_hazard_preempts_playing_guidance():
    arbiter, sink, events, clock = await _rig()
    arbiter.submit(
        _utt("Keep going straight.", Priority.GUIDANCE, 10**15,
             PhraseId.GO_STRAIGHT)
    )
    arbiter.submit(_utt("Stop.", Priority.HAZARD, 10**15, PhraseId.STOP))
    assert len(sink.interrupts) == 1
    assert _outcomes(events) == [
        Outcome.SPOKEN,
        Outcome.INTERRUPTED,
        Outcome.SPOKEN,
    ]


async def test_free_text_streams_via_loop():
    arbiter, sink, events, clock = await _rig()
    arbiter.submit(
        _utt("a free text line", Priority.GUIDANCE, 10**15)
    )
    for _ in range(100):
        await asyncio.sleep(0.01)
        if _outcomes(events) == [Outcome.SPOKEN]:
            break
    assert len(sink.plays) > 1
    assert _outcomes(events) == [Outcome.SPOKEN]


async def test_free_text_stale_before_first_chunk_dropped():
    clock = ManualClock()
    sink = RecordingAudioSink(clock=clock)
    synth = ToneSpeechSynthesizer(delay_s=0.1, seconds_per_char=0.02)
    cache = PhraseCache()
    events = CollectingEventPublisher()
    arbiter = SpeechArbiter(
        sink=sink,
        synthesizer=synth,
        cache=cache,
        events=events,
        clock=clock,
        loop=asyncio.get_running_loop(),
    )
    arbiter.submit(_utt("too late", Priority.GUIDANCE, 100_000_000))
    clock.advance(200_000_000)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if _outcomes(events):
            break
    assert _outcomes(events) == [Outcome.DROPPED_STALE]
    assert sink.plays == []
