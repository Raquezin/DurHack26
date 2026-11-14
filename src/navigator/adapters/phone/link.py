import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

from aiohttp import WSMsgType, web

_STATIC = Path(__file__).parent / "static"

_KIND_JPEG = 1
_KIND_PCM = 2
_KIND_H264 = 3
_ACK = '{"type":"ack"}'
_USE_JPEG = '{"type":"jpeg"}'


class PhoneLink:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._ws: web.WebSocketResponse | None = None
        self._frame_callback: Callable[[bytes], None] | None = None
        self.rtt_ms: float | None = None
        self.phone_fps: float | None = None
        self.bound_port: int | None = None

    def set_frame_callback(
        self, callback: Callable[[bytes, bool], bool]
    ) -> None:
        self._frame_callback = callback

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def __aenter__(self):
        self._loop = asyncio.get_running_loop()
        app = web.Application()
        app.on_response_prepare.append(_no_store)
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_static("/static", _STATIC)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        sockets = site._server.sockets
        if sockets:
            self.bound_port = sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._runner is not None:
            await self._runner.cleanup()

    async def _index(self, request):
        return web.FileResponse(_STATIC / "index.html")

    async def _ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        old = self._ws
        self._ws = ws
        if old is not None:
            await old.close()
        try:
            async for message in ws:
                if message.type == WSMsgType.BINARY:
                    await self._on_binary(ws, message.data)
                elif message.type == WSMsgType.TEXT:
                    await self._on_text(ws, message.data)
        finally:
            if self._ws is ws:
                self._ws = None
        return ws

    async def _on_binary(self, ws, data: bytes) -> None:
        if len(data) < 2 or data[0] not in (_KIND_JPEG, _KIND_H264):
            return
        callback = self._frame_callback
        accepted = callback is None or callback(
            bytes(data[1:]), data[0] == _KIND_H264
        )
        await ws.send_str(_ACK if accepted else _USE_JPEG)

    async def _on_text(self, ws, data: str) -> None:
        try:
            payload = json.loads(data)
        except ValueError:
            return
        kind = payload.get("type")
        if kind in ("stats", "log"):
            self.rtt_ms = payload.get("rtt_ms", self.rtt_ms)
            self.phone_fps = payload.get("fps", self.phone_fps)
            print(f"phone {data}", file=sys.stderr, flush=True)

    def send_pcm(self, samples: bytes) -> None:
        self._schedule(lambda ws: ws.send_bytes(bytes([_KIND_PCM]) + samples))

    def send_interrupt(self) -> None:
        self._schedule(lambda ws: ws.send_str('{"type":"interrupt"}'))

    def _schedule(self, send) -> None:
        loop = self._loop
        ws = self._ws
        if loop is None or loop.is_closed() or ws is None or ws.closed:
            return
        asyncio.run_coroutine_threadsafe(self._try_send(ws, send), loop)

    @staticmethod
    async def _try_send(ws, send) -> None:
        try:
            await send(ws)
        except (ConnectionError, RuntimeError):
            pass


async def _no_store(request, response) -> None:
    response.headers["Cache-Control"] = "no-store"
