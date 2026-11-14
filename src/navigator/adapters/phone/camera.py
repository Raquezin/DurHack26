import io
import threading

import numpy as np
from PIL import Image

from navigator.adapters.phone.h264 import H264Decoder
from navigator.domain.frame import Frame
from navigator.ports.clock import Clock


class PhoneFrameSource:
    def __init__(self, clock: Clock, link) -> None:
        self._clock = clock
        self._decoder = H264Decoder()
        self._condition = threading.Condition()
        self._latest: tuple[int, int, object] | None = None
        self._sequence = 0
        self._issued = -1
        link.set_frame_callback(self._on_frame)

    def _on_frame(self, payload: bytes, h264: bool) -> bool:
        t_capture_ns = self._clock.now_ns()
        picture = self._decoder.decode(payload) if h264 else payload
        if picture is None:
            return False
        with self._condition:
            self._sequence += 1
            self._latest = (self._sequence, t_capture_ns, picture)
            self._condition.notify_all()
        return True

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
            sequence, t_capture_ns, picture = self._latest
            self._issued = sequence
        if isinstance(picture, bytes):
            image = Image.open(io.BytesIO(picture)).convert("RGB")
            rgb = np.asarray(image)
            bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        else:
            bgr = picture.to_ndarray(format="bgr24")
        return Frame(
            frame_id=sequence,
            t_capture_ns=t_capture_ns,
            width=bgr.shape[1],
            height=bgr.shape[0],
            pixels=bgr.tobytes(),
        )

    def _has_newer(self, after_frame_id: int):
        threshold = max(after_frame_id, self._issued)

        def check() -> bool:
            return (
                self._latest is not None and self._latest[0] > threshold
            )

        return check
