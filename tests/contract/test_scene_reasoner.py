import json
import math
from contextlib import AsyncExitStack
from pathlib import Path

import pytest

from navigator.adapters.reasoner.scripted import ScriptedSceneReasoner
from navigator.bootstrap.config import Settings
from navigator.bootstrap.secrets import Secrets
from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.phrases import PhraseId

ROOT = Path(__file__).resolve().parents[2]
SECRETS = Secrets.load(ROOT / ".env")
SCENE = ROOT / "fixtures" / "scenes" / "clear_corridor"


def _scripted():
    return ScriptedSceneReasoner(
        text="Keep going straight.", phrase=PhraseId.GO_STRAIGHT, delay_s=0.0
    )


def _gemini():
    from navigator.adapters.reasoner.gemini import GeminiSceneReasoner

    settings = Settings()
    return GeminiSceneReasoner(
        api_key=SECRETS.require("GEMINI_API_KEY"),
        model=settings.gemini_model,
        max_output_tokens=settings.gemini_max_output_tokens,
    )


FACTORIES = [
    pytest.param(_scripted, id="scripted"),
    pytest.param(
        _gemini,
        id="gemini",
        marks=[
            pytest.mark.keys,
            pytest.mark.skipif(
                not SECRETS.get("GEMINI_API_KEY"),
                reason="GEMINI_API_KEY absent from .env",
            ),
        ],
    ),
]


@pytest.fixture(params=FACTORIES)
async def reasoner(request):
    async with AsyncExitStack() as stack:
        adapter = request.param()
        if hasattr(adapter, "__aenter__"):
            adapter = await stack.enter_async_context(adapter)
        yield adapter


def _request():
    data = json.loads(SCENE.with_suffix(".json").read_text())
    geometry = SceneGeometry(
        frame_id=7,
        t_capture_ns=123,
        rows=data["rows"],
        cols=data["cols"],
        distances_m=tuple(
            math.inf if d is None else d for d in data["distances_m"]
        ),
        valid=tuple(data["valid"]),
        horizontal_fov_deg=data["horizontal_fov_deg"],
    )
    return GuidanceRequest(
        geometry=geometry,
        camera_jpeg=SCENE.with_suffix(".jpg").read_bytes(),
        recently_spoken=(),
    )


async def test_instructions_carry_request_frame(reasoner):
    seen = []
    async for instruction in reasoner.advise(_request()):
        seen.append(instruction)
    assert seen
    for instruction in seen:
        assert instruction.frame_id == 7
        assert instruction.t_capture_ns == 123
        assert instruction.text or instruction.tags


async def test_consumer_can_stop_early(reasoner):
    iterator = reasoner.advise(_request())
    async for instruction in iterator:
        break
    await iterator.aclose()


async def test_advise_returns_async_iterator(reasoner):
    iterator = reasoner.advise(_request())
    assert hasattr(iterator, "__aiter__")
    await iterator.aclose()
