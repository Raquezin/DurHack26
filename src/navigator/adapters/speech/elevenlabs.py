import base64
import json
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import httpx
import websockets

from navigator.domain.speech import PcmChunk

HTTP_BASE = "https://api.elevenlabs.io"
WS_BASE = "wss://api.elevenlabs.io"
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

    def _stream_url(self) -> str:
        query = urlencode(
            {
                "model_id": self._model,
                "output_format": OUTPUT_FORMAT,
                "auto_mode": "true",
            }
        )
        return (
            f"{WS_BASE}/v1/text-to-speech/{self._voice_id}/stream-input?{query}"
        )

    async def stream(self, text: str) -> AsyncIterator[PcmChunk]:
        async with websockets.connect(
            self._stream_url(),
            additional_headers={"xi-api-key": self._api_key},
            close_timeout=0.5,
        ) as socket:
            await socket.send(json.dumps({"text": " "}))
            await socket.send(
                json.dumps({"text": text.strip() + " ", "flush": True})
            )
            await socket.send(json.dumps({"text": ""}))
            carry = b""
            async for raw in socket:
                message = json.loads(raw)
                if message.get("error") or message.get("message"):
                    raise RuntimeError(f"elevenlabs: {message}")
                if message.get("audio"):
                    data = carry + base64.b64decode(message["audio"])
                    cut = len(data) - len(data) % 2
                    carry = data[cut:]
                    if cut:
                        yield PcmChunk(samples=data[:cut])
                if message.get("isFinal"):
                    return

    async def render(self, text: str) -> PcmChunk:
        response = await self._http.post(
            f"/v1/text-to-speech/{self._voice_id}",
            params={"output_format": OUTPUT_FORMAT},
            json={"text": text, "model_id": self._model},
        )
        response.raise_for_status()
        data = response.content
        return PcmChunk(samples=data[: len(data) - len(data) % 2])
