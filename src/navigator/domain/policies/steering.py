from dataclasses import dataclass, replace

from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import gap_width_m, in_path, side, walk_clearance
from navigator.domain.phrases import PhraseId

_VEER = {-1: PhraseId.VEER_LEFT, 1: PhraseId.VEER_RIGHT}
_TURN = {-1: PhraseId.TURN_LEFT, 1: PhraseId.TURN_RIGHT}
_OPEN = (PhraseId.GO_STRAIGHT, PhraseId.PATH_CLEAR)
_DIRECTIONS = {phrase: d for table in (_VEER, _TURN) for d, phrase in table.items()}
_SIDES = (-1, 1)
_SWITCH_RATIO = 1.5


@dataclass(frozen=True, slots=True)
class SteeringSettings:
    look_m: float = 3.0
    open_m: float = 2.0
    half_width_m: float = 0.4
    confirm_frames: int = 5
    min_interval_s: float = 1.5
    repeat_s: float = 30.0
    max_m: float = 10.0


@dataclass(frozen=True, slots=True)
class SteeringState:
    seen: PhraseId | None = None
    streak: int = 0
    spoken: PhraseId | None = None
    spoken_ns: int | None = None
    committed: int | None = None


def _clearance(geometry: SceneGeometry, settings: SteeringSettings) -> tuple[float, ...]:
    return walk_clearance(geometry, settings.max_m)


def path_clearance(geometry: SceneGeometry, settings: SteeringSettings) -> float:
    clearance = _clearance(geometry, settings)
    blocking = [
        d for col, d in enumerate(clearance) if in_path(geometry, col, d, settings.half_width_m)
    ]
    return min(blocking, default=settings.max_m)


def _open_columns(
    geometry: SceneGeometry, settings: SteeringSettings, at_least_m: float
) -> list[int]:
    clearance = _clearance(geometry, settings)
    return [col for col, d in enumerate(clearance) if d >= at_least_m]


def _wide_enough(
    geometry: SceneGeometry, clearance: tuple[float, ...], settings: SteeringSettings
) -> set[int]:
    wide: set[int] = set()
    run: list[int] = []
    for col, d in enumerate((*clearance, 0.0)):
        if d >= settings.look_m:
            run.append(col)
            continue
        if run:
            nearest = min(clearance[c] for c in run)
            if gap_width_m(geometry, run[0], run[-1], nearest) >= 2 * settings.half_width_m:
                wide.update(run)
        run = []
    return wide


def steer(
    geometry: SceneGeometry,
    settings: SteeringSettings,
    committed: int | None = None,
) -> tuple[PhraseId | None, int | None]:
    if path_clearance(geometry, settings) >= settings.look_m:
        return PhraseId.GO_STRAIGHT, None
    clearance = _clearance(geometry, settings)
    room = {s: 0.0 for s in _SIDES}
    for col, d in enumerate(clearance):
        s = side(col, geometry.cols)
        if s != 0:
            room[s] += d
    wide = _wide_enough(geometry, clearance, settings)
    open_sides = [s for s in _SIDES if any(side(col, geometry.cols) == s for col in wide)]
    if not open_sides:
        return None, None
    best = max(open_sides, key=lambda s: (room[s], s))
    if committed in open_sides and room[committed] * _SWITCH_RATIO >= room[best]:
        chosen = committed
    else:
        chosen = best
    centre = (geometry.cols - 1) / 2
    col = _target(geometry, clearance, wide, chosen)
    table = _VEER if abs(col - centre) <= geometry.cols / 5 else _TURN
    return table[chosen], chosen


def _target(
    geometry: SceneGeometry, clearance: tuple[float, ...], wide: set[int], chosen: int
) -> int:
    centre = (geometry.cols - 1) / 2
    return max(
        (c for c in wide if side(c, geometry.cols) == chosen),
        key=lambda c: (clearance[c], -abs(c - centre)),
    )


def gap(
    geometry: SceneGeometry, settings: SteeringSettings, chosen: int
) -> tuple[int, int] | None:
    clearance = _clearance(geometry, settings)
    wide = _wide_enough(geometry, clearance, settings)
    if not any(side(c, geometry.cols) == chosen for c in wide):
        return None
    first = last = _target(geometry, clearance, wide, chosen)
    while first - 1 in wide:
        first -= 1
    while last + 1 in wide:
        last += 1
    return first, last


def permits(
    geometry: SceneGeometry,
    phrase: PhraseId | None,
    settings: SteeringSettings,
    committed: int | None = None,
) -> bool:
    if phrase in _OPEN:
        return path_clearance(geometry, settings) >= settings.open_m
    direction = _DIRECTIONS.get(phrase)
    if direction is None:
        return True
    open_columns = _open_columns(geometry, settings, settings.open_m)
    if (
        committed is not None
        and direction != committed
        and any(side(col, geometry.cols) == committed for col in open_columns)
    ):
        return False
    return any(side(col, geometry.cols) == direction for col in open_columns)


def advise(
    state: SteeringState, phrase: PhraseId | None, now_ns: int, settings: SteeringSettings
) -> tuple[SteeringState, PhraseId | None]:
    streak = state.streak + 1 if phrase is state.seen else 1
    state = replace(state, seen=phrase, streak=streak)
    if phrase is None or streak < settings.confirm_frames:
        return state, None
    quiet_s = settings.repeat_s if phrase is state.spoken else settings.min_interval_s
    if state.spoken_ns is not None and now_ns - state.spoken_ns < quiet_s * 1e9:
        return state, None
    return replace(state, spoken=phrase, spoken_ns=now_ns), phrase
