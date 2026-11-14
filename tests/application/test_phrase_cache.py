from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.speech.tone import ToneSpeechSynthesizer
from navigator.application.phrase_cache import PhraseCache
from navigator.domain.phrases import PHRASE_TEXT, PhraseId


class CountingTone(ToneSpeechSynthesizer):
    def __init__(self):
        super().__init__(delay_s=0.0, seconds_per_char=0.01)
        self.renders = 0

    async def render(self, text):
        self.renders += 1
        return await super().render(text)


async def test_build_renders_every_phrase():
    synth = CountingTone()
    cache = PhraseCache()
    await cache.build(synth)
    assert synth.renders == len(PhraseId)
    for phrase in PhraseId:
        assert cache.has(phrase)
        assert cache.get(phrase).samples


async def test_disk_cache_skips_render(tmp_path):
    first = CountingTone()
    cache = PhraseCache(directory=tmp_path, voice_key="tone")
    await cache.build(first)
    assert (tmp_path / "tone" / "stop.pcm").exists()
    second = CountingTone()
    cache2 = PhraseCache(directory=tmp_path, voice_key="tone")
    await cache2.build(second)
    assert second.renders == 0
    assert cache2.get(PhraseId.STOP) == cache.get(PhraseId.STOP)


async def test_voice_key_separates_directories(tmp_path):
    synth = CountingTone()
    await PhraseCache(directory=tmp_path, voice_key="a").build(synth)
    await PhraseCache(directory=tmp_path, voice_key="b").build(synth)
    assert (tmp_path / "a" / "stop.pcm").exists()
    assert (tmp_path / "b" / "stop.pcm").exists()
