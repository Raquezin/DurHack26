from pathlib import Path

from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.speech import PcmChunk
from navigator.ports.speech_synthesizer import SpeechSynthesizer


class PhraseCache:
    def __init__(
        self,
        directory: Path | None = None,
        voice_key: str | None = None,
    ) -> None:
        self._clips: dict[PhraseId, PcmChunk] = {}
        self._directory = (
            Path(directory) / voice_key
            if directory is not None and voice_key
            else None
        )

    async def build(self, synthesizer: SpeechSynthesizer) -> None:
        for phrase in PhraseId:
            cached = self._read(phrase)
            if cached is not None:
                self._clips[phrase] = cached
                continue
            chunk = await synthesizer.render(PHRASE_TEXT[phrase])
            self._clips[phrase] = chunk
            self._write(phrase, chunk)

    def _path(self, phrase: PhraseId) -> Path | None:
        if self._directory is None:
            return None
        return self._directory / f"{phrase.value}.pcm"

    def _read(self, phrase: PhraseId) -> PcmChunk | None:
        path = self._path(phrase)
        if path is not None and path.exists():
            return PcmChunk(samples=path.read_bytes())
        return None

    def _write(self, phrase: PhraseId, chunk: PcmChunk) -> None:
        path = self._path(phrase)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(chunk.samples)

    def get(self, phrase: PhraseId) -> PcmChunk:
        return self._clips[phrase]

    def has(self, phrase: PhraseId) -> bool:
        return phrase in self._clips
