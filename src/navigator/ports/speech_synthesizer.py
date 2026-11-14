from collections.abc import AsyncIterator
from typing import Protocol

from navigator.domain.speech import PcmChunk


class SpeechSynthesizer(Protocol):
    def stream(self, text: str) -> AsyncIterator[PcmChunk]: ...
    async def render(self, text: str) -> PcmChunk: ...
