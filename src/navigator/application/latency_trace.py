import asyncio
import threading
from collections import deque
from enum import Enum
from math import ceil

from navigator.domain.events import StageTiming, TimingEvent
from navigator.ports.event_publisher import EventPublisher


class Stage(Enum):
    FRAME_WAIT = "frame_wait"
    PERCEPTION = "perception"
    PREVIEWS = "previews"
    HAZARD_DECISION = "hazard_decision"
    HAZARD = "hazard"
    REASONER = "reasoner"
    TTS = "tts"
    GUIDANCE = "guidance"
    DESCRIPTION = "description"


class LatencyTrace:
    def __init__(self, window: int = 600) -> None:
        self._lock = threading.Lock()
        self._samples = {stage: deque(maxlen=window) for stage in Stage}

    def record(self, stage: Stage, elapsed_ns: int) -> None:
        with self._lock:
            self._samples[stage].append(elapsed_ns)

    def snapshot(self) -> TimingEvent:
        with self._lock:
            samples = {
                stage: list(values) for stage, values in self._samples.items()
            }
        stages = []
        for stage in Stage:
            values = sorted(samples[stage])
            if not values:
                continue
            stages.append(
                StageTiming(
                    name=stage.value,
                    p50_ms=_percentile_ms(values, 50),
                    p95_ms=_percentile_ms(values, 95),
                    p99_ms=_percentile_ms(values, 99),
                )
            )
        return TimingEvent(stages=tuple(stages))

    async def publish_every(
        self, events: EventPublisher, interval_s: float
    ) -> None:
        try:
            while True:
                await asyncio.sleep(interval_s)
                self._publish(events)
        finally:
            self._publish(events)

    def _publish(self, events: EventPublisher) -> None:
        snapshot = self.snapshot()
        if snapshot.stages:
            events.publish(snapshot)


def _percentile_ms(sorted_ns: list[int], p: int) -> float:
    rank = max(0, ceil(p / 100 * len(sorted_ns)) - 1)
    return sorted_ns[rank] / 1e6
