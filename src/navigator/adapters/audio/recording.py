import threading

from navigator.domain.speech import SAMPLE_RATE_HZ, PcmChunk
from navigator.ports.clock import Clock


class RecordingAudioSink:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._plays: list[tuple[int, PcmChunk]] = []
        self._interrupts: list[int] = []
        self._pending_end_ns = 0

    def play(self, chunk: PcmChunk) -> None:
        with self._lock:
            now = self._clock.now_ns()
            self._plays.append((now, chunk))
            duration_ns = len(chunk.samples) // 2 * 1_000_000_000 // SAMPLE_RATE_HZ
            self._pending_end_ns = max(self._pending_end_ns, now) + duration_ns

    def interrupt(self) -> None:
        with self._lock:
            self._interrupts.append(self._clock.now_ns())
            self._pending_end_ns = self._clock.now_ns()

    def is_playing(self) -> bool:
        with self._lock:
            return self._clock.now_ns() < self._pending_end_ns

    @property
    def plays(self) -> list[tuple[int, PcmChunk]]:
        with self._lock:
            return list(self._plays)

    @property
    def interrupts(self) -> list[int]:
        with self._lock:
            return list(self._interrupts)
