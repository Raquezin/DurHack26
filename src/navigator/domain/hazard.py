from dataclasses import dataclass
from enum import Enum


class HazardLevel(Enum):
    CAUTION = "caution"
    STOP = "stop"


class Bearing(Enum):
    LEFT = "left"
    AHEAD = "ahead"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class HazardAlert:
    level: HazardLevel
    bearing: Bearing
    distance_m: float
    frame_id: int
    t_capture_ns: int
