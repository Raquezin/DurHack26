import asyncio

import pytest

from navigator.adapters.reasoner.scripted import ScriptedSceneReasoner
from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.phrases import PhraseId


def _scripted():
    return ScriptedSceneReasoner(
        text="Keep going straight.", phrase=PhraseId.GO_STRAIGHT, delay_s=0.0
    )


def _silent():
    return ScriptedSceneReasoner(text="", phrase=None, delay_s=10.0)


FACTORIES = [_scripted]


def _request():
    geometry = SceneGeometry(
        frame_id=7,
        t_capture_ns=123,
        rows=3,
        cols=5,
        distances_m=(4.0,) * 15,
        valid=(True,) * 15,
        horizontal_fov_deg=70.0,
    )
    return GuidanceRequest(
        geometry=geometry, camera_jpeg=b"jpeg", recently_spoken=()
    )


@pytest.mark.parametrize("factory", FACTORIES)
async def test_instructions_carry_request_frame(factory):
    reasoner = factory()
    seen = []
    async for instruction in reasoner.advise(_request()):
        seen.append(instruction)
    assert seen
    for instruction in seen:
        assert instruction.frame_id == 7
        assert instruction.t_capture_ns == 123


@pytest.mark.parametrize("factory", FACTORIES)
async def test_consumer_can_stop_early(factory):
    reasoner = factory()
    iterator = reasoner.advise(_request())
    async for instruction in iterator:
        break
    await iterator.aclose()


@pytest.mark.parametrize("factory", FACTORIES)
async def test_advise_returns_async_iterator(factory):
    reasoner = factory()
    iterator = reasoner.advise(_request())
    assert hasattr(iterator, "__aiter__")
    await iterator.aclose()
