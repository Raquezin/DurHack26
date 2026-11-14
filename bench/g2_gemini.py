import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

from google.genai import errors
from guidance_scene import ROOT, SETTINGS

from navigator.adapters.reasoner.gemini import contents, generation_config
from navigator.bootstrap.secrets import Secrets
from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest

MODEL = "gemini-3.5-flash-lite"
FIRST_TOKEN_S = 1.0
TIMEOUT_S = 15.0


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def session_requests(session: Path):
    lines = (session / "geometry.jsonl").read_text().splitlines()
    for line in lines:
        g = json.loads(line)
        geometry = SceneGeometry(
            frame_id=g["frame_id"],
            t_capture_ns=g["t_capture_ns"],
            rows=g["rows"],
            cols=g["cols"],
            distances_m=tuple(math.inf if d is None else d for d in g["distances_m"]),
            valid=tuple(g["valid"]),
            horizontal_fov_deg=g["horizontal_fov_deg"],
        )
        jpeg = (session / "frames" / f"{g['frame_id']:05d}.jpg").read_bytes()
        yield GuidanceRequest(geometry=geometry, camera_jpeg=jpeg, recently_spoken=())


async def first_token(aio, model: str, request: GuidanceRequest) -> tuple[float, str]:
    config = generation_config(SETTINGS.gemini_max_output_tokens)
    start = time.perf_counter()
    stream = await aio.models.generate_content_stream(
        model=model, contents=contents(request), config=config
    )
    async for chunk in stream:
        if chunk.text:
            return time.perf_counter() - start, chunk.text.strip()
    raise RuntimeError("no text")


async def measure(aio, model: str, args) -> None:
    requests = list(session_requests(args.session))
    step = max(1, len(requests) // (args.n + 1))
    times = []
    for i in range(args.n):
        request = requests[(i + 1) * step % len(requests)]
        try:
            async with asyncio.timeout(TIMEOUT_S):
                seconds, text = await first_token(aio, model, request)
        except TimeoutError:
            seconds, text = TIMEOUT_S, "timeout"
        except errors.APIError as error:
            seconds, text = TIMEOUT_S, f"API error {error.code}"
        times.append(seconds)
        print(f"{model} frame {request.geometry.frame_id:>3}: first token {seconds * 1000:.0f} ms, {text!r}")
        await asyncio.sleep(args.gap_s)
    under = sum(t < FIRST_TOKEN_S for t in times) / len(times)
    p50, p95 = (percentile(times, q) * 1000 for q in (50, 95))
    verdict = "PASS" if p50 <= 700 and under >= 0.9 else "FAIL"
    print(
        f"{model}: G2 {verdict} first token p50 {p50:.0f} ms, p95 {p95:.0f} ms, "
        f"under {FIRST_TOKEN_S:.1f} s {under:.0%} of {len(times)}, a new frame every request"
    )


async def main_async(args) -> int:
    key = Secrets.load(ROOT / ".env").get("GEMINI_API_KEY")
    if key is None:
        print("G2 SKIPPED: GEMINI_API_KEY absent from .env")
        return 0
    from google import genai

    async with genai.Client(api_key=key).aio as aio:
        for model in args.models:
            await measure(aio, model, args)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=Path, default=ROOT / "fixtures" / "sessions" / "default")
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--gap-s", type=float, default=2.0)
    parser.add_argument("--models", nargs="+", default=[MODEL])
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
