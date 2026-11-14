import argparse
import asyncio
import sys
import wave
from contextlib import AsyncExitStack
from pathlib import Path

from guidance_scene import ROOT, build_synthesizer, enter, missing_keys

from navigator.adapters.audio.wav import WavFileAudioSink
from navigator.bootstrap.secrets import Secrets
from navigator.domain.phrases import PHRASE_TEXT, PhraseId


def clip_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


async def render_all(speech: str, out: Path) -> int:
    secrets = Secrets.load(ROOT / ".env")
    missing = missing_keys(secrets, speech)
    if missing:
        print(f"SKIPPED: {', '.join(missing)} absent from .env")
        return 0
    async with AsyncExitStack() as stack:
        synthesizer = await enter(stack, build_synthesizer(speech, secrets))
        for phrase in PhraseId:
            chunk = await synthesizer.render(PHRASE_TEXT[phrase])
            with WavFileAudioSink(path=out / f"{phrase.value}.wav") as sink:
                sink.play(chunk)
    seconds = {p: clip_seconds(out / f"{p.value}.wav") for p in PhraseId}
    for phrase, length in seconds.items():
        print(f"{phrase.name:<14} {length:5.2f} s  {PHRASE_TEXT[phrase]!r}")
    empty = [p.name for p, length in seconds.items() if length <= 0]
    assert not empty, f"empty clips: {empty}"
    print(f"{len(seconds)} phrases rendered with {speech} into {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speech", default="tone", choices=["tone", "elevenlabs"])
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "phrases")
    args = parser.parse_args()
    return asyncio.run(render_all(args.speech, args.out))


if __name__ == "__main__":
    sys.exit(main())
