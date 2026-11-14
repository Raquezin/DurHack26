from dataclasses import dataclass

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing, HazardAlert, HazardLevel

_BEARINGS = {1: Bearing.LEFT, 2: Bearing.AHEAD, 3: Bearing.RIGHT}


@dataclass(frozen=True, slots=True)
class HazardThresholds:
    stop_m: float = 1.2
    caution_m: float = 2.0


def evaluate(
    geometry: SceneGeometry, thresholds: HazardThresholds
) -> HazardAlert | None:
    nearest_m = float("inf")
    nearest_col = -1
    centre = (1 + min(4, geometry.cols) - 1) / 2
    for row in range(geometry.rows):
        for col in range(1, min(4, geometry.cols)):
            i = row * geometry.cols + col
            if not geometry.valid[i]:
                continue
            better = geometry.distances_m[i] < nearest_m or (
                geometry.distances_m[i] == nearest_m
                and abs(col - centre) < abs(nearest_col - centre)
            )
            if better:
                nearest_m = geometry.distances_m[i]
                nearest_col = col
    if nearest_m >= thresholds.caution_m:
        return None
    level = (
        HazardLevel.STOP
        if nearest_m < thresholds.stop_m
        else HazardLevel.CAUTION
    )
    return HazardAlert(
        level=level,
        bearing=_BEARINGS[nearest_col],
        distance_m=nearest_m,
        frame_id=geometry.frame_id,
        t_capture_ns=geometry.t_capture_ns,
    )
