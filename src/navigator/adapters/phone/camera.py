import io
import threading

import numpy as np
from PIL import Image

from navigator.domain.frame import Frame
from navigator.ports.clock import Clock


class PhoneFrameSource:
    def __init__(self, clock: Clock, link) -> None:
        self._clock = clock
        self._condition = threading.Condition()
        self._latest: tuple[int, int, bytes] | None = None
        self._sequence = 0
        self._issued = -1
        link.set_frame_callback(self._on_frame)

    def _on_frame(self, jpeg: bytes) -> None:
        with self._condition:
            self._sequence += 1
            self._latest = (self._sequence, self._clock.now_ns(), jpeg)
            self._condition.notify_all()

    def next_frame(
        self, after_frame_id: int, timeout_s: float
    ) -> Frame | None:
        with self._condition:
            fresh = (
                self._condition.wait_for(
                    self._has_newer(after_frame_id), max(0.0, timeout_s)
                )
            )
            if not fresh:
                return None
            sequence, t_capture_ns, jpeg = self._latest
            self._issued = sequence
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        rgb = np.asarray(image)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        return Frame(
            frame_id=sequence,
            t_capture_ns=t_capture_ns,
            width=image.width,
            height=image.height,
            pixels=bgr.tobytes(),
        )

    def _has_newer(self, after_frame_id: int):
        threshold = max(after_frame_id, self._issued)

        def check() -> bool:
            return (
                self._latest is not None and self._latest[0] > threshold
            )

        return check
