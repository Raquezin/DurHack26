from navigator.application.latency_trace import LatencyTrace, Stage
from navigator.domain.events import HazardEvent
from navigator.domain.geometry import Perception
from navigator.domain.hazard import Bearing, HazardLevel
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.policies.hazard import (
    AlertState,
    HazardThresholds,
    announce,
    evaluate,
)
from navigator.domain.speech import Priority, Utterance
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher

_HAZARD_DEADLINE_NS = 300_000_000
_PHRASES = {
    Bearing.AHEAD: PhraseId.CAUTION_AHEAD,
    Bearing.LEFT: PhraseId.CAUTION_LEFT,
    Bearing.RIGHT: PhraseId.CAUTION_RIGHT,
}


class HazardMonitor:
    def __init__(
        self,
        arbiter,
        events: EventPublisher,
        clock: Clock,
        trace: LatencyTrace,
        thresholds: HazardThresholds,
        deadline_offset_ns: int = 0,
    ) -> None:
        self._arbiter = arbiter
        self._events = events
        self._clock = clock
        self._trace = trace
        self._thresholds = thresholds
        self._offset_ns = deadline_offset_ns
        self._state = AlertState()

    def observe(self, perception: Perception) -> None:
        alert = evaluate(perception.geometry, self._thresholds)
        self._state, speak = announce(self._state, alert, self._thresholds)
        if not speak:
            return
        self._events.publish(
            HazardEvent(
                level=alert.level,
                bearing=alert.bearing,
                distance_m=alert.distance_m,
                frame_id=alert.frame_id,
            )
        )
        phrase = (
            PhraseId.STOP
            if alert.level is HazardLevel.STOP
            else _PHRASES[alert.bearing]
        )
        self._arbiter.submit(
            Utterance(
                priority=Priority.HAZARD,
                phrase=phrase,
                text=PHRASE_TEXT[phrase],
                frame_id=alert.frame_id,
                t_capture_ns=alert.t_capture_ns,
                deadline_ns=alert.t_capture_ns
                + _HAZARD_DEADLINE_NS
                - self._offset_ns,
            )
        )
        self._trace.record(
            Stage.HAZARD_DECISION,
            self._clock.now_ns() - perception.t_ready_ns,
        )
