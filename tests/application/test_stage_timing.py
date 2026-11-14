import asyncio

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.guidance_loop import GuidanceLoop
from navigator.application.hazard_monitor import HazardMonitor
from navigator.application.latency_trace import LatencyTrace, Stage
from navigator.application.perception_loop import PerceptionLoop
from navigator.application.phrase_cache import PhraseCache
from navigator.application.scene_board import SceneBoard
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.domain.frame import Frame
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.guidance import GuidanceInstruction
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.hazard import HazardThresholds
from navigator.domain.policies.trigger import TriggerSettings
from navigator.domain.speech import Priority, Utterance

STILL = (4.0,) * 15


def _geometry(frame_id, t_capture_ns=0, distances=STILL):
    return SceneGeometry(
        frame_id=frame_id,
        t_capture_ns=t_capture_ns,
        rows=3,
        cols=5,
        distances_m=distances,
        valid=(True,) * 15,
        horizontal_fov_deg=70.0,
    )


def _perception(frame_id, jpeg=b"jpeg", t_capture_ns=0, t_ready_ns=0, distances=STILL):
    return Perception(
        geometry=_geometry(frame_id, t_capture_ns, distances),
        t_ready_ns=t_ready_ns,
        camera_jpeg=jpeg,
        depth_jpeg=None,
    )


def _stage(trace, stage):
    return next(
        s for s in trace.snapshot().stages if s.name == stage.value
    )


def _names(trace):
    return [s.name for s in trace.snapshot().stages]


class _Source:
    def __init__(self, frame):
        self._frame = frame

    def next_frame(self, after_frame_id, timeout_s):
        return self._frame


class _Perception:
    def __init__(self, clock):
        self._clock = clock

    def perceive(self, frame, with_previews):
        self._clock.advance(10_000_000)
        ready_ns = self._clock.now_ns()
        if with_previews:
            self._clock.advance(2_000_000)
        return Perception(
            geometry=_geometry(frame.frame_id, frame.t_capture_ns),
            t_ready_ns=ready_ns,
            camera_jpeg=None,
            depth_jpeg=None,
        )


def _perception_loop(clock, trace, preview_every):
    frame = Frame(
        frame_id=0, t_capture_ns=0, width=8, height=6, pixels=b"\0" * 144
    )
    return PerceptionLoop(
        source=_Source(frame),
        perception=_Perception(clock),
        board=SceneBoard(),
        events=CollectingEventPublisher(),
        clock=clock,
        trace=trace,
        preview_every=preview_every,
    )


def test_perception_loop_records_frame_wait_perception_previews():
    clock = ManualClock(start_ns=4_000_000)
    trace = LatencyTrace()
    loop = _perception_loop(clock, trace, preview_every=1)
    loop.step(-1, timeout_s=0.0)
    assert _stage(trace, Stage.FRAME_WAIT).p50_ms == 4
    assert _stage(trace, Stage.PERCEPTION).p50_ms == 10
    assert _stage(trace, Stage.PREVIEWS).p50_ms == 2


def test_perception_loop_skips_previews_on_plain_frames():
    clock = ManualClock(start_ns=4_000_000)
    trace = LatencyTrace()
    loop = _perception_loop(clock, trace, preview_every=0)
    loop.step(-1, timeout_s=0.0)
    assert "previews" not in _names(trace)


class _Arbiter:
    def __init__(self):
        self.utterances = []

    def submit(self, utterance):
        self.utterances.append(utterance)


def _hazard_perception(distance_m, frame_id, t_capture_ns=0, t_ready_ns=0):
    distances = list(STILL)
    for row in range(3):
        distances[row * 5 + 2] = distance_m
    return _perception(
        frame_id,
        jpeg=None,
        t_capture_ns=t_capture_ns,
        t_ready_ns=t_ready_ns,
        distances=tuple(distances),
    )


def test_hazard_monitor_records_decision_only_when_speaking():
    clock = ManualClock()
    trace = LatencyTrace()
    monitor = HazardMonitor(
        arbiter=_Arbiter(),
        events=CollectingEventPublisher(),
        clock=clock,
        trace=trace,
        thresholds=HazardThresholds(),
    )
    monitor.observe(_hazard_perception(5.0, frame_id=1))
    monitor.observe(_hazard_perception(1.0, frame_id=2))
    assert trace.snapshot().stages == ()
    clock.advance(20_000_000)
    monitor.observe(
        _hazard_perception(1.0, frame_id=3, t_capture_ns=0, t_ready_ns=0)
    )
    assert _stage(trace, Stage.HAZARD_DECISION).p50_ms == 20


async def _arbiter(clock, trace, synth_delay_s=0.0):
    sink = RecordingAudioSink(clock=clock)
    synth = ToneSpeechSynthesizer(
        delay_s=synth_delay_s, seconds_per_char=0.02
    )
    cache = PhraseCache()
    await cache.build(synth)
    return SpeechArbiter(
        sink=sink,
        synthesizer=synth,
        cache=cache,
        events=CollectingEventPublisher(),
        clock=clock,
        loop=asyncio.get_running_loop(),
        trace=trace,
    )


def _utt(text, priority, deadline_ns=10**15, phrase=None, t_capture_ns=0):
    return Utterance(
        priority=priority,
        phrase=phrase,
        text=text,
        frame_id=1,
        t_capture_ns=t_capture_ns,
        deadline_ns=deadline_ns,
    )


async def test_cached_hazard_records_capture_to_sink():
    clock = ManualClock(start_ns=17_000_000)
    trace = LatencyTrace()
    arbiter = await _arbiter(clock, trace)
    arbiter.submit(
        _utt("Stop.", Priority.HAZARD, phrase=PhraseId.STOP)
    )
    assert _stage(trace, Stage.HAZARD).p50_ms == 17


async def test_cached_stale_at_submit_records_nothing():
    clock = ManualClock(start_ns=2_000_000)
    trace = LatencyTrace()
    arbiter = await _arbiter(clock, trace)
    arbiter.submit(
        _utt(
            "Stop.",
            Priority.HAZARD,
            deadline_ns=1_000_000,
            phrase=PhraseId.STOP,
        )
    )
    assert trace.snapshot().stages == ()


async def _wait(predicate, tries=200):
    for _ in range(tries):
        await asyncio.sleep(0.01)
        if predicate():
            return
    raise AssertionError("timed out")


async def test_streamed_guidance_records_tts_and_guidance():
    clock = ManualClock(start_ns=5_000_000)
    trace = LatencyTrace()
    arbiter = await _arbiter(clock, trace, synth_delay_s=0.05)
    events = arbiter._events
    arbiter.submit(_utt("a free text line", Priority.GUIDANCE))
    clock.advance(200_000_000)
    await _wait(lambda: len(events.events) >= 1)
    assert _stage(trace, Stage.TTS).p50_ms == 200
    assert _stage(trace, Stage.GUIDANCE).p50_ms == 205


async def test_streamed_stale_records_tts_but_not_guidance():
    clock = ManualClock()
    trace = LatencyTrace()
    arbiter = await _arbiter(clock, trace, synth_delay_s=0.05)
    events = arbiter._events
    arbiter.submit(
        _utt("too late", Priority.GUIDANCE, deadline_ns=100_000_000)
    )
    clock.advance(200_000_000)
    await _wait(lambda: len(events.events) >= 1)
    assert "tts" in _names(trace)
    assert "guidance" not in _names(trace)


class _GatedReasoner:
    def __init__(self, gates):
        self._gates = gates
        self.requests = []

    async def advise(self, request):
        self.requests.append(request)
        for gate in self._gates:
            await gate.wait()
            yield GuidanceInstruction(
                phrase=None,
                text="step",
                frame_id=request.geometry.frame_id,
                t_capture_ns=request.geometry.t_capture_ns,
            )


async def test_reasoner_records_first_instruction_only():
    clock = ManualClock()
    trace = LatencyTrace()
    gates = [asyncio.Event(), asyncio.Event()]
    reasoner = _GatedReasoner(gates)
    arbiter = _Arbiter()
    guidance = GuidanceLoop(
        board=SceneBoard(),
        reasoner=reasoner,
        arbiter=arbiter,
        events=CollectingEventPublisher(),
        clock=clock,
        trace=trace,
        trigger_settings=TriggerSettings(),
    )
    task = asyncio.create_task(guidance.run())
    guidance._board.put(_perception(1, t_capture_ns=clock.now_ns()))
    await _wait(lambda: len(reasoner.requests) >= 1)
    clock.advance(800_000_000)
    gates[0].set()
    await _wait(lambda: len(arbiter.utterances) >= 1)
    clock.advance(400_000_000)
    gates[1].set()
    await _wait(lambda: len(arbiter.utterances) >= 2)
    guidance.stop()
    await asyncio.wait_for(task, 1.0)
    reasoner_stage = _stage(trace, Stage.REASONER)
    assert reasoner_stage.p50_ms == 800
    assert reasoner_stage.p99_ms == 800
