import time

from navigator.domain.frame import Frame
from navigator.ports.clock import Clock


class SyntheticFrameSource:
    def __init__(self, clock: Clock, width: int, height: int, fps: int) -> None:
        self._clock = clock
        self._width = width
        self._height = height
        self._interval_ns = int(1_000_000_000 / fps)
        self._start_ns = clock.now_ns()
        self._issued = -1

    def next_frame(
        self, after_frame_id: int, timeout_s: float
    ) -> Frame | None:
        deadline = time.monotonic() + timeout_s
        while True:
            now = self._clock.now_ns()
            index = (now - self._start_ns) // self._interval_ns
            if index > after_frame_id and index > self._issued:
                self._issued = index
                return Frame(
                    frame_id=index,
                    t_capture_ns=now,
                    width=self._width,
                    height=self._height,
                    pixels=self._pixels(index),
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            wake_in = (
                self._start_ns + (index + 1) * self._interval_ns - now
            ) / 1_000_000_000
            time.sleep(max(0.0, min(remaining, wake_in)))

    def _pixels(self, index: int) -> bytes:
        row = bytes(
            (x + index * 7) % 256
            for x in range(self._width)
            for _ in range(3)
        )
        return row * self._height
