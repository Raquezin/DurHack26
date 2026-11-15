import asyncio

from test_guidance_loop import (
    BLOCKED_RIGHT_OPEN,
    STILL,
    CollectingArbiter,
    _feed,
    _loop,
    _perception,
)

from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.domain.events import RouteEvent
from navigator.domain.guidance import GuidanceInstruction
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.route import floor_line, floor_mark
from navigator.domain.policies.trigger import TriggerSettings
from navigator.domain.speech import Priority
from navigator.domain.tags import SceneTag

CHAIR = SceneTag("chair", ((0.4, 0.4), (0.6, 0.4), (0.6, 0.9), (0.4, 0.9)))
OPEN = (8.0,) * 15


class TagOnlyReasoner:
    def __init__(self, *tags):
        self.tags = tags

    async def advise(self, request):
        if self.tags:
            yield GuidanceInstruction(
                phrase=None,
                text="",
                frame_id=request.geometry.frame_id,
                t_capture_ns=request.geometry.t_capture_ns,
                tags=self.tags,
            )


async def _walk(reasoner, *scenes):
    clock = ManualClock()
    arbiter = CollectingArbiter()
    events = CollectingEventPublisher()
    guidance = _loop(reasoner, clock, arbiter, events, TriggerSettings())
    task = asyncio.create_task(guidance.run())
    start = 0
    for scene in scenes:
        await _feed(guidance, clock, scene, start=start)
        start += len(scene)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    routes = [e for e in events.events if isinstance(e, RouteEvent)]
    return arbiter, routes


async def test_open_path_publishes_a_straight_route_every_frame():
    _, routes = await _walk(TagOnlyReasoner(), [STILL] * 3)
    assert [r.frame_id for r in routes] == [1, 2, 3]
    assert routes[-1].waypoints == ((0.0, 0.0), (0.0, 4.0))
    assert routes[-1].blocker == (0.0, 4.0)
    assert routes[-1].label is None
    geometry = _perception(0).geometry
    assert routes[-1].picture_blocker == floor_mark(geometry, routes[-1].blocker)
    assert routes[-1].picture_line == floor_line(geometry, routes[-1].waypoints)
    assert len(routes[-1].boundary) == 10


async def test_blocked_path_publishes_a_route_bending_to_the_spoken_side():
    arbiter, routes = await _walk(TagOnlyReasoner(), [BLOCKED_RIGHT_OPEN] * 8)
    assert [u.phrase for u in arbiter.utterances] == [PhraseId.VEER_RIGHT]
    assert all(r.waypoints[1][0] > 0 for r in routes)
    assert routes[-1].blocker == (0.0, 2.5)


async def test_direction_is_followed_by_the_name_of_what_blocks_the_line():
    arbiter, routes = await _walk(TagOnlyReasoner(CHAIR), [BLOCKED_RIGHT_OPEN] * 8)
    direction, named = arbiter.utterances
    assert direction.phrase is PhraseId.VEER_RIGHT
    assert named.text == "A chair ahead."
    assert named.priority is Priority.DESCRIPTION
    assert routes[-1].label == "chair"


async def test_tag_beside_the_line_is_not_named():
    beside = SceneTag("chair", ((0.8, 0.4), (1.0, 0.4), (1.0, 0.9), (0.8, 0.9)))
    arbiter, routes = await _walk(TagOnlyReasoner(beside), [BLOCKED_RIGHT_OPEN] * 8)
    assert [u.phrase for u in arbiter.utterances] == [PhraseId.VEER_RIGHT]
    assert routes[-1].label is None


async def test_tags_from_before_the_scene_changed_are_not_named():
    arbiter, routes = await _walk(
        TagOnlyReasoner(CHAIR), [OPEN], [BLOCKED_RIGHT_OPEN] * 8
    )
    assert PhraseId.VEER_RIGHT in [u.phrase for u in arbiter.utterances]
    assert all(u.priority is not Priority.DESCRIPTION for u in arbiter.utterances)
    assert routes[0].label is None and routes[-1].label is None
