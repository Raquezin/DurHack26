import asyncio

from test_speech_arbiter import (
    _outcomes,
    _rig,
    _utt,
    _wait_outcomes,
)

from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.application.phrase_cache import PhraseCache
from navigator.domain.events import Outcome
from navigator.domain.phrases import PhraseId
from navigator.domain.speech import Priority


class _CountingStream(ToneSpeechSynthesizer):
    def __init__(self, delay_s=0.0):
        super().__init__(delay_s=delay_s, seconds_per_char=0.02)
        self.stream_calls = 0

    async def stream(self, text):
        self.stream_calls += 1
        async for chunk in super().stream(text):
            yield chunk


async def test_cached_text_never_streams():
    synth = _CountingStream()
    arbiter, sink, events, _ = await _rig(synth=synth)
    arbiter.submit(_utt("Continue for 4 metres.", Priority.GUIDANCE))
    assert synth.stream_calls == 0
    assert len(sink.plays) == 1
    assert _outcomes(events) == [
        (Outcome.SPOKEN, "Continue for 4 metres.")
    ]


async def test_finished_stream_is_remembered_and_replayed():
    synth = _CountingStream()
    arbiter, sink, events, clock = await _rig(synth=synth)
    arbiter.submit(_utt("a brand new sentence", Priority.GUIDANCE))
    await _wait_outcomes(events, 1)
    for _ in range(200):
        if arbiter._current is None:
            break
        await asyncio.sleep(0.01)
    once = sum(len(chunk.samples) for _, chunk in sink.plays)
    clock.advance(6_000_000_000)
    arbiter.submit(_utt("a brand new sentence", Priority.GUIDANCE))
    assert synth.stream_calls == 1
    assert len(sink.plays[-1][1].samples) == once
    assert _outcomes(events)[-1] == (
        Outcome.SPOKEN,
        "a brand new sentence",
    )


async def test_interrupted_stream_is_not_remembered():
    synth = _CountingStream(delay_s=0.2)
    cache = PhraseCache()
    await cache.build(synth)
    arbiter, _sink, events, clock = await _rig(synth=synth, cache=cache)
    arbiter.submit(_utt("a cut off sentence", Priority.GUIDANCE))
    arbiter.submit(_utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP))
    await _wait_outcomes(events, 2)
    for _ in range(200):
        if arbiter._current is None:
            break
        await asyncio.sleep(0.01)
    assert cache.get("a cut off sentence") is None
    clock.advance(200_000_000)
    arbiter.submit(_utt("a cut off sentence", Priority.GUIDANCE))
    for _ in range(200):
        if synth.stream_calls == 2:
            break
        await asyncio.sleep(0.01)
    assert synth.stream_calls == 2


async def test_stale_stream_is_not_remembered():
    synth = _CountingStream(delay_s=0.1)
    cache = PhraseCache()
    await cache.build(synth)
    arbiter, _sink, events, clock = await _rig(synth=synth, cache=cache)
    arbiter.submit(
        _utt("too late to say", Priority.GUIDANCE, deadline_ns=100_000_000)
    )
    clock.advance(200_000_000)
    await _wait_outcomes(events, 1)
    for _ in range(200):
        if arbiter._current is None:
            break
        await asyncio.sleep(0.01)
    assert _outcomes(events) == [
        (Outcome.DROPPED_STALE, "too late to say")
    ]
    assert cache.get("too late to say") is None
