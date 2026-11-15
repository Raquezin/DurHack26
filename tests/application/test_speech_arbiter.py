import asyncio

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.latency_trace import LatencyTrace
from navigator.application.phrase_cache import PhraseCache
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.domain.events import Outcome, UtteranceEvent
from navigator.domain.phrases import PhraseId
from navigator.domain.speech import Priority, Utterance


async def _rig(
    synth_delay_s=0.0,
    hazard_cooldown_s=2.0,
    guidance_cooldown_s=5.0,
    synth=None,
    cache=None,
):
    clock = ManualClock()
    sink = RecordingAudioSink(clock=clock)
    if synth is None:
        synth = ToneSpeechSynthesizer(
            delay_s=synth_delay_s, seconds_per_char=0.02
        )
    if cache is None:
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
        hazard_phrase_cooldown_s=hazard_cooldown_s,
        guidance_phrase_cooldown_s=guidance_cooldown_s,
    )
    return arbiter, sink, events, clock


def _utt(text, priority, deadline_ns=10**15, phrase=None, t_capture_ns=0):
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
        (e.outcome, e.text)
        for e in events.events
        if isinstance(e, UtteranceEvent)
    ]


async def _wait_outcomes(events, count, tries=200):
    for _ in range(tries):
        await asyncio.sleep(0.01)
        if len(_outcomes(events)) >= count:
            return
    raise AssertionError(_outcomes(events))


async def test_phrase_plays_from_cache_on_calling_thread():
    arbiter, sink, events, _ = await _rig()
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    assert len(sink.plays) == 1
    assert _outcomes(events) == [(Outcome.SPOKEN, "Stop.")]


async def test_pending_survives_a_lower_priority_submit():
    arbiter, sink, events, _ = await _rig(synth_delay_s=0.3)
    arbiter.submit(_utt("move left", Priority.GUIDANCE))
    arbiter.submit(_utt("a chair ahead", Priority.DESCRIPTION))
    await _wait_outcomes(events, 2)
    assert _outcomes(events) == [
        (Outcome.REPLACED, "a chair ahead"),
        (Outcome.SPOKEN, "move left"),
    ]


async def test_stale_dropped_at_submit():
    arbiter, sink, events, clock = await _rig()
    clock.advance(2_000_000)
    arbiter.submit(
        _utt("late", Priority.HAZARD, deadline_ns=1_000_000,
             phrase=PhraseId.STOP)
    )
    assert sink.plays == []
    assert _outcomes(events) == [(Outcome.DROPPED_STALE, "late")]


async def test_hazard_interrupts_playing_guidance():
    arbiter, sink, events, clock = await _rig()
    arbiter.submit(
        _utt("Keep going straight.", Priority.GUIDANCE,
             phrase=PhraseId.GO_STRAIGHT)
    )
    clock.advance(50_000_000)
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    assert len(sink.interrupts) == 1
    assert _outcomes(events) == [
        (Outcome.SPOKEN, "Keep going straight."),
        (Outcome.INTERRUPTED, "Keep going straight."),
        (Outcome.SPOKEN, "Stop."),
    ]


async def test_finished_guidance_is_not_interrupted():
    arbiter, sink, events, clock = await _rig()
    arbiter.submit(
        _utt("Keep going straight.", Priority.GUIDANCE,
             phrase=PhraseId.GO_STRAIGHT)
    )
    clock.advance(3_000_000_000)
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    assert sink.interrupts == []
    assert _outcomes(events) == [
        (Outcome.SPOKEN, "Keep going straight."),
        (Outcome.SPOKEN, "Stop."),
    ]


async def test_same_phrase_within_cooldown_dropped_repeat():
    arbiter, sink, events, clock = await _rig(
        hazard_cooldown_s=2.0
    )
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    clock.advance(500_000_000)
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    clock.advance(2_000_000_000)
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    assert _outcomes(events) == [
        (Outcome.SPOKEN, "Stop."),
        (Outcome.DROPPED_REPEAT, "Stop."),
        (Outcome.SPOKEN, "Stop."),
    ]
    assert len(sink.plays) == 2


async def test_same_free_text_within_cooldown_dropped_repeat():
    arbiter, _, events, _ = await _rig()
    arbiter.submit(_utt("Continue for 4 metres.", Priority.GUIDANCE))
    await _wait_outcomes(events, 1)
    arbiter.submit(_utt("Continue for 4 metres.", Priority.GUIDANCE))
    await _wait_outcomes(events, 2)
    assert _outcomes(events) == [
        (Outcome.SPOKEN, "Continue for 4 metres."),
        (Outcome.DROPPED_REPEAT, "Continue for 4 metres."),
    ]


async def test_equal_priority_replaces_unstarted():
    arbiter, sink, events, clock = await _rig(synth_delay_s=0.3)
    arbiter.submit(_utt("first", Priority.GUIDANCE))
    arbiter.submit(_utt("second", Priority.GUIDANCE))
    await _wait_outcomes(events, 2)
    assert _outcomes(events) == [
        (Outcome.REPLACED, "first"),
        (Outcome.SPOKEN, "second"),
    ]


async def test_newer_replacement_is_the_one_spoken():
    arbiter, sink, events, clock = await _rig(synth_delay_s=0.2)
    arbiter.submit(_utt("first", Priority.GUIDANCE))
    arbiter.submit(_utt("second", Priority.GUIDANCE))
    await _wait_outcomes(events, 2)
    texts = [text for outcome, text in _outcomes(events)
             if outcome is Outcome.SPOKEN]
    assert texts == ["second"]


async def test_free_text_streams_via_loop():
    arbiter, sink, events, clock = await _rig()
    arbiter.submit(_utt("a free text line", Priority.GUIDANCE))
    await _wait_outcomes(events, 1)
    for _ in range(200):
        if len(sink.plays) > 1:
            break
        await asyncio.sleep(0.01)
    assert len(sink.plays) > 1
    assert _outcomes(events) == [(Outcome.SPOKEN, "a free text line")]


async def test_spoken_published_at_first_stream_chunk():
    clock = ManualClock(start_ns=5_000_000)
    sink = RecordingAudioSink(clock=clock)
    synth = ToneSpeechSynthesizer(delay_s=0.0, seconds_per_char=0.02)
    events = CollectingEventPublisher()
    arbiter = SpeechArbiter(
        sink=sink,
        synthesizer=synth,
        cache=PhraseCache(),
        events=events,
        clock=clock,
        loop=asyncio.get_running_loop(),
        trace=LatencyTrace(),
    )
    text = "a long free text line " * 100
    utterance = _utt(text, Priority.GUIDANCE)
    arbiter.submit(utterance)
    clock.advance(200_000_000)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if sink.plays:
            break
    spoken = [
        e
        for e in events.events
        if isinstance(e, UtteranceEvent) and e.outcome is Outcome.SPOKEN
    ]
    assert arbiter._current is utterance
    assert len(spoken) == 1
    assert spoken[0].age_ms == 205


async def test_free_text_stale_before_first_chunk_dropped():
    arbiter, sink, events, clock = await _rig(synth_delay_s=0.1)
    arbiter.submit(
        _utt("too late", Priority.GUIDANCE, deadline_ns=100_000_000)
    )
    clock.advance(200_000_000)
    await _wait_outcomes(events, 1)
    assert _outcomes(events) == [(Outcome.DROPPED_STALE, "too late")]
    assert sink.plays == []


async def test_current_cleared_after_stream_finishes():
    arbiter, sink, events, clock = await _rig()
    arbiter.submit(_utt("one", Priority.GUIDANCE))
    await _wait_outcomes(events, 1)
    for _ in range(200):
        if arbiter._current is None:
            break
        await asyncio.sleep(0.01)
    assert arbiter._current is None
    arbiter.submit(_utt("two", Priority.GUIDANCE))
    await _wait_outcomes(events, 2)
    outcomes = _outcomes(events)
    assert outcomes[-1] == (Outcome.SPOKEN, "two")
    assert not any(
        outcome is Outcome.REPLACED for outcome, _ in outcomes
    )


class _FailingSynthesizer:
    def stream(self, text):
        async def gen():
            raise RuntimeError("synthesizer failed")
            yield

        return gen()

    async def render(self, text):
        raise RuntimeError("synthesizer failed")


async def test_failed_stream_clears_current_and_publishes_nothing():
    clock = ManualClock()
    sink = RecordingAudioSink(clock=clock)
    events = CollectingEventPublisher()
    arbiter = SpeechArbiter(
        sink=sink,
        synthesizer=_FailingSynthesizer(),
        cache=PhraseCache(),
        events=events,
        clock=clock,
        loop=asyncio.get_running_loop(),
        trace=LatencyTrace(),
    )
    arbiter.submit(_utt("broken", Priority.GUIDANCE))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if arbiter._current is None:
            break
    assert arbiter._current is None
    assert _outcomes(events) == []
    arbiter.submit(_utt("next", Priority.GUIDANCE))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if arbiter._current is None:
            break
    assert not any(
        outcome is Outcome.REPLACED for outcome, _ in _outcomes(events)
    )
