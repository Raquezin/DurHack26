from dataclasses import dataclass
from enum import IntEnum

from navigator.domain.phrases import PhraseId

SAMPLE_RATE_HZ = 24000


class Priority(IntEnum):
    HAZARD = 0
    GUIDANCE = 1
    DESCRIPTION = 2


@dataclass(frozen=True, slots=True)
class Utterance:
    priority: Priority
    phrase: PhraseId | None
    text: str
    frame_id: int
    t_capture_ns: int
    deadline_ns: int


@dataclass(frozen=True, slots=True)
class PcmChunk:
    samples: bytes
