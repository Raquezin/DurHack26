from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneGeometry:
    frame_id: int
    t_capture_ns: int
    rows: int
    cols: int
    distances_m: tuple[float, ...]
    valid: tuple[bool, ...]
    horizontal_fov_deg: float
    vertical_fov_deg: float
    mount_height_m: float
    pitch_deg: float


@dataclass(frozen=True, slots=True)
class Perception:
    geometry: SceneGeometry
    t_ready_ns: int
    camera_jpeg: bytes | None
    depth_jpeg: bytes | None
