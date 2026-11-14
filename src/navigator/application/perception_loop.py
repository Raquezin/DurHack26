import threading
from collections.abc import Callable

from navigator.application.latency_trace import LatencyTrace, Stage
from navigator.domain.events import GeometryEvent, PreviewEvent, PreviewKind
from navigator.domain.geometry import Perception
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher
from navigator.ports.frame_source import FrameSource
from navigator.ports.scene_perception import ScenePerception


class PerceptionLoop:
    def __init__(
        self,
        source: FrameSource,
        perception: ScenePerception,
        board,
        events: EventPublisher,
        clock: Clock,
        trace: LatencyTrace,
        on_perception: Callable[[Perception], None] | None = None,
        preview_every: int = 1,
    ) -> None:
        self._source = source
        self._perception = perception
        self._board = board
        self._events = events
        self._clock = clock
        self._trace = trace
        self._on_perception = on_perception
        self._preview_every = preview_every

    def step(self, after_frame_id: int, timeout_s: float) -> int:
        frame = self._source.next_frame(after_frame_id, timeout_s)
        if frame is None:
            return after_frame_id
        with_previews = (
            self._preview_every > 0
            and frame.frame_id % self._preview_every == 0
        )
        started_ns = self._clock.now_ns()
        perception = self._perception.perceive(frame, with_previews)
        done_ns = self._clock.now_ns()
        self._trace.record(Stage.FRAME_WAIT, started_ns - frame.t_capture_ns)
        self._trace.record(
            Stage.PERCEPTION, perception.t_ready_ns - started_ns
        )
        if with_previews:
            self._trace.record(
                Stage.PREVIEWS, done_ns - perception.t_ready_ns
            )
        self._board.put(perception)
        geometry = perception.geometry
        age_ms = (self._clock.now_ns() - geometry.t_capture_ns) / 1_000_000
        self._events.publish(
            GeometryEvent(
                frame_id=geometry.frame_id,
                distances_m=geometry.distances_m,
                valid=geometry.valid,
                age_ms=age_ms,
            )
        )
        if perception.camera_jpeg is not None:
            self._events.publish(
                PreviewEvent(
                    kind=PreviewKind.CAMERA,
                    frame_id=geometry.frame_id,
                    jpeg=perception.camera_jpeg,
                )
            )
        if perception.depth_jpeg is not None:
            self._events.publish(
                PreviewEvent(
                    kind=PreviewKind.DEPTH,
                    frame_id=geometry.frame_id,
                    jpeg=perception.depth_jpeg,
                )
            )
        if self._on_perception is not None:
            self._on_perception(perception)
        return frame.frame_id

    def run(self, stop: threading.Event) -> None:
        self._perception.warm_up()
        last = -1
        while not stop.is_set():
            last = self.step(last, timeout_s=0.2)
