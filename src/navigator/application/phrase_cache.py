import re
from pathlib import Path

from navigator.domain.phrases import CACHED_TEXTS
from navigator.domain.speech import PcmChunk
from navigator.ports.speech_synthesizer import SpeechSynthesizer

_REMEMBERED_MAX = 256


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class PhraseCache:
    def __init__(
        self,
        directory: Path | None = None,
        voice_key: str | None = None,
    ) -> None:
        self._clips: dict[str, PcmChunk] = {}
        self._remembered: dict[str, PcmChunk] = {}
        self._directory = (
            Path(directory) / voice_key
            if directory is not None and voice_key
            else None
        )

    async def build(self, synthesizer: SpeechSynthesizer) -> None:
        for text in CACHED_TEXTS:
            cached = self._read(text)
            if cached is not None:
                self._clips[text] = cached
                continue
            chunk = await synthesizer.render(text)
            self._clips[text] = chunk
            self._write(text, chunk)

    def _path(self, text: str) -> Path | None:
        if self._directory is None:
            return None
        return self._directory / f"{_slug(text)}.pcm"

    def _read(self, text: str) -> PcmChunk | None:
        path = self._path(text)
        if path is not None and path.exists():
            return PcmChunk(samples=path.read_bytes())
        return None

    def _write(self, text: str, chunk: PcmChunk) -> None:
        path = self._path(text)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(chunk.samples)

    def get(self, text: str) -> PcmChunk | None:
        clip = self._clips.get(text)
        if clip is not None:
            return clip
        return self._remembered.get(text)

    def remember(self, text: str, chunk: PcmChunk) -> None:
        if text in self._clips:
            return
        self._remembered[text] = chunk
        while len(self._remembered) > _REMEMBERED_MAX:
            self._remembered.pop(next(iter(self._remembered)))
