import argparse
import asyncio
import json
import math
import sys
import wave
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path

from navigator.adapters.audio.wav import WavFileAudioSink
from navigator.adapters.clock.system import SystemClock
from navigator.adapters.ui.collecting import CollectingEventPublisher
from navigator.application.guidance_loop import GuidanceLoop
from navigator.application.phrase_cache import PhraseCache
from navigator.application.scene_board import SceneBoard
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.bootstrap.config import Settings
from navigator.bootstrap.secrets import Secrets
from navigator.domain.events import GuidanceTextEvent, Outcome, UtteranceEvent
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.policies.trigger import TriggerSettings

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / "fixtures" / "scenes"
SETTINGS = Settings()
REQUIRED = {
    "gemini": ("GEMINI_API_KEY",),
    "elevenlabs": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"),
}


def scene_names() -> list[str]:
    return sorted(path.stem for path in SCENES.glob("*.json"))


def load_scene(name: str) -> tuple[Perception, PhraseId]:
    data = json.loads((SCENES / f"{name}.json").read_text())
    geometry = SceneGeometry(
        frame_id=data["frame_id"],
        t_capture_ns=data["t_capture_ns"],
        rows=data["rows"],
        cols=data["cols"],
        distances_m=tuple(math.inf if d is None else d for d in data["distances_m"]),
        valid=tuple(data["valid"]),
        horizontal_fov_deg=data["horizontal_fov_deg"],
    )
    perception = Perception(
        geometry=geometry,
        t_ready_ns=data["t_capture_ns"],
        camera_jpeg=(SCENES / f"{name}.jpg").read_bytes(),
        depth_jpeg=None,
    )
    return perception, PhraseId[data["expected"]]


def restamp(perception: Perception, frame_id: int, now_ns: int) -> Perception:
    geometry = replace(perception.geometry, frame_id=frame_id, t_capture_ns=now_ns)
    return replace(perception, geometry=geometry, t_ready_ns=now_ns)


def missing_keys(secrets: Secrets, *adapters: str) -> list[str]:
    return [k for a in adapters for k in REQUIRED.get(a, ()) if not secrets.get(k)]


def build_reasoner(name: str, secrets: Secrets, expected: PhraseId, model: str):
    if name == "gemini":
        from navigator.adapters.reasoner.gemini import GeminiSceneReasoner

        return GeminiSceneReasoner(
            api_key=secrets.require("GEMINI_API_KEY"),
            model=model,
            max_output_tokens=SETTINGS.gemini_max_output_tokens,
        )
    from navigator.adapters.reasoner.scripted import ScriptedSceneReasoner

    return ScriptedSceneReasoner(
        text=PHRASE_TEXT[expected], phrase=expected, delay_s=SETTINGS.reasoner_delay_s
    )


def build_synthesizer(name: str, secrets: Secrets):
    if name == "elevenlabs":
        from navigator.adapters.speech.elevenlabs import ElevenLabsSpeechSynthesizer

        return ElevenLabsSpeechSynthesizer(
            api_key=secrets.require("ELEVENLABS_API_KEY"),
            voice_id=secrets.require("ELEVENLABS_VOICE_ID"),
            model=SETTINGS.elevenlabs_model,
        )
    from navigator.adapters.speech.tone import ToneSpeechSynthesizer

    return ToneSpeechSynthesizer(
        delay_s=SETTINGS.tone_delay_s, seconds_per_char=SETTINGS.tone_seconds_per_char
    )


async def enter(stack: AsyncExitStack, adapter):
    if hasattr(adapter, "__aenter__"):
        return await stack.enter_async_context(adapter)
    return adapter


async def feed(board: SceneBoard, base: Perception, clock: SystemClock) -> None:
    frame_id = 0
    while True:
        frame_id += 1
        board.put(restamp(base, frame_id, clock.now_ns()))
        await asyncio.sleep(0.1)


def spoken(events: CollectingEventPublisher) -> bool:
    return any(
        isinstance(e, UtteranceEvent) and e.outcome is Outcome.SPOKEN
        for e in events.events
    )


async def run_scene(args) -> int:
    secrets = Secrets.load(ROOT / ".env")
    missing = missing_keys(secrets, args.reasoner, args.speech)
    if missing:
        print(f"SKIPPED: {', '.join(missing)} absent from .env")
        return 0
    base, expected = load_scene(args.scene)
    clock = SystemClock()
    events = CollectingEventPublisher()
    async with AsyncExitStack() as stack:
        reasoner = await enter(stack, build_reasoner(args.reasoner, secrets, expected, args.model))
        synthesizer = await enter(stack, build_synthesizer(args.speech, secrets))
        sink = stack.enter_context(WavFileAudioSink(path=args.out))
        cache = PhraseCache()
        await cache.build(synthesizer)
        arbiter = SpeechArbiter(
            sink=sink,
            synthesizer=synthesizer,
            cache=cache,
            events=events,
            clock=clock,
            loop=asyncio.get_running_loop(),
        )
        board = SceneBoard()
        guidance = GuidanceLoop(
            board=board,
            reasoner=reasoner,
            arbiter=arbiter,
            events=events,
            clock=clock,
            trigger_settings=TriggerSettings(interval_s=SETTINGS.trigger_interval_s),
            deadline_offset_ns=int(SETTINGS.deadline_offset_ms * 1_000_000),
        )
        tasks = [
            asyncio.create_task(guidance.run()),
            asyncio.create_task(feed(board, base, clock)),
        ]
        for _ in range(int(args.timeout_s / 0.02)):
            if spoken(events):
                break
            await asyncio.sleep(0.02)
        guidance.stop()
        tasks[1].cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return report(args, expected, events)


def report(args, expected: PhraseId, events: CollectingEventPublisher) -> int:
    print(f"scene {args.scene}: expected {expected.name} ({PHRASE_TEXT[expected]!r})")
    print(f"reasoner {args.reasoner}, speech {args.speech}")
    for event in events.events:
        if isinstance(event, GuidanceTextEvent):
            print(f"  guidance_text request {event.request_id}: {event.delta!r}")
        elif isinstance(event, UtteranceEvent):
            print(f"  utterance {event.text!r}: {event.outcome.value}, age {event.age_ms:.0f} ms")
    with wave.open(str(args.out), "rb") as wav:
        seconds = wav.getnframes() / wav.getframerate()
    print(f"wav {args.out}: {seconds:.2f} s")
    if not spoken(events) or seconds <= 0:
        print(f"FAILED: nothing spoken within {args.timeout_s:.1f} s")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True, choices=scene_names())
    parser.add_argument("--reasoner", default="scripted", choices=["scripted", "gemini"])
    parser.add_argument("--speech", default="tone", choices=["tone", "elevenlabs"])
    parser.add_argument("--model", default=SETTINGS.gemini_model)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    args.out = args.out or ROOT / "out" / f"{args.scene}.wav"
    return asyncio.run(run_scene(args))


if __name__ == "__main__":
    sys.exit(main())
