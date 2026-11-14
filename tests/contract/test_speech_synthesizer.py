from contextlib import AsyncExitStack
from pathlib import Path

import pytest

from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.bootstrap.config import Settings
from navigator.bootstrap.secrets import Secrets

SECRETS = Secrets.load(Path(__file__).resolve().parents[2] / ".env")
ELEVENLABS_KEYS = ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID")


def _tone():
    return ToneSpeechSynthesizer(delay_s=0.0, seconds_per_char=0.01)


def _elevenlabs():
    from navigator.adapters.speech.elevenlabs import ElevenLabsSpeechSynthesizer

    return ElevenLabsSpeechSynthesizer(
        api_key=SECRETS.require("ELEVENLABS_API_KEY"),
        voice_id=SECRETS.require("ELEVENLABS_VOICE_ID"),
        model=Settings().elevenlabs_model,
    )


FACTORIES = [
    pytest.param(_tone, id="tone"),
    pytest.param(
        _elevenlabs,
        id="elevenlabs",
        marks=[
            pytest.mark.keys,
            pytest.mark.skipif(
                not all(SECRETS.get(k) for k in ELEVENLABS_KEYS),
                reason="ElevenLabs keys absent from .env",
            ),
        ],
    ),
]


@pytest.fixture(params=FACTORIES)
async def synth(request):
    async with AsyncExitStack() as stack:
        adapter = request.param()
        if hasattr(adapter, "__aenter__"):
            adapter = await stack.enter_async_context(adapter)
        yield adapter


async def test_stream_first_chunk_non_empty(synth):
    chunks = []
    async for chunk in synth.stream("hello there"):
        chunks.append(chunk)
    assert chunks
    assert chunks[0].samples
    assert all(len(c.samples) % 2 == 0 for c in chunks)


async def test_stream_stops_when_consumer_stops(synth):
    iterator = synth.stream("a much longer sentence to say out loud")
    async for chunk in iterator:
        assert chunk.samples
        break
    await iterator.aclose()


async def test_render_one_chunk(synth):
    chunk = await synth.render("Stop.")
    assert chunk.samples
    assert len(chunk.samples) % 2 == 0
    longer = await synth.render("Careful, obstacle ahead.")
    assert len(longer.samples) > len(chunk.samples)
