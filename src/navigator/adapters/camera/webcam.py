import shutil
import subprocess
import threading

import cv2

from navigator.adapters.camera.mailbox import FrameMailbox
from navigator.domain.frame import Frame
from navigator.ports.clock import Clock

_RETRY_S = 0.01


class WebcamFrameSource:
    def __init__(
        self,
        clock: Clock,
        device: int,
        width: int,
        height: int,
        fps: int,
        fourcc: str,
    ) -> None:
        self._clock = clock
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._fourcc = fourcc
        self._mailbox = FrameMailbox()
        self._stop = threading.Event()
        self._capture = None
        self._thread = None

    def __enter__(self) -> "WebcamFrameSource":
        _fix_frame_rate(self._device)
        capture = cv2.VideoCapture(self._device, cv2.CAP_V4L2)
        if not capture.isOpened():
            raise RuntimeError(f"cannot open camera {self._device}")
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self._fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        capture.set(cv2.CAP_PROP_FPS, self._fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture = capture
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._capture.release()

    def next_frame(
        self, after_frame_id: int, timeout_s: float
    ) -> Frame | None:
        return self._mailbox.take(after_frame_id, timeout_s)

    def _run(self) -> None:
        frame_id = 0
        while not self._stop.is_set():
            if not self._capture.grab():
                self._stop.wait(_RETRY_S)
                continue
            t_capture_ns = self._clock.now_ns()
            ok, image = self._capture.retrieve()
            if not ok:
                continue
            height, width = image.shape[:2]
            self._mailbox.put(
                Frame(
                    frame_id=frame_id,
                    t_capture_ns=t_capture_ns,
                    width=width,
                    height=height,
                    pixels=image.tobytes(),
                )
            )
            frame_id += 1


def _fix_frame_rate(device: int) -> None:
    if shutil.which("v4l2-ctl") is None:
        return
    subprocess.run(
        [
            "v4l2-ctl",
            "-d",
            f"/dev/video{device}",
            "-c",
            "exposure_dynamic_framerate=0",
        ],
        capture_output=True,
        check=False,
    )
