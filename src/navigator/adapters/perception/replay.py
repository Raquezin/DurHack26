import io
import json
import math
from pathlib import Path

from PIL import Image

from navigator.adapters.perception.palette import depth_palette, palette_index
from navigator.domain.frame import Frame
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.ports.clock import Clock

PREVIEW_LONG_SIDE = 512
JPEG_QUALITY = 80


class ReplayScenePerception:
    def __init__(self, clock: Clock, session_dir: Path) -> None:
        self._clock = clock
        self._session_dir = Path(session_dir)
        self._geometry = {
            g["frame_id"]: g for g in _jsonl(self._session_dir / "geometry.jsonl")
        }
        self._files = {
            f["frame_id"]: f["file"] for f in _jsonl(self._session_dir / "frames.jsonl")
        }
        self._period = max(self._geometry) + 1
        self._palette = [tuple(int(c) for c in rgb) for rgb in depth_palette()]

    def warm_up(self) -> None:
        pass

    def perceive(self, frame: Frame, with_previews: bool) -> Perception:
        key = frame.frame_id % self._period
        record = self._geometry[key]
        geometry = SceneGeometry(
            frame_id=frame.frame_id,
            t_capture_ns=frame.t_capture_ns,
            rows=record["rows"],
            cols=record["cols"],
            distances_m=tuple(
                math.inf if d is None else d for d in record["distances_m"]
            ),
            valid=tuple(record["valid"]),
            horizontal_fov_deg=record["horizontal_fov_deg"],
        )
        camera_jpeg = depth_jpeg = None
        if with_previews:
            camera = Image.open(self._session_dir / self._files[key])
            camera.thumbnail((PREVIEW_LONG_SIDE, PREVIEW_LONG_SIDE))
            camera_jpeg = _jpeg(camera.convert("RGB"))
            depth = self._depth_image(geometry)
            depth_jpeg = _jpeg(depth.resize(camera.size, Image.Resampling.NEAREST))
        return Perception(
            geometry=geometry,
            t_ready_ns=self._clock.now_ns(),
            camera_jpeg=camera_jpeg,
            depth_jpeg=depth_jpeg,
        )

    def _depth_image(self, geometry: SceneGeometry) -> Image.Image:
        image = Image.new("RGB", (geometry.cols, geometry.rows))
        image.putdata(
            [
                self._palette[palette_index(d)] if ok else (0, 0, 0)
                for d, ok in zip(geometry.distances_m, geometry.valid)
            ]
        )
        return image


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
