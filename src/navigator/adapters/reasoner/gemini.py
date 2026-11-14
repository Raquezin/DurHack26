from collections.abc import AsyncIterator
from contextlib import aclosing

from google import genai
from google.genai import types

from navigator.adapters.reasoner.prompt import (
    SYSTEM_PROMPT,
    first_sentence,
    parse_answer,
    user_text,
)
from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest


def thinking_config(model: str) -> types.ThinkingConfig:
    if model.startswith("gemini-2."):
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)


def generation_config(
    model: str, max_output_tokens: int
) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=max_output_tokens,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        thinking_config=thinking_config(model),
    )


def contents(request: GuidanceRequest) -> list:
    return [
        types.Part.from_bytes(data=request.camera_jpeg, mime_type="image/jpeg"),
        user_text(request),
    ]


class GeminiSceneReasoner:
    def __init__(self, api_key: str, model: str, max_output_tokens: int) -> None:
        self._api_key = api_key
        self._model = model
        self._config = generation_config(model, max_output_tokens)
        self._client = None

    async def __aenter__(self) -> "GeminiSceneReasoner":
        self._client = genai.Client(api_key=self._api_key)
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aio.aclose()
        self._client = None

    async def _answer(self, request: GuidanceRequest) -> str:
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents(request), config=self._config
        )
        buffer = ""
        async with aclosing(stream):
            async for chunk in stream:
                buffer += chunk.text or ""
                sentence = first_sentence(buffer)
                if sentence:
                    return sentence
        return buffer

    async def advise(
        self, request: GuidanceRequest
    ) -> AsyncIterator[GuidanceInstruction]:
        try:
            answer = await self._answer(request)
        except Exception:
            return
        parsed = parse_answer(answer)
        if parsed is None:
            return
        phrase, text = parsed
        yield GuidanceInstruction(
            phrase=phrase,
            text=text,
            frame_id=request.geometry.frame_id,
            t_capture_ns=request.geometry.t_capture_ns,
        )
