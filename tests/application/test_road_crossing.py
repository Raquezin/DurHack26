import asyncio

from test_guidance_loop import STILL, CollectingArbiter, _feed, _loop, _perception

from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.domain.events import TagsEvent
from navigator.domain.guidance import GuidanceInstruction
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.policies.trigger import TriggerSettings
from navigator.domain.tags import SceneTag


class TaggedReasoner:
    def __init__(self, tags, text="Keep going straight.", phrase=PhraseId.GO_STRAIGHT):
        self.tags = tuple(SceneTag(label) for label in tags)
        self.text = text
        self.phrase = phrase

    async def advise(self, request):
        yield GuidanceInstruction(
            phrase=self.phrase,
            text=self.text,
            frame_id=request.geometry.frame_id,
            t_capture_ns=request.geometry.t_capture_ns,
            tags=self.tags,
        )


async def _run(reasoner, frames=12):
    clock = ManualClock()
    arbiter = CollectingArbiter()
    events = CollectingEventPublisher()
    guidance = _loop(reasoner, clock, arbiter, events, TriggerSettings())
    task = asyncio.create_task(guidance.run())
    await _feed(guidance, clock, [STILL] * frames)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    return arbiter, events


def _tags(events):
    return [
        tuple(tag.label for tag in e.tags)
        for e in events.events
        if isinstance(e, TagsEvent)
    ]


async def test_road_crossing_is_announced_whatever_the_model_says():
    arbiter, events = await _run(TaggedReasoner(("road crossing", "car")))
    assert [u.phrase for u in arbiter.utterances] == [PhraseId.ROAD_CROSSING]
    assert arbiter.utterances[0].text == PHRASE_TEXT[PhraseId.ROAD_CROSSING]
    assert _tags(events) == [("road crossing", "car")]


async def test_empty_depth_does_not_send_the_walker_into_the_road():
    arbiter, _ = await _run(TaggedReasoner(("road crossing",)), frames=30)
    assert PhraseId.GO_STRAIGHT not in [u.phrase for u in arbiter.utterances]


async def test_open_path_is_spoken_when_no_road_is_seen():
    arbiter, events = await _run(TaggedReasoner(("pavement", "bench")))
    assert [u.phrase for u in arbiter.utterances] == [PhraseId.GO_STRAIGHT]
    assert _tags(events) == [("pavement", "bench")]


async def test_tags_without_an_instruction_are_shown_but_not_spoken():
    arbiter, events = await _run(TaggedReasoner(("stairs",), text="", phrase=None), frames=3)
    assert not arbiter.utterances
    assert _tags(events) == [("stairs",)]


async def test_answers_without_tags_publish_no_tags():
    _, events = await _run(TaggedReasoner(()), frames=3)
    assert _tags(events) == []


class FlickeringLabeller:
    def __init__(self):
        self.calls = 0

    async def advise(self, request):
        self.calls += 1
        labels = ("road crossing",) if self.calls == 1 else ("pavement",)
        yield GuidanceInstruction(
            phrase=None,
            text="",
            frame_id=request.geometry.frame_id,
            t_capture_ns=request.geometry.t_capture_ns,
            tags=tuple(SceneTag(label) for label in labels),
        )


async def test_a_later_frame_without_the_crossing_keeps_the_road_hold():
    clock = ManualClock()
    arbiter = CollectingArbiter()
    events = CollectingEventPublisher()
    settings = TriggerSettings(min_interval_s=0.0, keepalive_s=0.0)
    reasoner = FlickeringLabeller()
    guidance = _loop(reasoner, clock, arbiter, events, settings)
    task = asyncio.create_task(guidance.run())
    await _feed(guidance, clock, [STILL] * 80)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert reasoner.calls > 1
    assert PhraseId.GO_STRAIGHT not in [u.phrase for u in arbiter.utterances]
