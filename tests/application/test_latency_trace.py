import asyncio

from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.latency_trace import LatencyTrace, Stage
from navigator.domain.events import TimingEvent


def test_percentiles_exact():
    trace = LatencyTrace()
    for ms in range(1, 101):
        trace.record(Stage.PERCEPTION, ms * 1_000_000)
    (stage,) = trace.snapshot().stages
    assert stage.p50_ms == 50
    assert stage.p95_ms == 95
    assert stage.p99_ms == 99


def test_window_drops_oldest():
    trace = LatencyTrace(window=3)
    for ms in (1, 2, 3, 100, 100, 100):
        trace.record(Stage.TTS, ms * 1_000_000)
    (stage,) = trace.snapshot().stages
    assert stage.p50_ms == 100


def test_snapshot_in_stage_order_skipping_empty():
    trace = LatencyTrace()
    trace.record(Stage.TTS, 1_000_000)
    trace.record(Stage.FRAME_WAIT, 1_000_000)
    trace.record(Stage.HAZARD, 1_000_000)
    names = [stage.name for stage in trace.snapshot().stages]
    assert names == ["frame_wait", "hazard", "tts"]


async def test_empty_trace_publishes_nothing():
    trace = LatencyTrace()
    events = CollectingEventPublisher()
    task = asyncio.create_task(trace.publish_every(events, 0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert events.events == []
    assert trace.snapshot().stages == ()


async def test_publishes_after_sample():
    trace = LatencyTrace()
    events = CollectingEventPublisher()
    task = asyncio.create_task(trace.publish_every(events, 0.01))
    trace.record(Stage.PERCEPTION, 5_000_000)
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert any(isinstance(e, TimingEvent) for e in events.events)


async def test_cancel_publishes_one_final_snapshot():
    trace = LatencyTrace()
    events = CollectingEventPublisher()
    task = asyncio.create_task(trace.publish_every(events, 10.0))
    await asyncio.sleep(0)
    trace.record(Stage.PERCEPTION, 5_000_000)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    timing = [e for e in events.events if isinstance(e, TimingEvent)]
    assert len(timing) == 1
