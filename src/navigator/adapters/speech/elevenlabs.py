from collections.abc import AsyncIterator

import httpx

from navigator.domain.speech import PcmChunk

HTTP_BASE = "https://api.elevenlabs.io"
OUTPUT_FORMAT = "pcm_24000"


class ElevenLabsSpeechSynthesizer:
    def __init__(self, api_key: str, voice_id: str, model: str) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ElevenLabsSpeechSynthesizer":
        self._http = httpx.AsyncClient(
            base_url=HTTP_BASE,
            headers={"xi-api-key": self._api_key},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        return self

    async def __aexit__(self, *exc) -> None:
        await self._http.aclose()
        self._http = None

    async def stream(self, text: str) -> AsyncIterator[PcmChunk]:
        async with self._http.stream(
            "POST",
            f"/v1/text-to-speech/{self._voice_id}/stream",
            params={"output_format": OUTPUT_FORMAT},
            json={"text": text.strip(), "model_id": self._model},
        ) as response:
            response.raise_for_status()
            carry = b""
            async for data in response.aiter_bytes():
                data = carry + data
                cut = len(data) - len(data) % 2
                carry = data[cut:]
                if cut:
                    yield PcmChunk(samples=data[:cut])

    async def render(self, text: str) -> PcmChunk:
        response = await self._http.post(
            f"/v1/text-to-speech/{self._voice_id}",
            params={"output_format": OUTPUT_FORMAT},
            json={"text": text, "model_id": self._model},
        )
        response.raise_for_status()
        data = response.content
        return PcmChunk(samples=data[: len(data) - len(data) % 2])
