import asyncio
import json
import threading
from collections import deque
from pathlib import Path

from aiohttp import WSMsgType, web

from navigator.adapters.ui.serialize import (
    event_to_json,
    event_to_preview_bytes,
)
from navigator.domain.events import Event, PreviewEvent, PreviewKind

_STATIC = Path(__file__).parent / "static"
_TEXT_BACKLOG = 256
_QUEUE_BUDGET_S = 0.1
_INITIAL_WINDOW = 2
_ACK = "ack"


class _Client:
    def __init__(self) -> None:
        self.texts: deque[str] = deque(maxlen=_TEXT_BACKLOG)
        self.previews: dict[PreviewKind, bytes] = {}
        self.sent: deque[float] = deque()
        self.min_rtt: float | None = None
        self.window = _INITIAL_WINDOW
        self.wake = asyncio.Event()

    def offer(self, kind: PreviewKind | None, payload) -> None:
        if kind is None:
            self.texts.append(payload)
        else:
            self.previews[kind] = payload
        self.wake.set()

    def acked(self, now: float) -> None:
        if not self.sent:
            return
        full = len(self.sent) >= self.window
        rtt = now - self.sent.popleft()
        self.min_rtt = rtt if self.min_rtt is None else min(self.min_rtt, rtt)
        if rtt > self.min_rtt + _QUEUE_BUDGET_S:
            self.window = max(1, self.window - 1)
        elif full:
            self.window += 1
        self.wake.set()

    def ready(self) -> bool:
        return len(self.sent) < self.window


class WebEventPublisher:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._clients: set[_Client] = set()
        self._clients_lock = threading.Lock()
        self.bound_port: int | None = None

    async def __aenter__(self):
        self._loop = asyncio.get_running_loop()
        app = web.Application()
        app.on_response_prepare.append(_no_store)
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
        client = _Client()
        with self._clients_lock:
            self._clients.add(client)
        sender = asyncio.create_task(self._send(ws, client))
        try:
            async for message in ws:
                if message.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
                if message.type == WSMsgType.TEXT and message.data == _ACK:
                    client.acked(self._loop.time())
        finally:
            with self._clients_lock:
                self._clients.discard(client)
            sender.cancel()
        return ws

    async def _send(self, ws, client: _Client) -> None:
        try:
            while True:
                await client.wake.wait()
                client.wake.clear()
                while client.texts:
                    await ws.send_str(client.texts.popleft())
                if client.previews and client.ready():
                    previews, client.previews = client.previews, {}
                    for payload in previews.values():
                        client.sent.append(self._loop.time())
                        await ws.send_bytes(payload)
        except (asyncio.CancelledError, ConnectionError, RuntimeError):
            return

    def publish(self, event: Event) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        if isinstance(event, PreviewEvent):
            kind, payload = event.kind, event_to_preview_bytes(event)
        else:
            kind, payload = None, json.dumps(event_to_json(event))
        with self._clients_lock:
            clients = list(self._clients)
        if not clients:
            return
        for client in clients:
            loop.call_soon_threadsafe(client.offer, kind, payload)


async def _no_store(request, response) -> None:
    response.headers["Cache-Control"] = "no-store"
