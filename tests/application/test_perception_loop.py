from navigator.adapters.camera.synthetic import SyntheticFrameSource
from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.perception.scripted import ScriptedScenePerception
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.latency_trace import LatencyTrace
from navigator.application.perception_loop import PerceptionLoop
from navigator.application.scene_board import SceneBoard
from navigator.domain.events import GeometryEvent, PreviewEvent


def _rig():
    clock = ManualClock()
    source = SyntheticFrameSource(clock=clock, width=8, height=6, fps=30)
    scripted = ScriptedScenePerception(
        clock=clock,
        rows=3,
        cols=5,
        horizontal_fov_deg=70.0,
        start_m=4.0,
        speed_mps=0.5,
    )
    events = CollectingEventPublisher()
    loop = PerceptionLoop(
        source=source,
        perception=scripted,
        board=SceneBoard(),
        events=events,
        clock=clock,
        trace=LatencyTrace(),
        preview_every=3,
    )
    return loop, events


def test_step_returns_frame_and_publishes_geometry():
    loop, events = _rig()
    frame_id = loop.step(-1, timeout_s=0.1)
    assert frame_id == 0
    assert isinstance(events.events[0], GeometryEvent)


def test_step_timeout_keeps_frame_id():
    loop, events = _rig()
    frame_id = loop.step(-1, timeout_s=0.1)
    assert loop.step(frame_id, timeout_s=0.0) == frame_id


def test_preview_events_every_nth_frame():
    loop, events = _rig()
    last = -1
    for _ in range(3):
        last = loop.step(last, timeout_s=1.0)
    previews = [e for e in events.events if isinstance(e, PreviewEvent)]
    assert len(previews) == 2
    kinds = {p.kind.value for p in previews}
    assert kinds == {"camera", "depth"}
