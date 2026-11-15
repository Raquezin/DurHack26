import asyncio
import io
from types import SimpleNamespace

import pytest
from google.genai import types
from PIL import Image

from navigator.adapters.reasoner import gemini
from navigator.adapters.reasoner.gemini import GeminiSceneReasoner
from navigator.adapters.reasoner.prompt import SYSTEM_PROMPT, user_text
from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.phrases import PhraseId
from navigator.domain.tags import SceneTag


class FakeModels:
    def __init__(self, chunks, delay_s=0.0, error=None, fail_after=None):
        self.chunks = chunks
        self.delay_s = delay_s
        self.error = error
        self.fail_after = fail_after
        self.calls = []
        self.consumed = 0
        self.closed = False

    async def generate_content_stream(self, *, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        if self.error and self.fail_after is None:
            raise self.error
        return self._stream()

    async def _stream(self):
        try:
            for i, text in enumerate(self.chunks):
                if i == self.fail_after:
                    raise self.error
                await asyncio.sleep(self.delay_s)
                self.consumed += 1
                yield SimpleNamespace(text=text)
        finally:
            self.closed = True


class FakeClient:
    def __init__(self, models):
        self.models = models
        self.closed = False
        self.aio = SimpleNamespace(models=models, aclose=self._aclose)

    async def _aclose(self):
        self.closed = True


@pytest.fixture
def install(monkeypatch):
    clients = []

    def apply(models):
        def build(api_key):
            assert api_key == "key"
            clients.append(FakeClient(models))
            return clients[-1]

        monkeypatch.setattr(gemini.genai, "Client", build)
        return clients

    return apply


def _jpeg(width=1280, height=720):
    image = Image.new("RGB", (width, height), (30, 60, 90))
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


def _request():
    geometry = SceneGeometry(
        frame_id=9,
        t_capture_ns=456,
        rows=3,
        cols=5,
        distances_m=(4.0,) * 15,
        valid=(True,) * 15,
        horizontal_fov_deg=70.0,
    )
    return GuidanceRequest(
        geometry=geometry, camera_jpeg=_jpeg(), recently_spoken=("Turn left.",)
    )


async def _advise(model="gemini-3.5-flash-lite"):
    async with GeminiSceneReasoner(api_key="key", model=model, max_output_tokens=40) as r:
        return [i async for i in r.advise(_request())]


async def test_phrase_name_across_chunks(install):
    models = FakeModels(["TURN", "_RIGHT"])
    install(models)
    [instruction] = await _advise()
    assert instruction.phrase is PhraseId.TURN_RIGHT
    assert instruction.text == "Turn right."
    assert (instruction.frame_id, instruction.t_capture_ns) == (9, 456)


async def test_first_sentence_then_stream_closed(install):
    models = FakeModels(["Bear right", " around the bench.", " Then", " stop.", " More."])
    install(models)
    [instruction] = await _advise()
    assert instruction.phrase is None
    assert instruction.text == "Bear right around the bench."
    assert models.consumed == 5
    assert models.closed


async def test_request_configuration_and_payload(install):
    models = FakeModels(["GO_STRAIGHT"])
    clients = install(models)
    await _advise()
    call = models.calls[0]
    assert call.model == "gemini-3.5-flash-lite"
    assert call.config.system_instruction == SYSTEM_PROMPT
    assert call.config.max_output_tokens == 40
    assert call.config.media_resolution is types.MediaResolution.MEDIA_RESOLUTION_LOW
    assert call.config.thinking_config.thinking_level is types.ThinkingLevel.MINIMAL
    image, text = call.contents
    assert image.inline_data.mime_type == "image/jpeg"
    sent = Image.open(io.BytesIO(image.inline_data.data))
    assert sent.size == (640, 360)
    assert text == user_text(_request())
    assert clients[0].closed


async def test_provider_error_on_call_ends_stream(install):
    models = FakeModels([], error=RuntimeError("quota"))
    install(models)
    assert await _advise() == []


async def test_provider_error_mid_stream_ends_stream(install):
    models = FakeModels(["Bear", " right"], error=RuntimeError("reset"), fail_after=1)
    install(models)
    assert await _advise() == []
    assert models.closed


async def test_empty_answer_yields_nothing(install):
    models = FakeModels(["", "  "])
    install(models)
    assert await _advise() == []


async def test_consumer_cancel_closes_provider_stream(install):
    models = FakeModels(["Bear", " right."], delay_s=10.0)
    install(models)
    async with GeminiSceneReasoner(api_key="key", model="m", max_output_tokens=40) as r:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                async for _ in r.advise(_request()):
                    pass
    assert models.closed


async def test_instruction_arrives_before_tags(install):
    models = FakeModels(["ROAD_CROSS", "ING\nTAGS: pavement@legs ahead, ", "door"])
    install(models)
    first, second = await _advise()
    assert first.phrase is PhraseId.ROAD_CROSSING
    assert first.tags == ()
    assert second.tags == (
        SceneTag("pavement", ((0.4, 2 / 3), (0.6, 2 / 3), (0.6, 1.0), (0.4, 1.0))),
        SceneTag("door"),
    )
    assert second.phrase is None
    assert second.text == ""


async def test_tags_first_order_still_parses(install):
    models = FakeModels(["TAGS: pavement@legs ahead, ", "door\nGO_STRAIGHT"])
    install(models)
    tags_instruction, instruction = await _advise()
    assert tags_instruction.tags == (
        SceneTag("pavement", ((0.4, 2 / 3), (0.6, 2 / 3), (0.6, 1.0), (0.4, 1.0))),
        SceneTag("door"),
    )
    assert instruction.phrase is PhraseId.GO_STRAIGHT


async def test_tags_do_not_delay_the_first_sentence(install):
    models = FakeModels(["TAGS: car\nBear", " right.", " More."])
    install(models)
    tags_instruction, instruction = await _advise()
    assert tags_instruction.tags == (SceneTag("car"),)
    assert instruction.text == "Bear right."
    assert models.consumed == 3


async def test_tags_without_instruction_are_still_yielded(install):
    models = FakeModels(["TAGS: stairs, door"])
    install(models)
    [instruction] = await _advise()
    assert instruction.tags == (SceneTag("stairs"), SceneTag("door"))
    assert instruction.phrase is None
    assert instruction.text == ""