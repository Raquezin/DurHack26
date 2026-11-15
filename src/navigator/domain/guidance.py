from dataclasses import dataclass

from navigator.domain.geometry import SceneGeometry
from navigator.domain.phrases import PhraseId
from navigator.domain.tags import SceneTag


@dataclass(frozen=True, slots=True)
class GuidanceRequest:
    geometry: SceneGeometry
    camera_jpeg: bytes
    recently_spoken: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GuidanceInstruction:
    phrase: PhraseId | None
    text: str
    frame_id: int
    t_capture_ns: int
    tags: tuple[SceneTag, ...] = ()
