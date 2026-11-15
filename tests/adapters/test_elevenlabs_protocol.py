import asyncio
import functools
import json

import httpx
import pytest

from navigator.adapters.speech import elevenlabs
from navigator.adapters.speech.elevenlabs import ElevenLabsSpeechSynthesizer

AUDIO = [b"\x01\x02\x03", b"\x04\x05\x06\x07\x08", b"\x09\x0a"]


def _synth():
    return ElevenLabsSpeechSynthesizer(
        api_key="key", voice_id="voice", model="eleven_flash_v2_5"
    )


async def _body(chunks):
    for chunk in chunks:
        yield chunk


def _mock(monkeypatch, handler):
    requests = []

    def handle(request):
        requests.append(request)
        return handler(request)

    monkeypatch.setattr(
        elevenlabs.httpx,
        "AsyncClient",
        functools.partial(
            httpx.AsyncClient, transport=httpx.MockTransport(handle)
        ),
    )
    return requests


async def test_stream_posts_to_the_streaming_endpoint(monkeypatch):
    requests = _mock(
        monkeypatch,
        lambda request: httpx.Response(200, content=_body([b"\x00\x01"])),
    )
    async with _synth() as synth:
        chunks = [c.samples async for c in synth.stream("  Turn left. ")]
    assert chunks == [b"\x00\x01"]
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/text-to-speech/voice/stream"
    assert request.url.params["output_format"] == "pcm_24000"
    assert request.headers["xi-api-key"] == "key"
    assert json.loads(request.content) == {
        "text": "Turn left.",
        "model_id": "eleven_flash_v2_5",
    }


async def test_stream_reassembles_odd_chunk_boundaries(monkeypatch):
    _mock(
        monkeypatch,
        lambda request: httpx.Response(200, content=_body(AUDIO)),
    )
    async with _synth() as synth:
        chunks = [c.samples async for c in synth.stream("Turn left.")]
    assert chunks == [b"\x01\x02", b"\x03\x04\x05\x06\x07\x08", b"\x09\x0a"]


async def test_stream_drops_an_odd_tail(monkeypatch):
    _mock(
        monkeypatch,
        lambda request: httpx.Response(200, content=_body([b"\x01\x02\x03"])),
    )
    async with _synth() as synth:
        chunks = [c.samples async for c in synth.stream("Stop.")]
    assert chunks == [b"\x01\x02"]


async def test_stream_http_error_raises(monkeypatch):
    _mock(monkeypatch, lambda request: httpx.Response(401))
    async with _synth() as synth:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in synth.stream("Stop."):
                pass


async def test_stream_closes_response_when_consumer_stops(monkeypatch):
    responses = []

    async def body():
        for _ in range(50):
            yield b"\x00\x01" * 100
            await asyncio.sleep(0.05)

    def handler(request):
        response = httpx.Response(200, content=body())
        responses.append(response)
        return response

    _mock(monkeypatch, handler)
    async with _synth() as synth:
        iterator = synth.stream("a much longer sentence to say out loud")
        async for chunk in iterator:
            assert chunk.samples
            break
        await asyncio.wait_for(iterator.aclose(), 1.0)
        assert responses[0].is_closed


async def test_render_posts_and_returns_one_even_chunk(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"\x01\x02\x03\x04\x05")

    monkeypatch.setattr(
        elevenlabs.httpx,
        "AsyncClient",
        functools.partial(
            httpx.AsyncClient, transport=httpx.MockTransport(handler)
        ),
    )
    async with _synth() as synth:
        chunk = await synth.render("Stop.")
    assert chunk.samples == b"\x01\x02\x03\x04"
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/text-to-speech/voice"
    assert request.url.params["output_format"] == "pcm_24000"
    assert request.headers["xi-api-key"] == "key"
    assert json.loads(request.content) == {
        "text": "Stop.",
        "model_id": "eleven_flash_v2_5",
    }


async def test_render_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        elevenlabs.httpx,
        "AsyncClient",
        functools.partial(
            httpx.AsyncClient,
            transport=httpx.MockTransport(lambda r: httpx.Response(401)),
        ),
    )
    async with _synth() as synth:
        with pytest.raises(httpx.HTTPStatusError):
            await synth.render("Stop.")
