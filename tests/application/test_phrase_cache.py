from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.application.phrase_cache import PhraseCache
from navigator.domain.phrases import CACHED_TEXTS
from navigator.domain.speech import PcmChunk


class CountingTone(ToneSpeechSynthesizer):
    def __init__(self):
        super().__init__(delay_s=0.0, seconds_per_char=0.01)
        self.renders = 0

    async def render(self, text):
        self.renders += 1
        return await super().render(text)


async def test_build_renders_every_cached_text():
    synth = CountingTone()
    cache = PhraseCache()
    await cache.build(synth)
    assert synth.renders == len(CACHED_TEXTS)
    for text in CACHED_TEXTS:
        assert cache.get(text).samples
    assert cache.get("a sentence nobody rendered") is None


async def test_disk_cache_skips_render(tmp_path):
    first = CountingTone()
    cache = PhraseCache(directory=tmp_path, voice_key="tone")
    await cache.build(first)
    assert (tmp_path / "tone" / "stop.pcm").exists()
    assert (tmp_path / "tone" / "continue_for_4_metres.pcm").exists()
    second = CountingTone()
    cache2 = PhraseCache(directory=tmp_path, voice_key="tone")
    await cache2.build(second)
    assert second.renders == 0
    assert cache2.get("Stop.") == cache.get("Stop.")


async def test_voice_key_separates_directories(tmp_path):
    synth = CountingTone()
    await PhraseCache(directory=tmp_path, voice_key="a").build(synth)
    await PhraseCache(directory=tmp_path, voice_key="b").build(synth)
    assert (tmp_path / "a" / "stop.pcm").exists()
    assert (tmp_path / "b" / "stop.pcm").exists()


async def test_remembered_text_is_returned():
    cache = PhraseCache()
    chunk = PcmChunk(samples=b"\x01\x02")
    cache.remember("a novel sentence", chunk)
    assert cache.get("a novel sentence") is chunk


async def test_remembered_evicts_oldest_but_keeps_prerendered():
    cache = PhraseCache()
    await cache.build(CountingTone())
    for index in range(257):
        cache.remember(f"novel {index}", PcmChunk(samples=b"\x01\x02"))
    assert cache.get("novel 0") is None
    assert cache.get("novel 256") is not None
    assert cache.get("Stop.").samples


async def test_remember_writes_nothing_to_disk(tmp_path):
    cache = PhraseCache(directory=tmp_path, voice_key="tone")
    await cache.build(CountingTone())
    before = sorted(p.name for p in (tmp_path / "tone").iterdir())
    cache.remember("a novel sentence", PcmChunk(samples=b"\x01\x02"))
    after = sorted(p.name for p in (tmp_path / "tone").iterdir())
    assert after == before
