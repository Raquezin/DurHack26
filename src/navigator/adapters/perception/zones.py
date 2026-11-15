import math

import torch

FLOOR_MARGIN = 0.9
MAX_RANGE_M = 10.0
NEAR_PERCENTILE = 0.05
MIN_VALID_FRACTION = 0.25
PITCH_MIN_DEG = -20.0
PITCH_MAX_DEG = 40.0
FLOOR_TOP = 0.45
FLOOR_FAR_QUANTILE = 0.9
FLOOR_PROBES = 24
FLOOR_TOLERANCE = 0.03
FLOOR_MIN_ROWS = 0.3
FLOOR_MIN_SPAN = 0.15
HEIGHT_RATIO_MIN, HEIGHT_RATIO_MAX = 0.75, 1.35


def focal_px(width: int, horizontal_fov_deg: float) -> float:
    return (width / 2) / math.tan(math.radians(horizontal_fov_deg) / 2)


def intrinsics(height: int, width: int, horizontal_fov_deg: float) -> torch.Tensor:
    f = focal_px(width, horizontal_fov_deg)
    return torch.tensor(
        [[f, 0.0, (width - 1) / 2], [0.0, f, (height - 1) / 2], [0.0, 0.0, 1.0]]
    )


def floor_depth(
    height: int,
    focal: float,
    mount_height_m: float,
    pitch_deg: float,
    device: torch.device | str = "cpu",
) -> torch.Tensor:
    pitch = math.radians(pitch_deg)
    ray_y = (torch.arange(height, device=device) - (height - 1) / 2) / focal
    down = ray_y * math.cos(pitch) + math.sin(pitch)
    expected = torch.where(
        down > 0, mount_height_m / down.clamp(min=1e-6), torch.inf
    )
    return expected[:, None]


def fit_floor(
    depth: torch.Tensor,
    usable: torch.Tensor,
    focal: float,
    mount_height_m: float,
) -> tuple[float, float] | None:
    height = depth.shape[0]
    top = int(height * FLOOR_TOP)
    ray_y = (torch.arange(top, height, device=depth.device) - (height - 1) / 2) / focal
    far = torch.where(usable[top:], depth[top:], torch.nan).nanquantile(
        FLOOR_FAR_QUANTILE, dim=1
    )
    seen = torch.isfinite(far)
    inverse = torch.where(seen, 1 / far, 0.0)
    probes = torch.linspace(0, height - top - 1, FLOOR_PROBES, device=depth.device).long()
    first, second = torch.combinations(probes, 2).unbind(1)
    slope = (inverse[second] - inverse[first]) / (ray_y[second] - ray_y[first])
    offset = inverse[first] - slope * ray_y[first]
    plausible = seen[first] & seen[second] & _plausible(
        torch.rad2deg(torch.atan2(offset, slope)),
        1 / torch.hypot(slope, offset),
        mount_height_m,
    )
    error = (slope[:, None] * ray_y + offset[:, None] - inverse).abs()
    fits = seen & (error < FLOOR_TOLERANCE * inverse)
    votes = torch.where(plausible, fits.sum(dim=1), 0)
    best = votes.argmax()
    weight = fits[best].float()
    count = weight.sum()
    mean_y = (weight * ray_y).sum() / count
    mean_inverse = (weight * inverse).sum() / count
    spread = (weight * (ray_y - mean_y) ** 2).sum()
    slope = (weight * (ray_y - mean_y) * (inverse - mean_inverse)).sum() / spread
    offset = mean_inverse - slope * mean_y
    lit = torch.where(fits[best], ray_y, torch.nan)
    span = lit.nan_to_num(-torch.inf).max() - lit.nan_to_num(torch.inf).min()
    voted, span, pitch_deg, height_m = torch.stack(
        (
            votes[best].float(),
            span,
            torch.rad2deg(torch.atan2(offset, slope)),
            1 / torch.hypot(slope, offset),
        )
    ).cpu().tolist()
    if voted < FLOOR_MIN_ROWS * (height - top) or not span >= FLOOR_MIN_SPAN:
        return None
    if not _plausible(pitch_deg, height_m, mount_height_m):
        return None
    return pitch_deg, height_m


def _plausible(pitch_deg, height_m, mount_height_m):
    return (
        (pitch_deg >= PITCH_MIN_DEG)
        & (pitch_deg <= PITCH_MAX_DEG)
        & (height_m >= HEIGHT_RATIO_MIN * mount_height_m)
        & (height_m <= HEIGHT_RATIO_MAX * mount_height_m)
    )


def reduce_zones(
    depth: torch.Tensor,
    usable: torch.Tensor,
    floor: torch.Tensor,
    rows: int,
    cols: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    obstacle = usable & (depth < floor * FLOOR_MARGIN) & (depth <= MAX_RANGE_M)
    near = torch.where(obstacle, depth, torch.inf)
    tiles = _tiles(near, rows, cols)
    counts = _tiles(usable, rows, cols).sum(dim=1)
    rank = ((counts - 1).clamp(min=0) * NEAR_PERCENTILE).long()
    nearest = tiles.sort(dim=1).values.gather(1, rank[:, None]).squeeze(1)
    valid = counts >= MIN_VALID_FRACTION * tiles.shape[1]
    return nearest, valid


def _tiles(values: torch.Tensor, rows: int, cols: int) -> torch.Tensor:
    h, w = values.shape[0] // rows, values.shape[1] // cols
    cropped = values[: h * rows, : w * cols]
    return cropped.reshape(rows, h, cols, w).transpose(1, 2).reshape(rows * cols, h * w)
