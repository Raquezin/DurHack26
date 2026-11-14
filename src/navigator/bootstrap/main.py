import argparse
import asyncio
import contextlib
import sys
import threading

from navigator.application.guidance_loop import GuidanceLoop
from navigator.application.hazard_monitor import HazardMonitor
from navigator.application.perception_loop import PerceptionLoop
from navigator.application.phrase_cache import PhraseCache
from navigator.application.scene_board import SceneBoard
from navigator.application.speech_arbiter import SpeechArbiter
from navigator.bootstrap import adapters
from navigator.bootstrap.config import PRESETS, apply_overrides, resolve
from navigator.bootstrap.secrets import Secrets
from navigator.domain.policies.hazard import HazardThresholds
from navigator.domain.policies.trigger import TriggerSettings


def _voice_key(settings, secrets) -> str:
    name = settings.adapters["speech_synthesizer"]
    if name == "elevenlabs":
        voice = secrets.get("ELEVENLABS_VOICE_ID") or "unknown"
        return f"elevenlabs:{voice}:{settings.elevenlabs_model}"
    return name


_SERVICE_PORTS = [
    "frame_source",
    "scene_perception",
    "scene_reasoner",
    "speech_synthesizer",
    "audio_sink",
    "event_publisher",
]


def _parse(argv):
    parser = argparse.ArgumentParser(prog="navigator")
    parser.add_argument("--preset", default="all-fakes", choices=PRESETS)
    parser.add_argument("--adapter", action="append", default=[])
    parser.add_argument("--duration-s", type=float, default=None)
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    args = parser.parse_args(argv)
    overrides = {}
    for item in args.adapter:
        port, _, name = item.partition("=")
        if port not in adapters.REGISTRY:
            parser.error(f"unknown port {port!r}")
        overrides[port] = name
    settings = resolve(args.preset, overrides)
    try:
        settings = apply_overrides(settings, args.overrides)
    except ValueError as error:
        parser.error(str(error))
    return settings, args.duration_s


async def _enter(stack, obj):
    if hasattr(obj, "__aenter__"):
        return await stack.enter_async_context(obj)
    if hasattr(obj, "__enter__"):
        return stack.enter_context(obj)
    return obj


async def _run(settings, duration_s) -> None:
    secrets = Secrets.load()
    offset_ns = int(settings.deadline_offset_ms * 1_000_000)
    async with contextlib.AsyncExitStack() as stack:
        resources = adapters.Resources()
        clock = adapters.build("clock", settings, None, secrets, resources)
        if "phone" in (
            settings.adapters["frame_source"],
            settings.adapters["audio_sink"],
        ):
            from navigator.adapters.phone.link import PhoneLink

            resources.phone_link = await _enter(
                stack, PhoneLink(settings.phone_host, settings.phone_port)
            )
        built = {}
        for port in _SERVICE_PORTS:
            obj = adapters.build(port, settings, clock, secrets, resources)
            built[port] = await _enter(stack, obj)
        voice_key = _voice_key(settings, secrets)
        cache = PhraseCache(
            directory=settings.phrase_cache_dir, voice_key=voice_key
        )
        await cache.build(built["speech_synthesizer"])
        board = SceneBoard()
        loop = asyncio.get_running_loop()
        arbiter = SpeechArbiter(
            sink=built["audio_sink"],
            synthesizer=built["speech_synthesizer"],
            cache=cache,
            events=built["event_publisher"],
            clock=clock,
            loop=loop,
            hazard_phrase_cooldown_s=settings.hazard_phrase_cooldown_s,
            guidance_phrase_cooldown_s=settings.guidance_phrase_cooldown_s,
        )
        monitor = HazardMonitor(
            arbiter=arbiter,
            events=built["event_publisher"],
            clock=clock,
            thresholds=HazardThresholds(
                stop_m=settings.stop_m, caution_m=settings.caution_m
            ),
            deadline_offset_ns=offset_ns,
        )
        perception_loop = PerceptionLoop(
            source=built["frame_source"],
            perception=built["scene_perception"],
            board=board,
            events=built["event_publisher"],
            clock=clock,
            on_perception=monitor.observe,
            preview_every=settings.preview_every,
        )
        guidance = GuidanceLoop(
            board=board,
            reasoner=built["scene_reasoner"],
            arbiter=arbiter,
            events=built["event_publisher"],
            clock=clock,
            trigger_settings=TriggerSettings(
                interval_s=settings.trigger_interval_s,
                abandon_s=settings.trigger_abandon_s,
            ),
            deadline_offset_ns=offset_ns,
        )
        stop = threading.Event()
        gpu_thread = threading.Thread(
            target=perception_loop.run, args=(stop,), daemon=True
        )
        gpu_thread.start()
        guidance_task = asyncio.create_task(guidance.run())
        try:
            if duration_s is not None:
                await asyncio.sleep(duration_s)
            else:
                await guidance_task
        finally:
            stop.set()
            guidance.stop()
            await asyncio.gather(guidance_task, return_exceptions=True)
            gpu_thread.join(timeout=2)


def main(argv=None) -> None:
    settings, duration_s = _parse(sys.argv[1:] if argv is None else argv)
    try:
        asyncio.run(_run(settings, duration_s))
    except KeyboardInterrupt:
        pass
