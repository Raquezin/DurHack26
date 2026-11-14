import asyncio
from contextlib import aclosing, suppress
from dataclasses import replace

from navigator.application.scene_board import SceneBoard
from navigator.domain.events import GuidanceTextEvent
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.policies.steering import (
    SteeringSettings,
    SteeringState,
    advise,
    steer,
)
from navigator.domain.policies.trigger import (
    TriggerSettings,
    should_request,
    still_valid,
)
from navigator.domain.speech import Priority, Utterance
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher
from navigator.ports.scene_reasoner import SceneReasoner

_RECENT_MAX = 5
_LOCAL_DEADLINE_NS = 1_000_000_000


class GuidanceLoop:
    def __init__(
        self,
        board: SceneBoard,
        reasoner: SceneReasoner,
        arbiter,
        events: EventPublisher,
        clock: Clock,
        trigger_settings: TriggerSettings,
        steering_settings: SteeringSettings | None = None,
        deadline_offset_ns: int = 0,
    ) -> None:
        self._board = board
        self._reasoner = reasoner
        self._arbiter = arbiter
        self._events = events
        self._clock = clock
        self._settings = trigger_settings
        self._steering = steering_settings or SteeringSettings()
        self._offset_ns = deadline_offset_ns
        self._recently_spoken: list[str] = []
        self._last_request_ns: int | None = None
        self._last_request: SceneGeometry | None = None
        self._steering_state = SteeringState()
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

    def _steer(self, geometry: SceneGeometry) -> None:
        self._steering_state, phrase = advise(
            self._steering_state,
            steer(geometry, self._steering),
            self._clock.now_ns(),
            self._steering,
        )
        if phrase is not None:
            deadline_ns = geometry.t_capture_ns + _LOCAL_DEADLINE_NS - self._offset_ns
            self._speak(phrase, PHRASE_TEXT[phrase], geometry, deadline_ns)

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
        remaining_s = (deadline_ns - self._clock.now_ns()) / 1e9
        with suppress(TimeoutError):
            async with (
                aclosing(self._reasoner.advise(request)) as stream,
                asyncio.timeout(max(0.0, remaining_s)),
            ):
                async for instruction in stream:
                    self._deliver(geometry, instruction, deadline_ns)

    def _deliver(
        self, asked: SceneGeometry, instruction: GuidanceInstruction, deadline_ns: int
    ) -> None:
        latest = self._board.latest()
        if latest is not None and not still_valid(asked, latest.geometry, self._settings):
            return
        self._events.publish(
            GuidanceTextEvent(request_id=asked.frame_id, delta=instruction.text, final=True)
        )
        self._steering_state = replace(
            self._steering_state, spoken=instruction.phrase, spoken_ns=self._clock.now_ns()
        )
        self._speak(instruction.phrase, instruction.text, asked, deadline_ns)

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
