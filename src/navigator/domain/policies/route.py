import math

from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import (
    bearing_tangent,
    column_known,
    edge_tangent,
    walk_clearance,
)
from navigator.domain.policies.steering import SteeringSettings

Point = tuple[float, float]

ORIGIN: Point = (0.0, 0.0)
_STEP_M = 0.25
_MIN_LEG_M = 0.5
_NEAREST_M = 0.1
_TOLERANCE_M = 1e-6


def _point(x_m: float, z_m: float) -> Point:
    return round(x_m, 2), round(z_m, 2)


def zone_point(geometry: SceneGeometry, col: int, distance_m: float) -> Point:
    tangent = bearing_tangent(col, geometry.cols, geometry.horizontal_fov_deg)
    return _point(distance_m * tangent, distance_m)


def boundary(geometry: SceneGeometry, settings: SteeringSettings) -> tuple[Point, ...]:
    clearance = walk_clearance(geometry, settings.max_m)
    points = []
    for col, (d, seen) in enumerate(zip(clearance, column_known(geometry))):
        reach = d if seen else 0.0
        for edge in (col, col + 1):
            tangent = edge_tangent(edge, geometry.cols, geometry.horizontal_fov_deg)
            points.append(_point(reach * tangent, reach))
    return tuple(points)


def _column_at(geometry: SceneGeometry, tangent: float) -> int | None:
    half = math.tan(math.radians(geometry.horizontal_fov_deg) / 2)
    col = math.floor((tangent / half + 1) / 2 * geometry.cols)
    return col if 0 <= col < geometry.cols else None


def _lane_end(
    geometry: SceneGeometry, settings: SteeringSettings, x_m: float, start_m: float
) -> float:
    clearance = walk_clearance(geometry, settings.max_m)
    end = settings.max_m
    for col, d in enumerate(clearance):
        tangent = bearing_tangent(col, geometry.cols, geometry.horizontal_fov_deg)
        if start_m <= d < end and abs(d * tangent - x_m) < settings.half_width_m:
            end = d
    known = column_known(geometry)
    reached = start_m
    z = max(start_m, _STEP_M)
    while z <= end:
        col = _column_at(geometry, x_m / z)
        if col is None or not known[col] or clearance[col] < z:
            return reached
        reached = z
        z += _STEP_M
    return end


def _aim(
    geometry: SceneGeometry, settings: SteeringSettings, run: tuple[int, int]
) -> float:
    first, last = run
    cols, fov = geometry.cols, geometry.horizontal_fov_deg
    left, right = edge_tangent(first, cols, fov), edge_tangent(last + 1, cols, fov)
    lo, hi = left, right
    for col, d in enumerate(walk_clearance(geometry, settings.max_m)):
        margin = settings.half_width_m / max(d, _NEAREST_M)
        if col < first:
            lo = max(lo, edge_tangent(col + 1, cols, fov) + margin)
        elif col > last:
            hi = min(hi, edge_tangent(col, cols, fov) - margin)
    if lo > hi:
        return (left + right) / 2
    return min(max(0.0, lo), hi)


def _reach(
    geometry: SceneGeometry, settings: SteeringSettings, tangent: float
) -> float:
    cols, fov = geometry.cols, geometry.horizontal_fov_deg
    reach = settings.look_m
    for col, d in enumerate(walk_clearance(geometry, settings.max_m)):
        beside = max(
            edge_tangent(col, cols, fov) - tangent,
            tangent - edge_tangent(col + 1, cols, fov),
            0.0,
        )
        if d < settings.look_m and d * beside < settings.half_width_m - _TOLERANCE_M:
            reach = min(reach, d - settings.half_width_m)
    return max(_MIN_LEG_M, reach)


def _project(geometry: SceneGeometry, point: Point) -> Point:
    x_m, z_m = point
    t_h = math.tan(math.radians(geometry.horizontal_fov_deg) / 2)
    t_v = math.tan(math.radians(geometry.vertical_fov_deg) / 2)
    pitch = math.radians(geometry.pitch_deg)
    u = 0.5 + (x_m / z_m) / (2 * t_h)
    ray_y = (geometry.mount_height_m / z_m - math.sin(pitch)) / math.cos(pitch)
    return u, 0.5 + ray_y / (2 * t_v)


def floor_mark(geometry: SceneGeometry, point: Point) -> Point:
    u, v = _project(geometry, point)
    return round(u, 4), round(min(max(v, 0.0), 1.0), 4)


def floor_line(
    geometry: SceneGeometry, waypoints: tuple[Point, ...]
) -> tuple[Point, ...]:
    pitch = math.radians(geometry.pitch_deg)
    t_v = math.tan(math.radians(geometry.vertical_fov_deg) / 2)
    den = t_v * math.cos(pitch) + math.sin(pitch)
    if den <= 0 or len(waypoints) < 2:
        return ()
    z_min = geometry.mount_height_m / den
    index = next(
        (i for i, (_, z) in enumerate(waypoints) if z >= z_min), len(waypoints)
    )
    if index == len(waypoints):
        return ()
    a, b = waypoints[index - 1], waypoints[index]
    if b[1] == z_min:
        start = b
        rest = waypoints[index + 1 :]
    else:
        start = (a[0] + (b[0] - a[0]) * (z_min - a[1]) / (b[1] - a[1]), z_min)
        rest = waypoints[index:]
    return tuple(
        (round(u, 4), round(v, 4))
        for u, v in (_project(geometry, p) for p in (start, *rest))
    )


def plan(
    geometry: SceneGeometry,
    settings: SteeringSettings,
    run: tuple[int, int] | None,
) -> tuple[Point, ...]:
    if run is None:
        end = _lane_end(geometry, settings, 0.0, 0.0)
        return (ORIGIN, _point(0.0, end)) if end > 0 else (ORIGIN,)
    tangent = _aim(geometry, settings, run)
    reach = _reach(geometry, settings, tangent)
    points = [ORIGIN, _point(reach * tangent, reach)]
    if reach < settings.look_m:
        return tuple(points)
    end = _lane_end(geometry, settings, reach * tangent, reach)
    if end - reach >= _MIN_LEG_M:
        points.append(_point(reach * tangent, end))
    return tuple(points)
