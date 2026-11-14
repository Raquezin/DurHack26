from collections.abc import AsyncIterator
from typing import Protocol

from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest


class SceneReasoner(Protocol):
    def advise(
        self, request: GuidanceRequest
    ) -> AsyncIterator[GuidanceInstruction]: ...
