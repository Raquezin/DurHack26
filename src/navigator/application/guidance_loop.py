import asyncio

from navigator.application.scene_board import SceneBoard
from navigator.domain.events import GuidanceTextEvent
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.policies.trigger import TriggerSettings, should_request
from navigator.domain.speech import Priority, Utterance
from navigator.ports.clock import Clock
from navigator.ports.event_publisher import EventPublisher
from navigator.ports.scene_reasoner import SceneReasoner

_GUIDANCE_DEADLINE_NS = 1_500_000_000
_RECENT_MAX = 5


class GuidanceLoop:
    def __init__(
        self,
        board: SceneBoard,
        reasoner: SceneReasoner,
        arbiter,
        events: EventPublisher,
        clock: Clock,
        trigger_settings: TriggerSettings,
        deadline_offset_ns: int = 0,
    ) -> None:
        self._board = board
        self._reasoner = reasoner
        self._arbiter = arbiter
        self._events = events
        self._clock = clock
        self._settings = trigger_settings
        self._offset_ns = deadline_offset_ns
        self._recently_spoken: list[str] = []
        self._last_request_ns = 0
        self._in_flight = False
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        last_frame_id = -1
        while not self._stop.is_set():
            perception = await self._board.wait_newer(last_frame_id, 0.5)
            if perception is None:
                continue
            last_frame_id = perception.geometry.frame_id
            if not should_request(
                self._clock.now_ns(),
                self._last_request_ns,
                self._in_flight,
                self._settings,
            ):
                continue
            if perception.camera_jpeg is None:
                continue
            await self._request(perception)
        return

    async def _request(self, perception) -> None:
        self._in_flight = True
        self._last_request_ns = self._clock.now_ns()
        request = GuidanceRequest(
            geometry=perception.geometry,
            camera_jpeg=perception.camera_jpeg,
            recently_spoken=tuple(self._recently_spoken),
        )
        request_id = perception.geometry.frame_id
        try:
            async for instruction in self._reasoner.advise(request):
                self._events.publish(
                    GuidanceTextEvent(
                        request_id=request_id,
                        delta=instruction.text,
                        final=True,
                    )
                )
                self._recently_spoken.append(instruction.text)
                del self._recently_spoken[:-_RECENT_MAX]
                self._arbiter.submit(
                    Utterance(
                        priority=Priority.GUIDANCE,
                        phrase=instruction.phrase,
                        text=instruction.text,
                        frame_id=instruction.frame_id,
                        t_capture_ns=instruction.t_capture_ns,
                        deadline_ns=instruction.t_capture_ns
                        + _GUIDANCE_DEADLINE_NS
                        - self._offset_ns,
                    )
                )
        finally:
            self._in_flight = False
