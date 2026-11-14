from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.speech import PcmChunk
from navigator.ports.speech_synthesizer import SpeechSynthesizer


class PhraseCache:
    def __init__(self) -> None:
        self._clips: dict[PhraseId, PcmChunk] = {}

    async def build(self, synthesizer: SpeechSynthesizer) -> None:
        for phrase in PhraseId:
            self._clips[phrase] = await synthesizer.render(PHRASE_TEXT[phrase])

    def get(self, phrase: PhraseId) -> PcmChunk:
        return self._clips[phrase]

    def has(self, phrase: PhraseId) -> bool:
        return phrase in self._clips
