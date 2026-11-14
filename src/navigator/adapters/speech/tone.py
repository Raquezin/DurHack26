import asyncio
import math
import struct
from collections.abc import AsyncIterator

from navigator.domain.speech import SAMPLE_RATE_HZ, PcmChunk

_CHUNK_S = 0.02


class ToneSpeechSynthesizer:
    def __init__(self, delay_s: float, seconds_per_char: float) -> None:
        self._delay_s = delay_s
        self._seconds_per_char = seconds_per_char

    def _samples(self, text: str, start: int, count: int) -> bytes:
        return struct.pack(
            f"<{count}h",
            *(
                int(
                    12000
                    * math.sin(
                        2 * math.pi * 440 * (start + i) / SAMPLE_RATE_HZ
                    )
                )
                for i in range(count)
            ),
        )

    def _total(self, text: str) -> int:
        seconds = max(1, len(text)) * self._seconds_per_char
        return max(1, int(seconds * SAMPLE_RATE_HZ))

    async def stream(self, text: str) -> AsyncIterator[PcmChunk]:
        await asyncio.sleep(self._delay_s)
        total = self._total(text)
        per = int(_CHUNK_S * SAMPLE_RATE_HZ)
        pos = 0
        while pos < total:
            n = min(per, total - pos)
            yield PcmChunk(samples=self._samples(text, pos, n))
            pos += n
            await asyncio.sleep(0)

    async def render(self, text: str) -> PcmChunk:
        await asyncio.sleep(self._delay_s)
        total = self._total(text)
        return PcmChunk(samples=self._samples(text, 0, total))
