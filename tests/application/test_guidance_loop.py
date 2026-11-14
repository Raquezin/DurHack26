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
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.trigger import TriggerSettings


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
        geometry=geometry,
        t_ready_ns=frame_id,
        camera_jpeg=jpeg,
        depth_jpeg=None,
    )


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
        text="Keep going straight.", phrase=PhraseId.GO_STRAIGHT,
        delay_s=delay_s,
    )
    guidance = GuidanceLoop(
        board=SceneBoard(),
        reasoner=reasoner,
        arbiter=arbiter,
        events=events,
        clock=clock,
        trigger_settings=TriggerSettings(interval_s=1.5),
    )
    return guidance, events, clock


async def test_guidance_utterance_produced():
    guidance, events, clock = await _rig()
    task = asyncio.create_task(guidance.run())
    await asyncio.sleep(0.05)
    clock.advance(2_000_000_000)
    guidance._board.put(_perception(1, t_capture_ns=clock.now_ns()))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if any(isinstance(e, UtteranceEvent) for e in events.events):
            break
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    texts = [
        e for e in events.events if isinstance(e, GuidanceTextEvent)
    ]
    assert texts and texts[0].final
    utterances = [
        e for e in events.events if isinstance(e, UtteranceEvent)
    ]
    assert utterances[0].outcome is Outcome.SPOKEN
    assert utterances[0].text == "Keep going straight."


async def test_perception_without_jpeg_skipped():
    guidance, events, clock = await _rig()
    task = asyncio.create_task(guidance.run())
    await asyncio.sleep(0.05)
    clock.advance(2_000_000_000)
    guidance._board.put(_perception(1, jpeg=None, t_capture_ns=clock.now_ns()))
    await asyncio.sleep(0.1)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    assert not [
        e for e in events.events if isinstance(e, GuidanceTextEvent)
    ]
