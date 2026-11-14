import math

import numpy as np

DEPTH_RANGE_M = 5.0
_STOPS = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
_COLOURS = np.array(
    [
        (255, 0, 0),
        (255, 128, 0),
        (255, 230, 0),
        (60, 200, 60),
        (0, 160, 230),
        (40, 40, 200),
    ]
)


def depth_palette() -> np.ndarray:
    levels = np.linspace(0.0, 1.0, 256)
    channels = [np.interp(levels, _STOPS, _COLOURS[:, c]) for c in range(3)]
    return np.stack(channels, axis=1).round().astype(np.uint8)


def palette_index(distance_m: float) -> int:
    if math.isinf(distance_m):
        return 255
    return int(round(min(max(distance_m / DEPTH_RANGE_M, 0.0), 1.0) * 255))
