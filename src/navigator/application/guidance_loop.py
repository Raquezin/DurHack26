import asyncio
from contextlib import aclosing, suppress
from dataclasses import replace

from navigator.application.describing import description
from navigator.application.latency_trace import LatencyTrace, Stage
from navigator.application.scene_board import SceneBoard
from navigator.domain.events import GuidanceTextEvent, RouteEvent, TagsEvent
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest
from navigator.domain.path import blocking_zone
from navigator.domain.phrases import PHRASE_TEXT, PhraseId, continue_for
from navigator.domain.policies.describe import blocker_tag, tag_map
from navigator.domain.policies.route import (
    boundary,
    floor_line,
    floor_mark,
    plan,
    zone_point,
)
from navigator.domain.policies.steering import (
    SteeringSettings,
    SteeringState,
    advise,
    gap,
    path_clearance,
    permits,
    steer,
)
from navigator.domain.policies.trigger import (
    TriggerSettings,
    should_request,
    still_valid,
)
from navigator.domain.speech import Priority, Utterance
from navigator.domain.tags import SceneTag, has_road_crossing
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher
from navigator.ports.scene_reasoner import SceneReasoner

_RECENT_MAX = 5
_LOCAL_DEADLINE_NS = 1_000_000_000
_ROAD_HOLD_NS = 12_000_000_000
_OPEN_PATH = (PhraseId.GO_STRAIGHT, PhraseId.PATH_CLEAR)


class GuidanceLoop:
    def __init__(
        self,
        board: SceneBoard,
        reasoner: SceneReasoner,
        arbiter,
        events: EventPublisher,
        clock: Clock,
        trace: LatencyTrace,
        trigger_settings: TriggerSettings,
        steering_settings: SteeringSettings | None = None,
        deadline_offset_ns: int = 0,
    ) -> None:
        self._board = board
        self._reasoner = reasoner
        self._arbiter = arbiter
        self._events = events
        self._clock = clock
        self._trace = trace
        self._settings = trigger_settings
        self._steering = steering_settings or SteeringSettings()
        self._offset_ns = deadline_offset_ns
        self._recently_spoken: list[str] = []
        self._last_request_ns: int | None = None
        self._last_request: SceneGeometry | None = None
        self._steering_state = SteeringState()
        self._road_until_ns = 0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        last_frame_id = -1
        try:
            while not self._stop.is_set():
                perception = await self._board.wait_newer(last_frame_id, 0.5)
                if perception is None:
                    continue
                last_frame_id = perception.geometry.frame_id
                self._steer(perception.geometry)
                self._maybe_request(perception)
        finally:
            if self._task is not None:
                self._task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._task

    def _road_ahead(self) -> bool:
        return self._clock.now_ns() < self._road_until_ns

    def _steer(self, geometry: SceneGeometry) -> None:
        wanted, committed = steer(
            geometry, self._steering, self._steering_state.committed
        )
        blocker = self._route(geometry, committed)
        road_hides_open_path = wanted in _OPEN_PATH and self._road_ahead()
        if road_hides_open_path:
            wanted = None
        self._steering_state = replace(self._steering_state, committed=committed)
        self._steering_state, phrase = advise(
            self._steering_state, wanted, self._clock.now_ns(), self._steering
        )
        if phrase is not None:
            deadline_ns = geometry.t_capture_ns + _LOCAL_DEADLINE_NS - self._offset_ns
            phrase, text = self._render(phrase, geometry)
            self._speak(phrase, text, geometry, deadline_ns)
            if committed is not None and blocker is not None:
                self._arbiter.submit(
                    description(*blocker, geometry, self._offset_ns)
                )

    def _route(
        self, geometry: SceneGeometry, committed: int | None
    ) -> tuple[SceneTag, int] | None:
        run = None if committed is None else gap(geometry, self._steering, committed)
        zone = blocking_zone(geometry, self._steering.half_width_m)
        tag = zone and blocker_tag(
            self._board.latest_tags(),
            geometry,
            zone,
            self._steering.half_width_m,
            self._settings,
        )
        waypoints = plan(geometry, self._steering, run)
        blocker = zone and zone_point(geometry, zone[2], zone[0])
        self._events.publish(
            RouteEvent(
                frame_id=geometry.frame_id,
                waypoints=waypoints,
                boundary=boundary(geometry, self._steering),
                blocker=blocker,
                label=tag.label if tag else None,
                picture_line=floor_line(geometry, waypoints),
                picture_blocker=(
                    floor_mark(geometry, blocker) if blocker else None
                ),
            )
        )
        return (tag, zone[2]) if tag else None

    def _maybe_request(self, perception: Perception) -> None:
        if perception.camera_jpeg is None or (self._task and not self._task.done()):
            return
        now = self._clock.now_ns()
        if should_request(
            now, self._last_request_ns, self._last_request, perception.geometry, self._settings
        ):
            self._last_request_ns = now
            self._last_request = perception.geometry
            self._task = asyncio.create_task(self._request(perception))

    async def _request(self, perception: Perception) -> None:
        geometry = perception.geometry
        deadline_ns = (
            geometry.t_capture_ns + int(self._settings.max_age_s * 1e9) - self._offset_ns
        )
        request = GuidanceRequest(
            geometry=geometry,
            camera_jpeg=perception.camera_jpeg,
            recently_spoken=tuple(self._recently_spoken),
        )
        started_ns = self._clock.now_ns()
        remaining_s = (deadline_ns - started_ns) / 1e9
        with suppress(TimeoutError):
            async with (
                aclosing(self._reasoner.advise(request)) as stream,
                asyncio.timeout(max(0.0, remaining_s)),
            ):
                first = True
                async for instruction in stream:
                    if first:
                        first = False
                        self._trace.record(
                            Stage.REASONER,
                            self._clock.now_ns() - started_ns,
                        )
                    self._deliver(geometry, instruction, deadline_ns)

    def _deliver(
        self, asked: SceneGeometry, instruction: GuidanceInstruction, deadline_ns: int
    ) -> None:
        self._note_tags(asked, instruction.tags)
        if has_road_crossing(instruction.tags):
            self._announce(PhraseId.ROAD_CROSSING, asked, deadline_ns)
            return
        if not instruction.text or (
            instruction.phrase in _OPEN_PATH and self._road_ahead()
        ):
            return
        latest = self._board.latest()
        if latest is not None and not (
            still_valid(asked, latest.geometry, self._settings)
            and permits(
                latest.geometry,
                instruction.phrase,
                self._steering,
                self._steering_state.committed,
            )
        ):
            return
        self._announce(instruction.phrase, asked, deadline_ns, instruction.text)

    def _note_tags(self, asked: SceneGeometry, tags: tuple[SceneTag, ...]) -> None:
        if not tags:
            return
        self._board.set_tags(tag_map(asked, tags))
        self._events.publish(TagsEvent(frame_id=asked.frame_id, tags=tags))
        if has_road_crossing(tags):
            self._road_until_ns = self._clock.now_ns() + _ROAD_HOLD_NS

    def _render(
        self, phrase: PhraseId | None, geometry: SceneGeometry
    ) -> tuple[PhraseId | None, str]:
        if phrase is not PhraseId.GO_STRAIGHT:
            return phrase, PHRASE_TEXT[phrase]
        latest = self._board.latest()
        if latest is not None:
            geometry = latest.geometry
        metres = int(min(path_clearance(geometry, self._steering), self._steering.max_m))
        if metres >= self._steering.max_m:
            return PhraseId.PATH_CLEAR, PHRASE_TEXT[PhraseId.PATH_CLEAR]
        return None, continue_for(metres)

    def _announce(
        self,
        phrase: PhraseId | None,
        asked: SceneGeometry,
        deadline_ns: int,
        text: str | None = None,
    ) -> None:
        announced = phrase
        if phrase is PhraseId.GO_STRAIGHT or text is None:
            phrase, text = self._render(phrase, asked)
        self._events.publish(
            GuidanceTextEvent(request_id=asked.frame_id, delta=text, final=True)
        )
        self._steering_state = replace(
            self._steering_state, spoken=announced, spoken_ns=self._clock.now_ns()
        )
        self._speak(phrase, text, asked, deadline_ns)

    def _speak(
        self, phrase: PhraseId | None, text: str, geometry: SceneGeometry, deadline_ns: int
    ) -> None:
        self._recently_spoken.append(text)
        del self._recently_spoken[:-_RECENT_MAX]
        self._arbiter.submit(
            Utterance(
                priority=Priority.GUIDANCE,
                phrase=phrase,
                text=text,
                frame_id=geometry.frame_id,
                t_capture_ns=geometry.t_capture_ns,
                deadline_ns=deadline_ns,
            )
        )
