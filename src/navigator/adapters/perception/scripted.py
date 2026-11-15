import io
import math

from navigator.domain.frame import Frame
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.domain.path import vertical_fov_deg
from navigator.ports.clock import Clock

_PREVIEW_WIDTH = 160


class ScriptedScenePerception:
    def __init__(
        self,
        clock: Clock,
        rows: int,
        cols: int,
        horizontal_fov_deg: float,
        mount_height_m: float,
        pitch_deg: float,
        start_m: float,
        speed_mps: float,
    ) -> None:
        self._clock = clock
        self._rows = rows
        self._cols = cols
        self._hfov = horizontal_fov_deg
        self._mount_height_m = mount_height_m
        self._pitch_deg = pitch_deg
        self._start_m = start_m
        self._speed_mps = speed_mps
        self._t0_ns: int | None = None

    def warm_up(self) -> None:
        pass

    def perceive(self, frame: Frame, with_previews: bool) -> Perception:
        if self._t0_ns is None:
            self._t0_ns = frame.t_capture_ns
        elapsed_s = (frame.t_capture_ns - self._t0_ns) / 1_000_000_000
        distance = max(0.3, self._start_m - self._speed_mps * elapsed_s)
        geometry = SceneGeometry(
            frame_id=frame.frame_id,
            t_capture_ns=frame.t_capture_ns,
            rows=self._rows,
            cols=self._cols,
            distances_m=(distance,) * (self._rows * self._cols),
            valid=(True,) * (self._rows * self._cols),
            horizontal_fov_deg=self._hfov,
            vertical_fov_deg=vertical_fov_deg(self._hfov, frame.width, frame.height),
            mount_height_m=self._mount_height_m,
            pitch_deg=self._pitch_deg,
        )
        camera_jpeg = None
        depth_jpeg = None
        if with_previews:
            camera_jpeg = self._camera_jpeg(frame)
            depth_jpeg = self._depth_jpeg(distance)
        return Perception(
            geometry=geometry,
            t_ready_ns=self._clock.now_ns(),
            camera_jpeg=camera_jpeg,
            depth_jpeg=depth_jpeg,
        )

    def _camera_jpeg(self, frame: Frame) -> bytes:
        from PIL import Image

        rgb = bytearray(frame.width * frame.height * 3)
        rgb[0::3] = frame.pixels[2::3]
        rgb[1::3] = frame.pixels[1::3]
        rgb[2::3] = frame.pixels[0::3]
        image = Image.frombytes("RGB", (frame.width, frame.height), bytes(rgb))
        height = frame.height * _PREVIEW_WIDTH // frame.width
        image = image.resize((_PREVIEW_WIDTH, height))
        out = io.BytesIO()
        image.save(out, format="JPEG")
        return out.getvalue()

    def _depth_jpeg(self, distance_m: float) -> bytes:
        from PIL import Image

        level = max(0, min(255, int(255 - distance_m * 50)))
        image = Image.new("L", (self._cols, self._rows), level)
        image = image.resize((_PREVIEW_WIDTH, _PREVIEW_WIDTH * self._rows // self._cols))
        image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, format="JPEG")
        return out.getvalue()
