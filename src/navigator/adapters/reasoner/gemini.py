import io
from collections.abc import AsyncIterator
from contextlib import aclosing

from google import genai
from google.genai import types
from PIL import Image

from navigator.adapters.reasoner.prompt import (
    SYSTEM_PROMPT,
    next_part,
    parse_answer,
    user_text,
)
from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest
from navigator.domain.tags import SceneTag

_MAX_IMAGE_SIDE = 640


def generation_config(max_output_tokens: int) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=max_output_tokens,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MINIMAL
        ),
    )


def scaled_jpeg(jpeg: bytes) -> bytes:
    image = Image.open(io.BytesIO(jpeg))
    image.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=70)
    return out.getvalue()


def contents(request: GuidanceRequest) -> list:
    return [
        types.Part.from_bytes(
            data=scaled_jpeg(request.camera_jpeg), mime_type="image/jpeg"
        ),
        user_text(request),
    ]


def _instruction(
    request: GuidanceRequest,
    tags: tuple[SceneTag, ...] | None,
    answer: str | None,
) -> GuidanceInstruction | None:
    base = {
        "frame_id": request.geometry.frame_id,
        "t_capture_ns": request.geometry.t_capture_ns,
    }
    if answer is not None:
        parsed = parse_answer(answer)
        if parsed is None:
            return None
        phrase, text = parsed
        return GuidanceInstruction(phrase=phrase, text=text, tags=(), **base)
    if tags:
        return GuidanceInstruction(phrase=None, text="", tags=tags, **base)
    return None


def _drain(
    request: GuidanceRequest,
    buffer: str,
    answered: bool,
    final: bool = False,
) -> tuple[list[GuidanceInstruction], str, bool]:
    instructions = []
    while (part := next_part(buffer, final=final)) is not None:
        tags, answer, buffer = part
        if answer is not None and answered:
            continue
        instruction = _instruction(request, tags, answer)
        if instruction is None:
            continue
        answered = answered or answer is not None
        instructions.append(instruction)
    return instructions, buffer, answered


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

    async def advise(
        self, request: GuidanceRequest
    ) -> AsyncIterator[GuidanceInstruction]:
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model, contents=contents(request), config=self._config
            )
        except Exception:
            return
        buffer = ""
        answered = False
        try:
            async with aclosing(stream):
                async for chunk in stream:
                    buffer += chunk.text or ""
                    instructions, buffer, answered = _drain(
                        request, buffer, answered
                    )
                    for instruction in instructions:
                        yield instruction
        except Exception:
            return
        instructions, buffer, answered = _drain(
            request, buffer, answered, final=True
        )
        for instruction in instructions:
            yield instruction
