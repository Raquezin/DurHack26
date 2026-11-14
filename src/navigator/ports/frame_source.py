from typing import Protocol

from navigator.domain.frame import Frame


class FrameSource(Protocol):
    def next_frame(
        self, after_frame_id: int, timeout_s: float
    ) -> Frame | None: ...
