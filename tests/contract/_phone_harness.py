import asyncio
import io
import threading

from navigator.adapters.phone.link import PhoneLink


def make_jpeg(width=64, height=48):
    from PIL import Image

    image = Image.new("RGB", (width, height), (10, 120, 30))
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


class FakePhone:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self.loop.run_forever, daemon=True
        )
        self.thread.start()
        self.link = PhoneLink(host="127.0.0.1", port=0)
        self.received: list[bytes] = []
        self.texts: list[str] = []
        self._ws = None
        self._stream_task = None
        asyncio.run_coroutine_threadsafe(self._start(), self.loop).result(
            timeout=10
        )

    async def _start(self) -> None:
        await self.link.__aenter__()
        from aiohttp import ClientSession

        self._session = ClientSession()
        self._ws = await self._session.ws_connect(
            f"http://127.0.0.1:{self.link.bound_port}/ws"
        )
        self._collector = asyncio.create_task(self._collect())

    async def _collect(self) -> None:
        from aiohttp import WSMsgType

        async for message in self._ws:
            if message.type == WSMsgType.BINARY:
                self.received.append(bytes(message.data))
            elif message.type == WSMsgType.TEXT:
                self.texts.append(message.data)

    def send_frame(self, jpeg: bytes) -> None:
        async def send():
            await self._ws.send_bytes(bytes([1]) + jpeg)

        asyncio.run_coroutine_threadsafe(send(), self.loop).result(
            timeout=10
        )

    def start_streaming(self, jpeg: bytes, interval_s=0.05) -> None:
        async def stream():
            while True:
                await self._ws.send_bytes(bytes([1]) + jpeg)
                await asyncio.sleep(interval_s)

        self._stream_task = asyncio.run_coroutine_threadsafe(
            stream(), self.loop
        )

    def wait_received(self, predicate, timeout_s=10.0):
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            match = [m for m in self.received if predicate(m)]
            if match:
                return match[0]
            time.sleep(0.02)
        return None
