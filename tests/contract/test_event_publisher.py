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
