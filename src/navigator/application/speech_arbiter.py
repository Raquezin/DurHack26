import asyncio
import threading

from navigator.domain.events import Outcome, UtteranceEvent
from navigator.domain.policies import arbitration
from navigator.domain.speech import Priority, Utterance
from navigator.ports.audio_sink import AudioSink
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher
from navigator.ports.speech_synthesizer import SpeechSynthesizer

_PHRASE_COOLDOWN_NS = 2_000_000_000


class SpeechArbiter:
    def __init__(
        self,
        sink: AudioSink,
        synthesizer: SpeechSynthesizer,
        cache,
        events: EventPublisher,
        clock: Clock,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._sink = sink
        self._synthesizer = synthesizer
        self._cache = cache
        self._events = events
        self._clock = clock
        self._loop = loop
        self._lock = threading.Lock()
        self._playing: Utterance | None = None
        self._generation = 0
        self._last_spoken: dict = {}

    def submit(self, utterance: Utterance) -> None:
        now = self._clock.now_ns()
        if arbitration.is_stale(utterance, now):
            self._publish(utterance, Outcome.DROPPED_STALE)
            return
        with self._lock:
            playing = self._playing
            last_spoken = self._last_spoken.get(utterance.phrase)
            if (
                utterance.phrase is not None
                and last_spoken is not None
                and now - last_spoken < _PHRASE_COOLDOWN_NS
            ):
                self._publish(utterance, Outcome.DROPPED_REPEAT)
                return
            if (
                playing is not None
                and self._sink.is_playing()
                and arbitration.preempts(utterance.priority, playing.priority)
            ):
                self._sink.interrupt()
                self._publish(playing, Outcome.INTERRUPTED)
            self._generation += 1
            generation = self._generation
            self._playing = utterance
        if utterance.phrase is not None and self._cache.has(utterance.phrase):
            chunk = self._cache.get(utterance.phrase)
            self._sink.play(chunk)
            with self._lock:
                self._last_spoken[utterance.phrase] = self._clock.now_ns()
            self._publish(utterance, Outcome.SPOKEN)
            return
        asyncio.run_coroutine_threadsafe(
            self._stream(utterance, generation), self._loop
        )

    async def _stream(self, utterance: Utterance, generation: int) -> None:
        first = True
        async for chunk in self._synthesizer.stream(utterance.text):
            with self._lock:
                if generation != self._generation:
                    return
            if first and arbitration.is_stale(
                utterance, self._clock.now_ns()
            ):
                self._publish(utterance, Outcome.DROPPED_STALE)
                return
            first = False
            self._sink.play(chunk)
        if not first:
            self._publish(utterance, Outcome.SPOKEN)
        with self._lock:
            if self._playing is utterance:
                self._playing = None

    def _publish(self, utterance: Utterance, outcome: Outcome) -> None:
        age_ms = (self._clock.now_ns() - utterance.t_capture_ns) / 1_000_000
        self._events.publish(
            UtteranceEvent(
                text=utterance.text,
                priority=utterance.priority,
                outcome=outcome,
                age_ms=age_ms,
            )
        )
