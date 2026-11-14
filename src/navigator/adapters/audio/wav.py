import wave
from pathlib import Path

from navigator.domain.speech import SAMPLE_RATE_HZ, PcmChunk


class WavFileAudioSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._chunks: list[bytes] = []

    def __enter__(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc) -> None:
        with wave.open(str(self._path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE_HZ)
            wav.writeframes(b"".join(self._chunks))

    def play(self, chunk: PcmChunk) -> None:
        self._chunks.append(chunk.samples)

    def interrupt(self) -> None:
        pass

    def is_playing(self) -> bool:
        return False
