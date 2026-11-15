import math

from navigator.domain.geometry import SceneGeometry


def _edge_tangent(edge: int, cols: int, horizontal_fov_deg: float) -> float:
    return (2 * edge / cols - 1) * math.tan(math.radians(horizontal_fov_deg) / 2)


def inner_tangent(col: int, cols: int, horizontal_fov_deg: float) -> float:
    left = _edge_tangent(col, cols, horizontal_fov_deg)
    right = _edge_tangent(col + 1, cols, horizontal_fov_deg)
    if left <= 0 <= right:
        return 0.0
    return min(abs(left), abs(right))


def gap_width_m(geometry: SceneGeometry, first: int, last: int, distance_m: float) -> float:
    left = _edge_tangent(first, geometry.cols, geometry.horizontal_fov_deg)
    right = _edge_tangent(last + 1, geometry.cols, geometry.horizontal_fov_deg)
    return distance_m * (right - left)


def side(col: int, cols: int) -> int:
    centre = (cols - 1) / 2
    return (col > centre) - (col < centre)


def in_path(
    geometry: SceneGeometry, col: int, distance_m: float, half_width_m: float
) -> bool:
    tangent = inner_tangent(col, geometry.cols, geometry.horizontal_fov_deg)
    return distance_m * tangent < half_width_m


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
