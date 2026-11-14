from dataclasses import dataclass

import numpy as np
import torch
from fastforks import depth as fastforks_depth

from navigator.adapters.perception.previews import PreviewEncoder
from navigator.adapters.perception.zones import (
    floor_depth,
    focal_px,
    intrinsics,
    reduce_zones,
)
from navigator.domain.frame import Frame
from navigator.domain.geometry import Perception, SceneGeometry
from navigator.ports.clock import Clock

WARM_UP_PASSES = 20
WARM_UP_SHAPE = (480, 640)


@dataclass(frozen=True, slots=True)
class _Slot:
    host: np.ndarray
    pinned: torch.Tensor
    device: torch.Tensor
    intrinsics: torch.Tensor
    floor: torch.Tensor


class GpuScenePerception:
    def __init__(
        self,
        clock: Clock,
        model: str,
        input_long_side: int,
        rows: int,
        cols: int,
        horizontal_fov_deg: float,
        scale: float,
        mount_height_m: float,
        pitch_deg: float,
    ) -> None:
        self._clock = clock
        self._model_name = model
        self._input_long_side = input_long_side
        self._rows = rows
        self._cols = cols
        self._hfov = horizontal_fov_deg
        self._scale = scale
        self._mount_height_m = mount_height_m
        self._pitch_deg = pitch_deg
        self._device = torch.device("cuda")
        self._slots: dict[tuple[int, int], _Slot] = {}
        self._model = None
        self._previews = None

    def __enter__(self) -> "GpuScenePerception":
        self._model = fastforks_depth.load(
            self._model_name,
            mode="kernels",
            device=self._device,
            options={"long_side": self._input_long_side},
        )
        self._previews = PreviewEncoder(self._device)
        return self

    def __exit__(self, *exc) -> None:
        self._model = None
        self._previews = None
        self._slots.clear()
        torch.cuda.empty_cache()

    def warm_up(self) -> None:
        height, width = WARM_UP_SHAPE
        pixels = np.random.default_rng(0).integers(
            0, 256, height * width * 3, dtype=np.uint8
        ).tobytes()
        for index in range(WARM_UP_PASSES):
            frame = Frame(index, 0, width, height, pixels)
            self.perceive(frame, with_previews=index % 2 == 0)
        torch.cuda.synchronize()

    def perceive(self, frame: Frame, with_previews: bool) -> Perception:
        slot = self._slot(frame.height, frame.width)
        np.copyto(
            slot.host,
            np.frombuffer(frame.pixels, np.uint8).reshape(slot.host.shape),
        )
        slot.device.copy_(slot.pinned, non_blocking=True)
        rgb = slot.device.permute(2, 0, 1).flip(0).contiguous()
        result = self._model(rgb, intrinsics=slot.intrinsics)
        depth = result.depth * self._scale
        usable = torch.isfinite(depth) & (depth > 0) & result.mask
        nearest, valid = reduce_zones(
            depth, usable, slot.floor, self._rows, self._cols
        )
        values = torch.cat((nearest, valid.float())).cpu().tolist()
        zones = self._rows * self._cols
        geometry = SceneGeometry(
            frame_id=frame.frame_id,
            t_capture_ns=frame.t_capture_ns,
            rows=self._rows,
            cols=self._cols,
            distances_m=tuple(values[:zones]),
            valid=tuple(v > 0.5 for v in values[zones:]),
            horizontal_fov_deg=self._hfov,
        )
        t_ready_ns = self._clock.now_ns()
        camera_jpeg = depth_jpeg = None
        if with_previews:
            camera_jpeg, depth_jpeg = self._previews.encode(rgb, depth, usable)
        return Perception(
            geometry=geometry,
            t_ready_ns=t_ready_ns,
            camera_jpeg=camera_jpeg,
            depth_jpeg=depth_jpeg,
        )

    def _slot(self, height: int, width: int) -> _Slot:
        slot = self._slots.get((height, width))
        if slot is None:
            pinned = torch.empty((height, width, 3), dtype=torch.uint8).pin_memory()
            focal = focal_px(width, self._hfov)
            slot = _Slot(
                host=pinned.numpy(),
                pinned=pinned,
                device=torch.empty_like(pinned, device=self._device),
                intrinsics=intrinsics(height, width, self._hfov),
                floor=floor_depth(
                    height,
                    focal,
                    self._mount_height_m,
                    self._pitch_deg,
                    self._device,
                ),
            )
            self._slots[(height, width)] = slot
        return slot
