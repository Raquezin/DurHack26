import asyncio
import json
import threading
from pathlib import Path

from aiohttp import WSMsgType, web

from navigator.adapters.ui.serialize import (
    event_to_json,
    event_to_preview_bytes,
)
from navigator.domain.events import Event, PreviewEvent

_STATIC = Path(__file__).parent / "static"
_QUEUE_SIZE = 8


class WebEventPublisher:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._clients: set[asyncio.Queue] = set()
        self._clients_lock = threading.Lock()
        self.bound_port: int | None = None

    async def __aenter__(self):
        self._loop = asyncio.get_running_loop()
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._ws)
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
        if self._runner is not None:
            await self._runner.cleanup()

    async def _index(self, request):
        return web.FileResponse(_STATIC / "index.html")

    async def _ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_SIZE)
        with self._clients_lock:
            self._clients.add(queue)
        sender = asyncio.create_task(self._send(ws, queue))
        try:
            async for message in ws:
                if message.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
        finally:
            with self._clients_lock:
                self._clients.discard(queue)
            sender.cancel()
        return ws

    async def _send(self, ws, queue: asyncio.Queue) -> None:
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "bytes":
                    await ws.send_bytes(payload)
                else:
                    await ws.send_str(payload)
        except (asyncio.CancelledError, ConnectionError, RuntimeError):
            return

    def publish(self, event: Event) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        if isinstance(event, PreviewEvent):
            message = ("bytes", event_to_preview_bytes(event))
        else:
            message = ("str", json.dumps(event_to_json(event)))
        with self._clients_lock:
            clients = list(self._clients)
        if not clients:
            return
        for queue in clients:
            loop.call_soon_threadsafe(self._offer, queue, message)

    @staticmethod
    def _offer(queue: asyncio.Queue, message) -> None:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            if message[0] != "bytes":
                return
            kept = []
            dropped = False
            while not queue.empty():
                item = queue.get_nowait()
                if item[0] == "bytes" and not dropped:
                    dropped = True
                    continue
                kept.append(item)
            for item in kept:
                queue.put_nowait(item)
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass
