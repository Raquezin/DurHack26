from dataclasses import dataclass, replace

from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import column_clearance, in_path, side
from navigator.domain.phrases import PhraseId

_VEER = {-1: PhraseId.VEER_LEFT, 1: PhraseId.VEER_RIGHT}
_TURN = {-1: PhraseId.TURN_LEFT, 1: PhraseId.TURN_RIGHT}


@dataclass(frozen=True, slots=True)
class SteeringSettings:
    look_m: float = 3.0
    half_width_m: float = 0.4
    confirm_frames: int = 5
    min_interval_s: float = 3.0
    max_m: float = 10.0


@dataclass(frozen=True, slots=True)
class SteeringState:
    seen: PhraseId | None = None
    streak: int = 0
    spoken: PhraseId | None = None
    spoken_ns: int | None = None


def _clearance(geometry: SceneGeometry, settings: SteeringSettings) -> tuple[float, ...]:
    rows = range(1, geometry.rows) if geometry.rows > 1 else range(geometry.rows)
    return column_clearance(geometry, rows, settings.max_m)


def path_clearance(geometry: SceneGeometry, settings: SteeringSettings) -> float:
    clearance = _clearance(geometry, settings)
    blocking = [
        d for col, d in enumerate(clearance) if in_path(geometry, col, d, settings.half_width_m)
    ]
    return min(blocking, default=settings.max_m)


def steer(geometry: SceneGeometry, settings: SteeringSettings) -> PhraseId | None:
    if path_clearance(geometry, settings) >= settings.look_m:
        return PhraseId.GO_STRAIGHT
    clearance = _clearance(geometry, settings)
    centre = (geometry.cols - 1) / 2
    best = max(range(geometry.cols), key=lambda c: (clearance[c], -abs(c - centre)))
    direction = side(best, geometry.cols)
    if clearance[best] < settings.look_m or direction == 0:
        return None
    return (_VEER if abs(best - centre) <= 1 else _TURN)[direction]


def advise(
    state: SteeringState, phrase: PhraseId | None, now_ns: int, settings: SteeringSettings
) -> tuple[SteeringState, PhraseId | None]:
    streak = state.streak + 1 if phrase is state.seen else 1
    state = replace(state, seen=phrase, streak=streak)
    if phrase is None or streak < settings.confirm_frames or phrase is state.spoken:
        return state, None
    if state.spoken_ns is not None and now_ns - state.spoken_ns < settings.min_interval_s * 1e9:
        return state, None
    return replace(state, spoken=phrase, spoken_ns=now_ns), phrase
