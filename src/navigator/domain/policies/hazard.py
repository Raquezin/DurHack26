from dataclasses import dataclass, replace

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing, HazardAlert, HazardLevel
from navigator.domain.path import in_path, side

_BEARINGS = {-1: Bearing.LEFT, 0: Bearing.AHEAD, 1: Bearing.RIGHT}
_RANK = {None: 0, HazardLevel.CAUTION: 1, HazardLevel.STOP: 2}


@dataclass(frozen=True, slots=True)
class HazardThresholds:
    stop_m: float = 1.2
    caution_m: float = 2.0
    half_width_m: float = 0.4
    confirm_frames: int = 2
    closer_m: float = 0.3


@dataclass(frozen=True, slots=True)
class AlertState:
    seen: tuple[HazardLevel | None, Bearing | None] = (None, None)
    streak: int = 0
    announced: HazardLevel | None = None
    bearing: Bearing | None = None
    distance_m: float = float("inf")


def evaluate(
    geometry: SceneGeometry, thresholds: HazardThresholds
) -> HazardAlert | None:
    best = None
    for row in range(geometry.rows):
        for col in range(geometry.cols):
            i = row * geometry.cols + col
            distance = geometry.distances_m[i]
            if not geometry.valid[i] or not in_path(
                geometry, col, distance, thresholds.half_width_m
            ):
                continue
            key = (distance, abs(side(col, geometry.cols)))
            if best is None or key < best[0]:
                best = (key, col)
    if best is None or best[0][0] >= thresholds.caution_m:
        return None
    distance, col = best[0][0], best[1]
    return HazardAlert(
        level=HazardLevel.STOP if distance < thresholds.stop_m else HazardLevel.CAUTION,
        bearing=_BEARINGS[side(col, geometry.cols)],
        distance_m=distance,
        frame_id=geometry.frame_id,
        t_capture_ns=geometry.t_capture_ns,
    )


def announce(
    state: AlertState, alert: HazardAlert | None, thresholds: HazardThresholds
) -> tuple[AlertState, bool]:
    level = alert.level if alert else None
    caution = level is HazardLevel.CAUTION
    seen = (level, alert.bearing if caution else None)
    streak = state.streak + 1 if seen == state.seen else 1
    state = replace(state, seen=seen, streak=streak)
    if streak < thresholds.confirm_frames:
        return state, False
    if alert is None:
        return replace(state, announced=None, bearing=None, distance_m=float("inf")), False
    rose = _RANK[level] > _RANK[state.announced]
    turned = (
        caution
        and state.announced is level
        and state.bearing is not None
        and alert.bearing is not state.bearing
    )
    closer = (
        level is HazardLevel.STOP
        and state.announced is HazardLevel.STOP
        and state.distance_m - alert.distance_m >= thresholds.closer_m
    )
    if rose or turned or closer:
        return replace(
            state, announced=level, bearing=alert.bearing, distance_m=alert.distance_m
        ), True
    if _RANK[level] < _RANK[state.announced]:
        return replace(state, announced=level, bearing=None), False
    return state, False
