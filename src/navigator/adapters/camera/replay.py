import io
import json
import threading
import time
from pathlib import Path

from PIL import Image

from navigator.adapters.camera.mailbox import FrameMailbox
from navigator.domain.frame import Frame
from navigator.ports.clock import Clock

_SOLO_NS = 33_333_333


class ReplayFrameSource:
    def __init__(self, clock: Clock, session_dir: Path) -> None:
        self._clock = clock
        self._session_dir = Path(session_dir)
        self._mailbox = FrameMailbox()
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self) -> "ReplayFrameSource":
        lines = (self._session_dir / "frames.jsonl").read_text().splitlines()
        entries = [json.loads(line) for line in lines if line]
        if not entries:
            raise ValueError(f"empty session {self._session_dir}")
        jpegs = [(self._session_dir / e["file"]).read_bytes() for e in entries]
        self._thread = threading.Thread(
            target=self._run, args=(entries, jpegs), daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def next_frame(
        self, after_frame_id: int, timeout_s: float
    ) -> Frame | None:
        return self._mailbox.take(after_frame_id, timeout_s)

    def _run(self, entries: list[dict], jpegs: list[bytes]) -> None:
        first_ns = entries[0]["t_capture_ns"]
        offsets = [e["t_capture_ns"] - first_ns for e in entries]
        interval_ns = (
            offsets[-1] // (len(offsets) - 1) if len(offsets) > 1 else _SOLO_NS
        )
        cycle_ns = offsets[-1] + max(1, interval_ns)
        period = max(e["frame_id"] for e in entries) + 1
        start_ns = time.monotonic_ns()
        cycle = 0
        while True:
            for entry, offset_ns, jpeg in zip(entries, offsets, jpegs):
                pixels = _bgr(jpeg)
                due_ns = start_ns + cycle * cycle_ns + offset_ns
                if self._stop.wait(max(0, due_ns - time.monotonic_ns()) / 1e9):
                    return
                self._mailbox.put(
                    Frame(
                        frame_id=cycle * period + entry["frame_id"],
                        t_capture_ns=self._clock.now_ns(),
                        width=entry["width"],
                        height=entry["height"],
                        pixels=pixels,
                    )
                )
            cycle += 1


def _bgr(jpeg: bytes) -> bytes:
    return Image.open(io.BytesIO(jpeg)).convert("RGB").tobytes("raw", "BGR")
