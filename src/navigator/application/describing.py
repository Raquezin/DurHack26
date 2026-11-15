from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import bearing
from navigator.domain.policies.describe import describe
from navigator.domain.speech import Priority, Utterance
from navigator.domain.tags import SceneTag

_DEADLINE_NS = 4_000_000_000


def description(
    tag: SceneTag, col: int, geometry: SceneGeometry, offset_ns: int
) -> Utterance:
    return Utterance(
        priority=Priority.DESCRIPTION,
        phrase=None,
        text=describe(tag, bearing(col, geometry.cols)),
        frame_id=geometry.frame_id,
        t_capture_ns=geometry.t_capture_ns,
        deadline_ns=geometry.t_capture_ns + _DEADLINE_NS - offset_ns,
    )
