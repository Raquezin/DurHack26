import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from unittest import mock

import numpy as np

from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.latency_trace import LatencyTrace
from navigator.bootstrap.config import apply_overrides, resolve
from navigator.bootstrap.main import run
from navigator.domain.events import GeometryEvent

LIVE_FLAGS = ("trigger_min_interval_s=0.5", "trigger_keepalive_s=1.5")
FRAME_BUDGETS_MS = (20, 25, 33)
OFFLINE_ADAPTERS = {
    "speech_synthesizer": "tone",
    "audio_sink": "recording",
    "event_publisher": "collecting",
}


def _row(name: str, samples_ms: list[float]) -> str:
    p50, p95, p99 = np.percentile(samples_ms, [50, 95, 99])
    cells = " | ".join(f"{v:.2f}" for v in (p50, p95, p99, max(samples_ms)))
    return f"| `{name}` | {len(samples_ms)} | {cells} |"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reasoner", default="labeller", choices=["labeller", "scripted"])
    parser.add_argument("--duration-s", type=float, default=40.0)
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    args = parser.parse_args()
    settings = apply_overrides(
        resolve("video", {"scene_reasoner": args.reasoner, **OFFLINE_ADAPTERS}),
        [*LIVE_FLAGS, *args.overrides],
    )
    samples: dict[str, list[float]] = defaultdict(list)
    record = LatencyTrace.record

    def recording(trace, stage, elapsed_ns):
        samples[stage.value].append(elapsed_ns / 1e6)
        record(trace, stage, elapsed_ns)

    collector = CollectingEventPublisher()
    with mock.patch.object(LatencyTrace, "record", recording):
        asyncio.run(
            run(settings, args.duration_s, provided={"event_publisher": collector})
        )
    events = collector.events
    ages = [e.age_ms for e in events if isinstance(e, GeometryEvent)]
    print(
        f"recorded walk {settings.session_dir}, {args.duration_s:.0f} s, "
        f"reasoner {args.reasoner}, preview_every {settings.preview_every}"
    )
    print("| Stage | n | p50 ms | p95 ms | p99 ms | max ms |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, values in samples.items():
        print(_row(name, values))
    print(_row("frame arrival → geometry published", ages))
    perception = np.array(samples["perception"])
    over = ", ".join(
        f"{int((perception > budget).sum())} over {budget} ms"
        for budget in FRAME_BUDGETS_MS
    )
    print(f"perception frames: {len(perception)}, {over}")
    print(dict(Counter(type(e).__name__ for e in events)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
