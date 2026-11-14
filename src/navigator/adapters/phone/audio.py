import threading

from navigator.domain.speech import SAMPLE_RATE_HZ, PcmChunk
from navigator.ports.clock import Clock


class PhoneAudioSink:
    def __init__(self, clock: Clock, link) -> None:
        self._clock = clock
        self._link = link
        self._lock = threading.Lock()
        self._playing_until_ns = 0

    def play(self, chunk: PcmChunk) -> None:
        duration_ns = (
            len(chunk.samples) // 2 * 1_000_000_000 // SAMPLE_RATE_HZ
        )
        with self._lock:
            now = self._clock.now_ns()
            self._playing_until_ns = (
                max(self._playing_until_ns, now) + duration_ns
            )
        self._link.send_pcm(chunk.samples)

    def interrupt(self) -> None:
        with self._lock:
            self._playing_until_ns = self._clock.now_ns()
        self._link.send_interrupt()

    def is_playing(self) -> bool:
        with self._lock:
            return self._clock.now_ns() < self._playing_until_ns
