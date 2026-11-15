import math

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing

_BEARINGS = {-1: Bearing.LEFT, 0: Bearing.AHEAD, 1: Bearing.RIGHT}


def vertical_fov_deg(horizontal_fov_deg: float, width: int, height: int) -> float:
    return math.degrees(
        2 * math.atan(math.tan(math.radians(horizontal_fov_deg) / 2) * height / width)
    )


def edge_tangent(edge: int, cols: int, horizontal_fov_deg: float) -> float:
    return (2 * edge / cols - 1) * math.tan(math.radians(horizontal_fov_deg) / 2)


def bearing_tangent(col: int, cols: int, horizontal_fov_deg: float) -> float:
    left = edge_tangent(col, cols, horizontal_fov_deg)
    right = edge_tangent(col + 1, cols, horizontal_fov_deg)
    return (left + right) / 2


def centre_tangent(col: int, cols: int, horizontal_fov_deg: float) -> float:
    return abs(bearing_tangent(col, cols, horizontal_fov_deg))


def gap_width_m(geometry: SceneGeometry, first: int, last: int, distance_m: float) -> float:
    left = edge_tangent(first, geometry.cols, geometry.horizontal_fov_deg)
    right = edge_tangent(last + 1, geometry.cols, geometry.horizontal_fov_deg)
    return distance_m * (right - left)


def side(col: int, cols: int) -> int:
    centre = (cols - 1) / 2
    return (col > centre) - (col < centre)


def bearing(col: int, cols: int) -> Bearing:
    return _BEARINGS[side(col, cols)]


def below_head(geometry: SceneGeometry) -> range:
    return range(1, geometry.rows) if geometry.rows > 1 else range(geometry.rows)


def in_path(
    geometry: SceneGeometry, col: int, distance_m: float, half_width_m: float
) -> bool:
    tangent = centre_tangent(col, geometry.cols, geometry.horizontal_fov_deg)
    return distance_m * tangent < half_width_m


def blocking_zone(
    geometry: SceneGeometry, half_width_m: float
) -> tuple[float, int, int] | None:
    best = None
    for row in below_head(geometry):
        for col in range(geometry.cols):
            i = row * geometry.cols + col
            distance = geometry.distances_m[i]
            if not geometry.valid[i] or not in_path(
                geometry, col, distance, half_width_m
            ):
                continue
            key = (distance, abs(side(col, geometry.cols)))
            if best is None or key < best[0]:
                best = (key, row, col)
    if best is None:
        return None
    return best[0][0], best[1], best[2]


def column_clearance(
    geometry: SceneGeometry, rows: range, max_m: float
) -> tuple[float, ...]:
    clearance = []
    for col in range(geometry.cols):
        nearest = max_m
        for row in rows:
            i = row * geometry.cols + col
            if geometry.valid[i]:
                nearest = min(nearest, geometry.distances_m[i])
        clearance.append(nearest)
    return tuple(clearance)


def walk_clearance(geometry: SceneGeometry, max_m: float) -> tuple[float, ...]:
    return column_clearance(geometry, below_head(geometry), max_m)


def column_known(geometry: SceneGeometry) -> tuple[bool, ...]:
    return tuple(
        any(geometry.valid[row * geometry.cols + col] for row in below_head(geometry))
        for col in range(geometry.cols)
    )


def scene_changed(
    before: SceneGeometry, after: SceneGeometry, ratio: float, fraction: float, max_m: float
) -> bool:
    changed = 0
    for a, b, va, vb in zip(before.distances_m, after.distances_m, before.valid, after.valid):
        if va != vb:
            changed += 1
        elif va:
            near, far = sorted((min(a, max_m), min(b, max_m)))
            changed += far > near * ratio
    return changed >= fraction * len(after.distances_m)
