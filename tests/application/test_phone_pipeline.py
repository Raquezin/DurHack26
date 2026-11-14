import asyncio
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "contract")
)

from _phone_harness import make_jpeg

from navigator.bootstrap.config import apply_overrides, resolve
from navigator.bootstrap.main import _parse, _run


def _settings(port):
    settings = resolve(
        "phone",
        {
            "scene_perception": "scripted",
            "scene_reasoner": "scripted",
            "speech_synthesizer": "tone",
            "event_publisher": "collecting",
        },
    )
    return replace(
        settings,
        phone_port=port,
        scripted_speed_mps=4.0,
        phrase_cache_dir=Path("/tmp/phrase_cache_test"),
    )


async def test_phone_frames_to_hazard_pcm():
    from aiohttp.test_utils import unused_port

    port = unused_port()
    settings = _settings(port)
    task = asyncio.create_task(_run(settings, 15.0))
    for _ in range(100):
        await asyncio.sleep(0.05)
        try:
            import socket

            with socket.create_connection(
                ("127.0.0.1", port), timeout=0.2
            ):
                break
        except OSError:
            continue
    phone = _PhoneClient(port)
    await phone.connect()
    await phone.stream(make_jpeg(64, 48), seconds=6)
    pcm = phone.first_pcm()
    await phone.close()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert pcm is not None
    assert pcm[0] == 2
    assert len(pcm) > 100


class _PhoneClient:
    def __init__(self, port):
        self.port = port
        self.received = []

    async def connect(self):
        from aiohttp import ClientSession

        self._session = ClientSession()
        self._ws = await self._session.ws_connect(
            f"http://127.0.0.1:{self.port}/ws"
        )
        self._collector = asyncio.create_task(self._collect())

    async def _collect(self):
        from aiohttp import WSMsgType

        async for message in self._ws:
            if message.type == WSMsgType.BINARY:
                self.received.append(bytes(message.data))

    async def stream(self, jpeg, seconds):
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            await self._ws.send_bytes(bytes([1]) + jpeg)
            await asyncio.sleep(0.1)
            if any(m[0] == 2 for m in self.received):
                return

    def first_pcm(self):
        for m in self.received:
            if m[0] == 2:
                return m
        return None

    async def close(self):
        self._collector.cancel()
        await self._session.close()


def test_set_overrides_parse_types():
    settings = resolve("all-fakes", {})
    updated = apply_overrides(
        settings,
        [
            "hfov_deg=55",
            "preview_every=2",
            "scripted_speed_mps=0.75",
            "wav_path=out/x.wav",
            "audio_device=3",
            "audio_device=none",
        ],
    )
    assert updated.hfov_deg == 55.0
    assert updated.preview_every == 2
    assert updated.scripted_speed_mps == 0.75
    assert str(updated.wav_path) == "out/x.wav"
    assert updated.audio_device is None


def test_set_overrides_rejects_unknown_key():
    with pytest.raises(ValueError):
        apply_overrides(resolve("all-fakes", {}), ["nope=1"])


def test_parse_set_via_cli():
    settings, duration = _parse(
        ["--preset", "all-fakes", "--set", "hfov_deg=55",
         "--duration-s", "3"]
    )
    assert settings.hfov_deg == 55.0
    assert duration == 3.0
