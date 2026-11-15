import asyncio
import threading

from navigator.domain.geometry import Perception
from navigator.domain.policies.describe import TagMap


class SceneBoard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Perception | None = None
        self._tags: TagMap | None = None
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future]] = []

    def put(self, perception: Perception) -> None:
        with self._lock:
            self._latest = perception
            waiters = [
                (loop, fut)
                for loop, fut in self._waiters
                if not fut.done()
            ]
            self._waiters.clear()
        for loop, fut in waiters:
            loop.call_soon_threadsafe(self._deliver, fut, perception)

    @staticmethod
    def _deliver(fut: asyncio.Future, perception: Perception) -> None:
        if not fut.done():
            fut.set_result(perception)

    def latest(self) -> Perception | None:
        with self._lock:
            return self._latest

    def set_tags(self, tags: TagMap) -> None:
        with self._lock:
            self._tags = tags

    def latest_tags(self) -> TagMap | None:
        with self._lock:
            return self._tags

    async def wait_newer(
        self, frame_id: int, timeout_s: float
    ) -> Perception | None:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._latest is not None and self._latest.geometry.frame_id > frame_id:
                return self._latest
            fut = loop.create_future()
            self._waiters.append((loop, fut))
        try:
            return await asyncio.wait_for(fut, timeout_s)
        except TimeoutError:
            return None
        finally:
            with self._lock:
                self._waiters = [
                    w for w in self._waiters if w[1] is not fut
                ]
