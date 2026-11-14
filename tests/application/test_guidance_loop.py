import asyncio

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.reasoner.scripted import ScriptedSceneReasoner
from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.guidance_loop import GuidanceLoop
from navigator.application.phrase_cache import PhraseCache
from navigator.application.scene_board import SceneBoard
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.domain.events import GuidanceTextEvent, Outcome, UtteranceEvent
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.guidance import GuidanceInstruction
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.trigger import TriggerSettings
from navigator.domain.speech import Priority


def _perception(frame_id, jpeg=b"jpeg", t_capture_ns=0):
    geometry = SceneGeometry(
        frame_id=frame_id,
        t_capture_ns=t_capture_ns,
        rows=3,
        cols=5,
        distances_m=(4.0,) * 15,
        valid=(True,) * 15,
        horizontal_fov_deg=70.0,
    )
    return Perception(
        geometry=geometry, t_ready_ns=frame_id, camera_jpeg=jpeg, depth_jpeg=None
    )


class CollectingArbiter:
    def __init__(self):
        self.utterances = []

    def submit(self, utterance):
        self.utterances.append(utterance)


class TimedReasoner:
    def __init__(self, delays_s):
        self.delays_s = delays_s
        self.requests = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.closed = 0

    async def advise(self, request):
        self.requests.append(request)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            for i, delay_s in enumerate(self.delays_s):
                await asyncio.sleep(delay_s)
                yield GuidanceInstruction(
                    phrase=None,
                    text=f"step {i}",
                    frame_id=request.geometry.frame_id,
                    t_capture_ns=request.geometry.t_capture_ns,
                )
        finally:
            self.in_flight -= 1
            self.closed += 1


def _loop(reasoner, clock, arbiter, events, settings, offset_ns=0):
    return GuidanceLoop(
        board=SceneBoard(),
        reasoner=reasoner,
        arbiter=arbiter,
        events=events,
        clock=clock,
        trigger_settings=settings,
        deadline_offset_ns=offset_ns,
    )


async def _until(predicate, timeout_s=1.0):
    for _ in range(int(timeout_s / 0.005)):
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


async def _rig(delay_s=0.0):
    clock = ManualClock()
    sink = RecordingAudioSink(clock=clock)
    synth = ToneSpeechSynthesizer(delay_s=0.0, seconds_per_char=0.01)
    cache = PhraseCache()
    await cache.build(synth)
    events = CollectingEventPublisher()
    arbiter = SpeechArbiter(
        sink=sink,
        synthesizer=synth,
        cache=cache,
        events=events,
        clock=clock,
        loop=asyncio.get_running_loop(),
    )
    reasoner = ScriptedSceneReasoner(
        text="Keep going straight.", phrase=PhraseId.GO_STRAIGHT, delay_s=delay_s
    )
    guidance = _loop(reasoner, clock, arbiter, events, TriggerSettings())
    return guidance, events, clock


async def test_guidance_utterance_produced():
    guidance, events, clock = await _rig()
    task = asyncio.create_task(guidance.run())
    guidance._board.put(_perception(1, t_capture_ns=clock.now_ns()))
    assert await _until(
        lambda: any(isinstance(e, UtteranceEvent) for e in events.events)
    )
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    texts = [e for e in events.events if isinstance(e, GuidanceTextEvent)]
    assert texts and texts[0].final and texts[0].request_id == 1
    utterances = [e for e in events.events if isinstance(e, UtteranceEvent)]
    assert utterances[0].outcome is Outcome.SPOKEN
    assert utterances[0].text == "Keep going straight."


async def test_perception_without_jpeg_skipped():
    guidance, events, clock = await _rig()
    task = asyncio.create_task(guidance.run())
    guidance._board.put(_perception(1, jpeg=None, t_capture_ns=clock.now_ns()))
    await asyncio.sleep(0.1)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert not [e for e in events.events if isinstance(e, GuidanceTextEvent)]


async def test_utterance_deadline_from_capture_minus_offset():
    clock = ManualClock(start_ns=5_000_000_000)
    arbiter = CollectingArbiter()
    guidance = _loop(
        TimedReasoner([0.0]), clock, arbiter, CollectingEventPublisher(),
        TriggerSettings(), offset_ns=100_000_000,
    )
    task = asyncio.create_task(guidance.run())
    guidance._board.put(_perception(3, t_capture_ns=4_900_000_000))
    assert await _until(lambda: arbiter.utterances)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    utterance = arbiter.utterances[0]
    assert utterance.priority is Priority.GUIDANCE
    assert utterance.frame_id == 3
    assert utterance.deadline_ns == 4_900_000_000 + 1_500_000_000 - 100_000_000


async def test_fixed_cadence_on_manual_clock():
    clock = ManualClock()
    reasoner = TimedReasoner([0.0])
    guidance = _loop(
        reasoner, clock, CollectingArbiter(), CollectingEventPublisher(),
        TriggerSettings(interval_s=1.5),
    )
    task = asyncio.create_task(guidance.run())
    for frame_id in range(1, 31):
        guidance._board.put(_perception(frame_id, t_capture_ns=clock.now_ns()))
        await asyncio.sleep(0.005)
        clock.advance(100_000_000)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert [r.geometry.frame_id for r in reasoner.requests] == [1, 16]


async def test_one_request_in_flight():
    clock = ManualClock()
    reasoner = TimedReasoner([0.2])
    guidance = _loop(
        reasoner, clock, CollectingArbiter(), CollectingEventPublisher(),
        TriggerSettings(interval_s=0.0, abandon_s=1.0),
    )
    task = asyncio.create_task(guidance.run())
    for frame_id in range(1, 21):
        guidance._board.put(_perception(frame_id, t_capture_ns=clock.now_ns()))
        await asyncio.sleep(0.02)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert reasoner.max_in_flight == 1
    assert 1 < len(reasoner.requests) < 20


async def test_request_abandoned_without_first_instruction():
    clock = ManualClock()
    reasoner = TimedReasoner([10.0])
    events = CollectingEventPublisher()
    arbiter = CollectingArbiter()
    guidance = _loop(
        reasoner, clock, arbiter, events,
        TriggerSettings(interval_s=0.0, abandon_s=0.05),
    )
    task = asyncio.create_task(guidance.run())
    guidance._board.put(_perception(1, t_capture_ns=clock.now_ns()))
    assert await _until(lambda: reasoner.closed == 1, 0.5)
    guidance._board.put(_perception(2, t_capture_ns=clock.now_ns()))
    assert await _until(lambda: len(reasoner.requests) == 2, 0.5)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert not arbiter.utterances
    assert not events.events


async def test_later_instructions_bounded_by_deadline():
    clock = ManualClock()
    reasoner = TimedReasoner([0.0, 10.0])
    arbiter = CollectingArbiter()
    guidance = _loop(
        reasoner, clock, arbiter, CollectingEventPublisher(),
        TriggerSettings(interval_s=0.0, abandon_s=1.0),
        offset_ns=1_450_000_000,
    )
    task = asyncio.create_task(guidance.run())
    guidance._board.put(_perception(1, t_capture_ns=clock.now_ns()))
    assert await _until(lambda: reasoner.closed == 1, 0.5)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert [u.text for u in arbiter.utterances] == ["step 0"]
