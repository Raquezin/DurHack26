import math

import torch

FLOOR_MARGIN = 0.9
MAX_RANGE_M = 10.0
NEAR_PERCENTILE = 0.05
MIN_VALID_FRACTION = 0.25


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
