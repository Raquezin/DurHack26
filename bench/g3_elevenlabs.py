import argparse
import asyncio
import itertools
import math
import sys
import time

from guidance_scene import ROOT, build_synthesizer, missing_keys

from navigator.bootstrap.secrets import Secrets

SENTENCES = (
    "Keep going straight.",
    "Bear right around the bench.",
    "The corridor turns left ahead.",
    "Door ahead, slightly to your right.",
)
BOUND_MS = 350


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


async def first_audio(synthesizer, text: str) -> tuple[float, int]:
    start = time.perf_counter()
    iterator = synthesizer.stream(text)
    try:
        async for chunk in iterator:
            return time.perf_counter() - start, len(chunk.samples)
    finally:
        await iterator.aclose()
    raise RuntimeError("no audio")


async def main_async(args) -> int:
    secrets = Secrets.load(ROOT / ".env")
    missing = missing_keys(secrets, "elevenlabs")
    if missing:
        print(f"G3 SKIPPED: {', '.join(missing)} absent from .env")
        return 0
    times = []
    sentences = itertools.cycle(SENTENCES)
    async with build_synthesizer("elevenlabs", secrets) as synthesizer:
        for i in range(args.warmup + args.n):
            text = next(sentences)
            try:
                seconds, size = await first_audio(synthesizer, text)
            except Exception as error:
                print(f"{i:>3}: FAILED {type(error).__name__}: {error}")
                continue
            label = "warm-up" if i < args.warmup else f"{i - args.warmup + 1:>3}"
            print(f"{label}: first audio {seconds * 1000:.0f} ms, {size} bytes, {text!r}")
            if i >= args.warmup:
                times.append(seconds * 1000)
            await asyncio.sleep(args.gap_s)
    if not times:
        print("G3 no successful requests")
        return 1
    p50, p95, p99 = (percentile(times, q) for q in (50, 95, 99))
    verdict = "PASS" if p95 <= BOUND_MS else "FAIL"
    print(
        f"G3 {verdict} first audio p50 {p50:.0f} ms, p95 {p95:.0f} ms, p99 {p99:.0f} ms "
        f"over {len(times)} of {args.n} requests (WebSocket opened per request)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--gap-s", type=float, default=0.5)
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
