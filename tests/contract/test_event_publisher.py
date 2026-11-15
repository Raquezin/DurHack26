import io
import json

import pytest

from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.adapters.ui.log import LogEventPublisher
from navigator.domain.events import (
    GeometryEvent,
    Outcome,
    PreviewEvent,
    PreviewKind,
    RouteEvent,
    StageTiming,
    TimingEvent,
    UtteranceEvent,
)
from navigator.domain.speech import Priority


def _collecting():
    return CollectingEventPublisher(), None


def _log():
    stream = io.StringIO()
    return LogEventPublisher(stream=stream), stream


FACTORIES = [_collecting, _log]


@pytest.mark.parametrize("factory", FACTORIES)
def test_publish_is_non_blocking(factory):
    publisher, _ = factory()
    event = GeometryEvent(
        frame_id=1, distances_m=(1.0,), valid=(True,), age_ms=2.0
    )
    publisher.publish(event)


@pytest.mark.parametrize("factory", FACTORIES)
def test_events_reach_observer(factory):
    publisher, stream = factory()
    publisher.publish(
        UtteranceEvent(
            text="Stop.",
            priority=Priority.HAZARD,
            outcome=Outcome.SPOKEN,
            age_ms=1.0,
        )
    )
    if stream is None:
        assert len(publisher.events) == 1
    else:
        lines = stream.getvalue().strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["type"] == "utterance"
        assert payload["outcome"] == "spoken"
        assert payload["priority"] == "hazard"


@pytest.mark.parametrize("factory", FACTORIES)
def test_timing_event_reaches_observer(factory):
    publisher, stream = factory()
    publisher.publish(
        TimingEvent(
            stages=(
                StageTiming(
                    name="perception", p50_ms=1.0, p95_ms=2.0, p99_ms=3.0
                ),
            )
        )
    )
    if stream is None:
        assert len(publisher.events) == 1
    else:
        (line,) = stream.getvalue().strip().splitlines()
        assert json.loads(line) == {
            "type": "timing",
            "stages": [
                {
                    "name": "perception",
                    "p50_ms": 1.0,
                    "p95_ms": 2.0,
                    "p99_ms": 3.0,
                }
            ],
        }


@pytest.mark.parametrize("factory", FACTORIES)
def test_inf_serialised_as_null_and_preview_slim(factory):
    publisher, stream = factory()
    publisher.publish(
        GeometryEvent(
            frame_id=2,
            distances_m=(float("inf"),),
            valid=(False,),
            age_ms=0.5,
        )
    )
    publisher.publish(
        PreviewEvent(kind=PreviewKind.DEPTH, frame_id=2, jpeg=b"abc")
    )
    if stream is None:
        assert len(publisher.events) == 2
    else:
        geometry, preview = [
            json.loads(line) for line in stream.getvalue().splitlines()
        ]
        assert geometry["distances_m"] == [None]
        assert preview == {
            "type": "preview",
            "kind": "depth",
            "frame_id": 2,
            "jpeg_bytes": 3,
        }


def test_route_event_wire_format():
    publisher, stream = _log()
    publisher.publish(
        RouteEvent(
            frame_id=4,
            waypoints=((0.0, 0.0), (0.93, 3.0), (0.93, 8.0)),
            boundary=((-1.11, 2.0), (-0.96, 2.0)),
            blocker=(0.0, 2.0),
            label="chair",
        )
    )
    publisher.publish(
        RouteEvent(frame_id=5, waypoints=((0.0, 0.0),), boundary=(), blocker=None, label=None)
    )
    bent, empty = (json.loads(line) for line in stream.getvalue().splitlines())
    assert bent == {
        "type": "route",
        "frame_id": 4,
        "waypoints": [[0.0, 0.0], [0.93, 3.0], [0.93, 8.0]],
        "boundary": [[-1.11, 2.0], [-0.96, 2.0]],
        "blocker": [0.0, 2.0],
        "label": "chair",
    }
    assert empty["blocker"] is None and empty["label"] is None
