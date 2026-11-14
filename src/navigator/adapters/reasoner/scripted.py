import asyncio
from collections.abc import AsyncIterator

from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest
from navigator.domain.phrases import PhraseId


class ScriptedSceneReasoner:
    def __init__(
        self, text: str, phrase: PhraseId | None, delay_s: float
    ) -> None:
        self._text = text
        self._phrase = phrase
        self._delay_s = delay_s

    async def advise(
        self, request: GuidanceRequest
    ) -> AsyncIterator[GuidanceInstruction]:
        await asyncio.sleep(self._delay_s)
        yield GuidanceInstruction(
            phrase=self._phrase,
            text=self._text,
            frame_id=request.geometry.frame_id,
            t_capture_ns=request.geometry.t_capture_ns,
        )
