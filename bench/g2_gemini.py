import argparse
import asyncio
import math
import sys
import time

from guidance_scene import ROOT, SETTINGS, load_scene, restamp, scene_names

from navigator.adapters.reasoner.gemini import contents, generation_config
from navigator.adapters.reasoner.prompt import parse_answer
from navigator.bootstrap.secrets import Secrets
from navigator.domain.guidance import GuidanceRequest

MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite")
ABANDON_S = 1.0


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


async def one_request(aio, model: str, request: GuidanceRequest):
    config = generation_config(model, SETTINGS.gemini_max_output_tokens)
    start = time.perf_counter()
    first = None
    text = ""
    stream = await aio.models.generate_content_stream(
        model=model, contents=contents(request), config=config
    )
    async for chunk in stream:
        if chunk.text:
            first = first or time.perf_counter() - start
            text += chunk.text
    return first, time.perf_counter() - start, text


async def measure(aio, errors, model: str, args) -> None:
    base, expected = load_scene(args.scene)
    ttfts, failures, matches = [], 0, 0
    for i in range(args.warmup + args.n):
        perception = restamp(base, i + 1, time.monotonic_ns())
        request = GuidanceRequest(
            geometry=perception.geometry,
            camera_jpeg=perception.camera_jpeg,
            recently_spoken=(),
        )
        try:
            first, total, text = await one_request(aio, model, request)
        except errors.APIError as error:
            print(f"{model}: API ERROR {error.code}: {error.message}")
            if error.code in (401, 403, 404):
                return
            failures += i >= args.warmup
            continue
        label = "warm-up" if i < args.warmup else f"{i - args.warmup + 1:>3}"
        first_ms = f"{first * 1000:.0f} ms" if first else "no token"
        print(f"{model} {label}: ttft {first_ms}, total {total * 1000:.0f} ms, {text.strip()!r}")
        if i < args.warmup:
            continue
        if first is None:
            failures += 1
            continue
        ttfts.append(first)
        parsed = parse_answer(text)
        matches += bool(parsed and parsed[0] is expected)
    if not ttfts:
        print(f"{model}: G2 no successful requests")
        return
    under = sum(t < ABANDON_S for t in ttfts) / (len(ttfts) + failures)
    p50, p95, p99 = (percentile(ttfts, q) * 1000 for q in (50, 95, 99))
    verdict = "PASS" if p50 <= 700 and under >= 0.9 else "FAIL"
    print(
        f"{model}: G2 {verdict} ttft p50 {p50:.0f} ms, p95 {p95:.0f} ms, p99 {p99:.0f} ms, "
        f"under {ABANDON_S:.1f} s {under:.0%} of {len(ttfts) + failures}, "
        f"answered {expected.name} {matches}/{len(ttfts)}"
    )


async def main_async(args) -> int:
    key = Secrets.load(ROOT / ".env").get("GEMINI_API_KEY")
    if key is None:
        print("G2 SKIPPED: GEMINI_API_KEY absent from .env")
        return 0
    from google import genai
    from google.genai import errors

    client = genai.Client(api_key=key)
    async with client.aio as aio:
        for model in args.models:
            await measure(aio, errors, model, args)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="doorway", choices=scene_names())
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
