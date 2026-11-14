import asyncio
import base64
import io
import json
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ABSENT = {"", "placeholder"}
KEYS = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID")
PROMPT = "In at most eight words, what is in this image?"
SENTENCE = "Keep going straight."
TTS_URL = (
    "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
    "?model_id=eleven_flash_v2_5&output_format=pcm_24000&auto_mode=true"
)


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip().removeprefix("export ").strip()] = value.strip().strip("'\"")
    return values | {k: os.environ[k] for k in KEYS if k in os.environ}


def present(env, *keys):
    return all(env.get(k, "").strip() not in ABSENT for k in keys)


def tiny_jpeg():
    image = Image.new("RGB", (128, 96), (90, 90, 90))
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 96), (128, 96), (80, 50), (48, 50)], fill=(150, 130, 100))
    draw.rectangle([54, 20, 74, 50], fill=(110, 70, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def api_message(message):
    try:
        return json.loads(message)["error"]["message"]
    except (TypeError, ValueError, KeyError):
        return " ".join(str(message).split())


async def gemini_model(client, types, errors, model, thinking, image):
    config = types.GenerateContentConfig(
        max_output_tokens=40,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        thinking_config=thinking,
    )
    contents = [types.Part.from_bytes(data=image, mime_type="image/jpeg"), PROMPT]
    start = time.perf_counter()
    first = None
    text = []
    try:
        stream = await client.aio.models.generate_content_stream(model=model, contents=contents, config=config)
        async for chunk in stream:
            if chunk.text:
                first = first or time.perf_counter() - start
                text.append(chunk.text)
    except errors.APIError as error:
        label = "NOT ACCESSIBLE TO THIS KEY" if error.code in (403, 404) else "API ERROR"
        print(f"gemini {model}: {label} ({error.code}: {api_message(error.message)})")
        return
    except Exception as error:
        print(f"gemini {model}: FAILED ({type(error).__name__}: {error})")
        return
    total = time.perf_counter() - start
    if first is None:
        print(f"gemini {model}: NO TEXT after {total * 1000:.0f} ms")
        return
    print(f"gemini {model}: ttft {first * 1000:.0f} ms, total {total * 1000:.0f} ms, text {''.join(text).strip()!r}")


async def check_gemini(env):
    if not present(env, "GEMINI_API_KEY"):
        print("gemini: SKIPPED (GEMINI_API_KEY absent)")
        return
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=env["GEMINI_API_KEY"])
    image = tiny_jpeg()
    models = [
        ("gemini-3.5-flash-lite", types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)),
        ("gemini-2.5-flash-lite", types.ThinkingConfig(thinking_budget=0)),
    ]
    for model, thinking in models:
        await gemini_model(client, types, errors, model, thinking, image)


async def check_elevenlabs(env):
    if not present(env, "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        print("elevenlabs: SKIPPED (ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID absent)")
        return
    import websockets

    url = TTS_URL.format(voice_id=env["ELEVENLABS_VOICE_ID"])
    headers = {"xi-api-key": env["ELEVENLABS_API_KEY"]}
    try:
        async with websockets.connect(url, additional_headers=headers) as socket:
            await socket.send(json.dumps({"text": " "}))
            start = time.perf_counter()
            await socket.send(json.dumps({"text": SENTENCE + " ", "flush": True}))
            first, first_bytes, total_bytes = None, 0, 0
            async for raw in socket:
                message = json.loads(raw)
                if message.get("audio"):
                    size = len(base64.b64decode(message["audio"]))
                    if first is None:
                        first, first_bytes = time.perf_counter() - start, size
                        await socket.send(json.dumps({"text": ""}))
                    total_bytes += size
                elif message.get("isFinal"):
                    break
                else:
                    print(f"elevenlabs: SERVER MESSAGE {message}")
    except Exception as error:
        print(f"elevenlabs: FAILED ({type(error).__name__}: {error})")
        return
    if first is None:
        print("elevenlabs: NO AUDIO received")
        return
    print(
        f"elevenlabs eleven_flash_v2_5: first audio {first * 1000:.0f} ms, "
        f"first chunk {first_bytes} bytes, total {total_bytes} bytes ({total_bytes / 48000:.2f} s pcm_24000)"
    )


async def main():
    env = load_env(ROOT / ".env")
    await check_gemini(env)
    await check_elevenlabs(env)


if __name__ == "__main__":
    asyncio.run(main())
