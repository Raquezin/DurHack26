from typing import Protocol

from navigator.domain.frame import Frame
from navigator.domain.geometry import Perception


class ScenePerception(Protocol):
    def warm_up(self) -> None: ...
    def perceive(self, frame: Frame, with_previews: bool) -> Perception: ...
