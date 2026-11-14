import threading

from navigator.domain.frame import Frame


class FrameMailbox:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest: Frame | None = None
        self._issued = -1

    def put(self, frame: Frame) -> None:
        with self._condition:
            self._latest = frame
            self._condition.notify_all()

    def take(self, after_frame_id: int, timeout_s: float) -> Frame | None:
        with self._condition:
            if not self._condition.wait_for(
                lambda: self._fresh(after_frame_id), max(0.0, timeout_s)
            ):
                return None
            self._issued = self._latest.frame_id
            return self._latest

    def _fresh(self, after_frame_id: int) -> bool:
        return (
            self._latest is not None
            and self._latest.frame_id > max(after_frame_id, self._issued)
        )
