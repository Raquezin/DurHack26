from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Frame:
    frame_id: int
    t_capture_ns: int
    width: int
    height: int
    pixels: bytes
