import asyncio
import threading

from navigator.application.phrase_cache import PhraseCache
from navigator.domain.events import Outcome, UtteranceEvent
from navigator.domain.policies import arbitration
from navigator.domain.speech import Utterance
from navigator.ports.audio_sink import AudioSink
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher
from navigator.ports.speech_synthesizer import SpeechSynthesizer


class SpeechArbiter:
    def __init__(
        self,
        sink: AudioSink,
        synthesizer: SpeechSynthesizer,
        cache: PhraseCache,
        events: EventPublisher,
        clock: Clock,
        loop: asyncio.AbstractEventLoop,
        hazard_phrase_cooldown_s: float = 2.0,
        guidance_phrase_cooldown_s: float = 5.0,
    ) -> None:
        self._sink = sink
        self._synthesizer = synthesizer
        self._cache = cache
        self._events = events
        self._clock = clock
        self._loop = loop
        self._hazard_cooldown_ns = int(hazard_phrase_cooldown_s * 1e9)
        self._guidance_cooldown_ns = int(guidance_phrase_cooldown_s * 1e9)
        self._lock = threading.Lock()
        self._current: Utterance | None = None
        self._current_started = False
        self._generation = 0
        self._last_spoken: dict = {}

    def submit(self, utterance: Utterance) -> None:
        now = self._clock.now_ns()
        if arbitration.is_stale(utterance, now):
            self._publish(utterance, Outcome.DROPPED_STALE)
            return
        with self._lock:
            last = self._last_spoken.get(utterance.phrase)
            if (
                utterance.phrase is not None
                and last is not None
                and now - last < self._cooldown_ns(utterance)
            ):
                self._publish(utterance, Outcome.DROPPED_REPEAT)
                return
            current = self._current
            if current is not None:
                if (
                    not self._current_started
                    and utterance.priority <= current.priority
                ):
                    self._publish(current, Outcome.REPLACED)
                elif self._current_started and arbitration.preempts(
                    utterance.priority, current.priority
                ):
                    self._sink.interrupt()
                    self._publish(current, Outcome.INTERRUPTED)
            self._generation += 1
            generation = self._generation
            self._current = utterance
            self._current_started = False
        if utterance.phrase is not None and self._cache.has(utterance.phrase):
            self._speak_cached(utterance)
            return
        asyncio.run_coroutine_threadsafe(
            self._stream(utterance, generation), self._loop
        )

    def _cooldown_ns(self, utterance: Utterance) -> int:
        if arbitration.is_hazard(utterance):
            return self._hazard_cooldown_ns
        return self._guidance_cooldown_ns

    def _speak_cached(self, utterance: Utterance) -> None:
        if arbitration.is_stale(utterance, self._clock.now_ns()):
            self._publish(utterance, Outcome.DROPPED_STALE)
            return
        self._sink.play(self._cache.get(utterance.phrase))
        with self._lock:
            self._last_spoken[utterance.phrase] = self._clock.now_ns()
            self._current_started = True
        self._publish(utterance, Outcome.SPOKEN)

    async def _stream(self, utterance: Utterance, generation: int) -> None:
        started = False
        try:
            async for chunk in self._synthesizer.stream(utterance.text):
                with self._lock:
                    if generation != self._generation:
                        return
                if not started:
                    if arbitration.is_stale(
                        utterance, self._clock.now_ns()
                    ):
                        self._publish(utterance, Outcome.DROPPED_STALE)
                        return
                    started = True
                    with self._lock:
                        self._current_started = True
                self._sink.play(chunk)
            if started:
                with self._lock:
                    if utterance.phrase is not None:
                        self._last_spoken[utterance.phrase] = (
                            self._clock.now_ns()
                        )
                self._publish(utterance, Outcome.SPOKEN)
        except Exception:
            pass
        finally:
            self._clear_current(utterance)

    def _clear_current(self, utterance: Utterance) -> None:
        with self._lock:
            if self._current is utterance:
                self._current = None
                self._current_started = False

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
