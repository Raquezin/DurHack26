import pytest

from navigator.adapters.speech.tone import ToneSpeechSynthesizer


def _tone():
    return ToneSpeechSynthesizer(delay_s=0.0, seconds_per_char=0.01)


FACTORIES = [_tone]


@pytest.mark.parametrize("factory", FACTORIES)
async def test_stream_first_chunk_non_empty(factory):
    synth = factory()
    chunks = []
    async for chunk in synth.stream("hello there"):
        chunks.append(chunk)
    assert chunks
    assert chunks[0].samples
    assert all(len(c.samples) % 2 == 0 for c in chunks)


@pytest.mark.parametrize("factory", FACTORIES)
async def test_stream_stops_when_consumer_stops(factory):
    synth = factory()
    iterator = synth.stream("a much longer sentence to say out loud")
    async for chunk in iterator:
        assert chunk.samples
        break
    await iterator.aclose()


@pytest.mark.parametrize("factory", FACTORIES)
async def test_render_one_chunk(factory):
    synth = factory()
    chunk = await synth.render("Stop.")
    assert chunk.samples
    assert len(chunk.samples) % 2 == 0
    longer = await synth.render("Careful, obstacle ahead.")
    assert len(longer.samples) > len(chunk.samples)
