from dataclasses import dataclass, replace

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing, HazardAlert, HazardLevel
from navigator.domain.path import bearing, blocking_zone, walk_clearance

_SWITCH_RATIO = 1.5
_ROOM_CAP_M = 10.0
_RANK = {None: 0, HazardLevel.CAUTION: 1, HazardLevel.STOP: 2}


@dataclass(frozen=True, slots=True)
class HazardThresholds:
    stop_m: float = 1.5
    caution_m: float = 3.0
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
    zone = blocking_zone(geometry, thresholds.half_width_m)
    if zone is None or zone[0] >= thresholds.caution_m:
        return None
    distance, _, col = zone
    return HazardAlert(
        level=HazardLevel.STOP if distance < thresholds.stop_m else HazardLevel.CAUTION,
        bearing=bearing(col, geometry.cols),
        distance_m=distance,
        frame_id=geometry.frame_id,
        t_capture_ns=geometry.t_capture_ns,
    )


def escape(geometry: SceneGeometry, kept: Bearing | None = None) -> Bearing | None:
    clearance = walk_clearance(geometry, float("inf"))
    room: dict[Bearing, tuple[float, float]] = {}
    for col, d in enumerate(clearance):
        way = bearing(col, geometry.cols)
        if way is not Bearing.AHEAD:
            deepest, total = room.get(way, (0.0, 0.0))
            room[way] = (max(deepest, d), total + min(d, _ROOM_CAP_M))
    if not room:
        return None
    best = max(room, key=room.get)
    if kept in room and room[kept][0] * _SWITCH_RATIO >= room[best][0]:
        return kept
    return best


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
