from collections.abc import AsyncIterator
from contextlib import aclosing

from google import genai
from google.genai import types

from navigator.adapters.reasoner.prompt import (
    SYSTEM_PROMPT,
    first_sentence,
    parse_answer,
    split_tags,
    user_text,
)
from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest


def generation_config(max_output_tokens: int) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=max_output_tokens,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MINIMAL
        ),
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
        self._config = generation_config(max_output_tokens)
        self._client = None

    async def __aenter__(self) -> "GeminiSceneReasoner":
        self._client = genai.Client(api_key=self._api_key)
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aio.aclose()
        self._client = None

    async def _answer(self, request: GuidanceRequest) -> tuple[tuple[str, ...], str]:
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents(request), config=self._config
        )
        buffer = ""
        async with aclosing(stream):
            async for chunk in stream:
                buffer += chunk.text or ""
                split = split_tags(buffer)
                if split is None:
                    continue
                tags, rest = split
                sentence = first_sentence(rest)
                if sentence:
                    return tags, sentence
        return split_tags(buffer, final=True)

    async def advise(
        self, request: GuidanceRequest
    ) -> AsyncIterator[GuidanceInstruction]:
        try:
            tags, answer = await self._answer(request)
        except Exception:
            return
        parsed = parse_answer(answer)
        if parsed is None and not tags:
            return
        phrase, text = parsed or (None, "")
        yield GuidanceInstruction(
            phrase=phrase,
            text=text,
            frame_id=request.geometry.frame_id,
            t_capture_ns=request.geometry.t_capture_ns,
            tags=tags,
        )
