import math

import pytest

torch = pytest.importorskip("torch")
zones = pytest.importorskip("navigator.adapters.perception.zones")

ROWS, COLS = 3, 5
HEIGHT, WIDTH = 300, 500
MOUNT_M, PITCH_DEG = 1.4, 10.0


def _scene():
    focal = zones.focal_px(WIDTH, 70.0)
    floor = zones.floor_depth(HEIGHT, focal, MOUNT_M, PITCH_DEG)
    depth = torch.where(torch.isinf(floor), 20.0, floor * 0.95).expand(HEIGHT, WIDTH).clone()
    usable = torch.ones(HEIGHT, WIDTH, dtype=torch.bool)
    return depth, usable, floor


def _reduce(depth, usable, floor):
    nearest, valid = zones.reduce_zones(depth, usable, floor, ROWS, COLS)
    return nearest.tolist(), valid.tolist()


def _zone(row, col):
    return row * COLS + col


def test_open_floor_is_valid_and_clear():
    nearest, valid = _reduce(*_scene())
    assert all(valid)
    assert all(math.isinf(d) for d in nearest)


def test_wall_at_known_distance():
    depth, usable, floor = _scene()
    depth[:, 200:300] = 2.0
    nearest, valid = _reduce(depth, usable, floor)
    for row in range(ROWS):
        assert nearest[_zone(row, 2)] == pytest.approx(2.0)
    assert math.isinf(nearest[_zone(1, 1)])


def test_low_obstacle_on_floor():
    depth, usable, floor = _scene()
    depth[200:, 400:] = 1.0
    nearest, _ = _reduce(depth, usable, floor)
    assert nearest[_zone(2, 4)] == pytest.approx(1.0)


def test_isolated_noise_is_ignored():
    depth, usable, floor = _scene()
    depth[150:155, 150:152] = 0.3
    nearest, _ = _reduce(depth, usable, floor)
    assert math.isinf(nearest[_zone(1, 1)])


def test_zone_without_enough_pixels_is_invalid():
    depth, usable, floor = _scene()
    usable[:100, :100] = False
    usable[:20, :100] = True
    depth[:20, :100] = 1.5
    nearest, valid = _reduce(depth, usable, floor)
    assert not valid[_zone(0, 0)]
    assert valid[_zone(0, 1)]
    assert nearest[_zone(0, 0)] == pytest.approx(1.5)


def test_floor_is_infinite_above_horizon():
    focal = zones.focal_px(WIDTH, 70.0)
    floor = zones.floor_depth(HEIGHT, focal, MOUNT_M, PITCH_DEG)[:, 0]
    horizon = (HEIGHT - 1) / 2 - focal * math.tan(math.radians(PITCH_DEG))
    assert math.isinf(floor[int(horizon) - 1])
    assert math.isfinite(floor[int(horizon) + 2])
    assert floor[-1] == pytest.approx(
        MOUNT_M
        / (
            (HEIGHT - 1) / 2 / focal * math.cos(math.radians(PITCH_DEG))
            + math.sin(math.radians(PITCH_DEG))
        )
    )
