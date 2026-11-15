from collections.abc import Callable

from navigator.application.latency_trace import LatencyTrace, Stage
from navigator.domain.events import HazardEvent
from navigator.domain.geometry import Perception
from navigator.domain.hazard import Bearing, HazardLevel
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.policies.describe import describe
from navigator.domain.policies.hazard import (
    AlertState,
    HazardThresholds,
    announce,
    escape,
    evaluate,
)
from navigator.domain.speech import Priority, Utterance
from navigator.domain.tags import SceneTag
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher

_HAZARD_DEADLINE_NS = 300_000_000
_DESCRIBE_DEADLINE_NS = 4_000_000_000
_TAG_MAX_AGE_NS = 2_500_000_000
_PHRASES = {
    None: PhraseId.STOP,
    Bearing.LEFT: PhraseId.STOP_GO_LEFT,
    Bearing.RIGHT: PhraseId.STOP_GO_RIGHT,
}
_CAUTION = {
    Bearing.LEFT: PhraseId.CAUTION_LEFT,
    Bearing.AHEAD: PhraseId.CAUTION_AHEAD,
    Bearing.RIGHT: PhraseId.CAUTION_RIGHT,
}

TagsSource = Callable[[], tuple[int, tuple[SceneTag, ...]] | None]


class HazardMonitor:
    def __init__(
        self,
        arbiter,
        events: EventPublisher,
        clock: Clock,
        trace: LatencyTrace,
        thresholds: HazardThresholds,
        deadline_offset_ns: int = 0,
        tags_source: TagsSource | None = None,
    ) -> None:
        self._arbiter = arbiter
        self._events = events
        self._clock = clock
        self._trace = trace
        self._thresholds = thresholds
        self._offset_ns = deadline_offset_ns
        self._tags = tags_source
        self._state = AlertState()
        self._way = None

    def observe(self, perception: Perception) -> None:
        alert = evaluate(perception.geometry, self._thresholds)
        if alert is None:
            self._way = None
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
        if alert.level is HazardLevel.STOP:
            phrase = self._phrase(perception)
        else:
            phrase = _CAUTION[alert.bearing]
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
        self._describe(alert)

    def _describe(self, alert) -> None:
        if self._tags is None:
            return
        marked = self._tags()
        if marked is None:
            return
        t_tags, tags = marked
        if self._clock.now_ns() - t_tags > _TAG_MAX_AGE_NS:
            return
        text = describe(tags, alert.bearing)
        if text is None:
            return
        self._arbiter.submit(
            Utterance(
                priority=Priority.DESCRIPTION,
                phrase=None,
                text=text,
                frame_id=alert.frame_id,
                t_capture_ns=alert.t_capture_ns,
                deadline_ns=alert.t_capture_ns
                + _DESCRIBE_DEADLINE_NS
                - self._offset_ns,
            )
        )

    def _phrase(self, perception: Perception) -> PhraseId:
        self._way = escape(perception.geometry, self._way)
        return _PHRASES[self._way]
