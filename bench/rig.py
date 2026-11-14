import argparse
import asyncio
import sys
import threading
from contextlib import ExitStack, contextmanager

from navigator.bootstrap import adapters
from navigator.bootstrap.config import Settings, apply_overrides
from navigator.bootstrap.secrets import Secrets


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--camera", default="webcam", choices=["webcam", "phone"])
    parser.add_argument("--set", dest="overrides", action="append", default=[])


def settings_from(args) -> Settings:
    base = Settings(
        adapters={"clock": "system", "frame_source": args.camera, "scene_perception": "gpu"}
    )
    return apply_overrides(base, args.overrides)


@contextmanager
def _phone_link(settings: Settings):
    from navigator.adapters.phone.link import PhoneLink

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    link = PhoneLink(settings.phone_host, settings.phone_port)
    asyncio.run_coroutine_threadsafe(link.__aenter__(), loop).result()
    try:
        yield link
    finally:
        asyncio.run_coroutine_threadsafe(link.__aexit__(None, None, None), loop).result()
        loop.call_soon_threadsafe(loop.stop)
        thread.join()


def _enter(stack: ExitStack, obj):
    return stack.enter_context(obj) if hasattr(obj, "__enter__") else obj


@contextmanager
def rig(settings: Settings, camera: bool = True, perception: bool = True):
    secrets = Secrets.load()
    resources = adapters.Resources()
    clock = adapters.build("clock", settings, None, secrets, resources)
    with ExitStack() as stack:
        if camera and settings.adapters["frame_source"] == "phone":
            resources.phone_link = stack.enter_context(_phone_link(settings))
            print(
                f"open the phone page served on port {settings.phone_port} and press Start",
                file=sys.stderr,
            )
        source = None
        if camera:
            source = _enter(
                stack, adapters.build("frame_source", settings, clock, secrets, resources)
            )
        model = None
        if perception:
            model = _enter(
                stack,
                adapters.build("scene_perception", settings, clock, secrets, resources),
            )
            model.warm_up()
        yield clock, source, model


def first_frame(camera):
    frame = None
    while frame is None:
        frame = camera.next_frame(-1, 1.0)
    return frame
