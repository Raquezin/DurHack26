from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from navigator.domain.hazard import Bearing, HazardLevel
from navigator.domain.speech import Priority
from navigator.domain.tags import SceneTag


class Outcome(Enum):
    SPOKEN = "spoken"
    DROPPED_STALE = "dropped_stale"
    DROPPED_REPEAT = "dropped_repeat"
    REPLACED = "replaced"
    INTERRUPTED = "interrupted"


class PreviewKind(Enum):
    CAMERA = "camera"
    DEPTH = "depth"


@dataclass(frozen=True, slots=True)
class GeometryEvent:
    frame_id: int
    distances_m: tuple[float, ...]
    valid: tuple[bool, ...]
    age_ms: float
    type: ClassVar[str] = "geometry"


@dataclass(frozen=True, slots=True)
class HazardEvent:
    level: HazardLevel
    bearing: Bearing
    distance_m: float
    frame_id: int
    type: ClassVar[str] = "hazard"


@dataclass(frozen=True, slots=True)
class GuidanceTextEvent:
    request_id: int
    delta: str
    final: bool
    type: ClassVar[str] = "guidance_text"


@dataclass(frozen=True, slots=True)
class TagsEvent:
    frame_id: int
    tags: tuple[SceneTag, ...]
    type: ClassVar[str] = "tags"


@dataclass(frozen=True, slots=True)
class RouteEvent:
    frame_id: int
    waypoints: tuple[tuple[float, float], ...]
    boundary: tuple[tuple[float, float], ...]
    blocker: tuple[float, float] | None
    label: str | None
    picture_line: tuple[tuple[float, float], ...]
    picture_blocker: tuple[float, float] | None
    type: ClassVar[str] = "route"


@dataclass(frozen=True, slots=True)
class UtteranceEvent:
    text: str
    priority: Priority
    outcome: Outcome
    age_ms: float
    type: ClassVar[str] = "utterance"


@dataclass(frozen=True, slots=True)
class StageTiming:
    name: str
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass(frozen=True, slots=True)
class TimingEvent:
    stages: tuple[StageTiming, ...]
    type: ClassVar[str] = "timing"


@dataclass(frozen=True, slots=True)
class PreviewEvent:
    kind: PreviewKind
    frame_id: int
    jpeg: bytes
    type: ClassVar[str] = "preview"


Event = (
    GeometryEvent
    | HazardEvent
    | GuidanceTextEvent
    | TagsEvent
    | RouteEvent
    | UtteranceEvent
    | TimingEvent
    | PreviewEvent
)
