import asyncio
import base64
import functools
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from websockets.asyncio.server import serve

from navigator.adapters.speech import elevenlabs
from navigator.adapters.speech.elevenlabs import ElevenLabsSpeechSynthesizer

AUDIO = [b"\x01\x02\x03", b"\x04\x05\x06\x07\x08", b"\x09\x0a"]


class FakeServer:
    def __init__(self, audio, linger_s=0.0):
        self.audio = audio
        self.linger_s = linger_s
        self.received = []
        self.paths = []
        self.keys = []
        self.closed = asyncio.Event()

    async def handle(self, connection):
        self.paths.append(connection.request.path)
        self.keys.append(connection.request.headers["xi-api-key"])
        try:
            while True:
                message = json.loads(await connection.recv())
                self.received.append(message)
                if message["text"] == "":
                    break
            for data in self.audio:
                payload = {"audio": base64.b64encode(data).decode()}
                await connection.send(json.dumps(payload))
                await asyncio.sleep(self.linger_s)
            await connection.send(json.dumps({"audio": None, "isFinal": True}))
            await connection.wait_closed()
        finally:
            self.closed.set()


@pytest.fixture
async def fake(monkeypatch):
    servers = []

    async def start(audio, linger_s=0.0):
        server = FakeServer(audio, linger_s)
        handle = await serve(server.handle, "127.0.0.1", 0)
        servers.append(handle)
        port = handle.sockets[0].getsockname()[1]
        monkeypatch.setattr(elevenlabs, "WS_BASE", f"ws://127.0.0.1:{port}")
        return server

    yield start
    for handle in servers:
        handle.close()
        await handle.wait_closed()


def _synth():
    return ElevenLabsSpeechSynthesizer(
        api_key="key", voice_id="voice", model="eleven_flash_v2_5"
    )


async def test_stream_protocol_and_even_chunks(fake):
    server = await fake(AUDIO)
    chunks = [c.samples async for c in _synth().stream("  Turn left. ")]
    assert chunks == [b"\x01\x02", b"\x03\x04\x05\x06\x07\x08", b"\x09\x0a"]
    assert server.received == [
        {"text": " "},
        {"text": "Turn left. ", "flush": True},
        {"text": ""},
    ]
    assert server.keys == ["key"]
    url = urlsplit(server.paths[0])
    assert url.path == "/v1/text-to-speech/voice/stream-input"
    assert parse_qs(url.query) == {
        "model_id": ["eleven_flash_v2_5"],
        "output_format": ["pcm_24000"],
        "auto_mode": ["true"],
    }


async def test_odd_tail_dropped(fake):
    await fake([b"\x01\x02\x03"])
    chunks = [c.samples async for c in _synth().stream("Stop.")]
    assert chunks == [b"\x01\x02"]


async def test_stream_stops_and_closes_when_consumer_stops(fake):
    server = await fake([b"\x00\x01" * 100] * 50, linger_s=0.05)
    iterator = _synth().stream("a much longer sentence to say out loud")
    async for chunk in iterator:
        assert chunk.samples
        break
    await asyncio.wait_for(iterator.aclose(), 1.0)
    await asyncio.wait_for(server.closed.wait(), 1.0)


async def test_server_error_raises(monkeypatch):
    async def handle(connection):
        await connection.recv()
        await connection.send(json.dumps({"message": "bad key", "error": "x"}))
        await connection.wait_closed()

    async with serve(handle, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(elevenlabs, "WS_BASE", f"ws://127.0.0.1:{port}")
        with pytest.raises(RuntimeError, match="bad key"):
            async for _ in _synth().stream("Stop."):
                pass


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
